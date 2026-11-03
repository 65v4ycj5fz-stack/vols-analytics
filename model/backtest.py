"""Walk-forward backtest with no lookahead.

For each test season S:
  1. Hyperparameters (Elo K / home bonus / offseason regression, and the adjusted-EPA
     ridge penalty / prior weight) are chosen using only seasons before S.
  2. The margin model and sigma are fitted on seasons before S.
  3. Every S game is predicted from pregame features (which only use earlier games).
Evaluation is on FBS-vs-FBS games with a closing line. 2019 is burn-in only.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict

import numpy as np
import pandas as pd
from scipy.stats import norm

from model.features import EffParams, game_features
from model.margin import ELO_ONLY, FULL, MarginModel, market_sigma
from model.ratings import EloParams

ELO_GRID = [EloParams(k=k, home_field=h, season_regression=r)
            for k, h, r in itertools.product([30, 45, 60], [0, 20, 40], [0.05, 0.15, 0.3])]
EFF_GRID = [EffParams(alpha=a, prior_games=g, prior_keep=k)
            for a, g, k in itertools.product([0.1, 0.3, 1.0], [2.0, 4.0], [0.8, 1.0])]
BURN_IN = 1  # seasons used only to warm up ratings
ATS_EDGE = 3.0


def eval_mask(f: pd.DataFrame) -> pd.Series:
    return ((f["home_class"] == "fbs") & (f["away_class"] == "fbs") & f["completed"]
            & f["margin"].notna() & f["market_margin"].notna())


def _feature_sets(games: pd.DataFrame, adv: pd.DataFrame, log=print) -> dict[tuple[int, int], pd.DataFrame]:
    """Features for every grid combination. Elo and EPA parts are computed separately then joined."""
    elo_cols = ["game_id", "home_elo_pre", "away_elo_pre", "elo_diff", "home_elo_post", "away_elo_post"]
    base = None
    eff_parts = {}
    for j, ep in enumerate(EFF_GRID):
        f = game_features(games, adv, EloParams(), ep)
        eff_parts[j] = f[["game_id", "home_adj_off", "home_adj_def", "away_adj_off", "away_adj_def",
                          "home_games_in_season", "away_games_in_season", "epa_diff"]]
        if base is None:
            base = f.drop(columns=elo_cols[1:] + list(eff_parts[j].columns[1:]))
        log(f"  eff grid {j + 1}/{len(EFF_GRID)}")
    from model.ratings import run_elo
    elo_parts = {}
    for i, ep in enumerate(ELO_GRID):
        e, _ = run_elo(games, ep)
        e["elo_diff"] = e["home_elo_pre"] - e["away_elo_pre"]
        elo_parts[i] = e[elo_cols]
    return {(i, j): base.merge(elo_parts[i], on="game_id").merge(eff_parts[j], on="game_id")
            for i in elo_parts for j in eff_parts}


def _train_score(f: pd.DataFrame, train: pd.Series, features: tuple[str, ...]) -> float:
    """In-sample margin MAE on training seasons (selection criterion; test season never seen)."""
    tr = f[train]
    m = MarginModel(features).fit(tr)
    return float(np.mean(np.abs(m.predict(tr) - tr["margin"])))


def metrics(pred: np.ndarray, wp: np.ndarray, d: pd.DataFrame) -> dict:
    margin, market = d["margin"].to_numpy(), d["market_margin"].to_numpy()
    home_win = (margin > 0).astype(float)
    decided = margin != 0
    edge = pred - market
    ats_result = margin - market  # >0: home covered
    pick_home = edge > 0
    graded = (ats_result != 0) & (edge != 0)
    win = graded & (pick_home == (ats_result > 0))
    big = graded & (np.abs(edge) >= ATS_EDGE)
    wpc = np.clip(wp, 1e-6, 1 - 1e-6)
    return {
        "games": int(len(d)),
        "mae_vs_actual": float(np.mean(np.abs(pred - margin))),
        "rmse_vs_actual": float(np.sqrt(np.mean((pred - margin) ** 2))),
        "mae_vs_market": float(np.mean(np.abs(edge))),
        "straight_up_accuracy": float(np.mean((pred > 0)[decided] == (margin > 0)[decided])),
        "brier": float(np.mean((wp - home_win) ** 2)),
        "log_loss": float(-np.mean(home_win * np.log(wpc) + (1 - home_win) * np.log(1 - wpc))),
        "ats_wins": int(win.sum()), "ats_losses": int((graded & ~win).sum()),
        "ats_pushes": int((ats_result == 0).sum()),
        "ats_win_pct": float(win.sum() / graded.sum()) if graded.sum() else None,
        f"ats_edge{int(ATS_EDGE)}_wins": int((win & big).sum()),
        f"ats_edge{int(ATS_EDGE)}_losses": int((big & ~win).sum()),
        f"ats_edge{int(ATS_EDGE)}_win_pct": float((win & big).sum() / big.sum()) if big.sum() else None,
    }


def calibration(wp: np.ndarray, outcome: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(wp, edges) - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        p = outcome[m].mean()
        se = np.sqrt(max(p * (1 - p), 1e-9) / m.sum())
        out.append({"bin_low": float(edges[b]), "bin_high": float(edges[b + 1]), "n": int(m.sum()),
                    "mean_predicted": float(wp[m].mean()), "actual_rate": float(p),
                    "ci95_low": float(max(0, p - 1.96 * se)), "ci95_high": float(min(1, p + 1.96 * se))})
    return out


def walk_forward(games: pd.DataFrame, adv: pd.DataFrame, test_seasons: list[int], log=print) -> dict:
    feats = _feature_sets(games, adv, log)
    seasons = sorted(games["season"].unique())
    first_train = seasons[BURN_IN]
    preds, per_season, chosen = [], [], []
    for S in test_seasons:
        any_f = next(iter(feats.values()))
        train = eval_mask(any_f) & any_f["season"].between(first_train, S - 1)
        best = min(feats, key=lambda key: _train_score(feats[key], train, FULL))
        f = feats[best]
        train = eval_mask(f) & f["season"].between(first_train, S - 1)
        test = eval_mask(f) & (f["season"] == S)
        full = MarginModel(FULL).fit(f[train])
        # Elo-only baseline: pick its own Elo params (EPA params irrelevant, use grid entry 0)
        best_elo = min(range(len(ELO_GRID)), key=lambda i: _train_score(feats[(i, 0)], train, ELO_ONLY))
        elo_feats = feats[(best_elo, 0)]
        elo = MarginModel(ELO_ONLY).fit(elo_feats[train])
        msig = market_sigma(f[train])
        d = f[test].copy()
        de = elo_feats.set_index("game_id").loc[d["game_id"]]
        d["pred_margin"] = full.predict(d)
        d["pred_wp"] = full.win_prob(d["pred_margin"])
        d["elo_margin"] = elo.predict(de)
        d["elo_wp"] = elo.win_prob(d["elo_margin"])
        d["market_wp"] = norm.cdf(d["market_margin"] / msig)
        preds.append(d)
        row = {"season": int(S), "train_seasons": f"{first_train}-{S - 1}",
               "model": metrics(d["pred_margin"].to_numpy(), d["pred_wp"].to_numpy(), d),
               "elo_only": metrics(d["elo_margin"].to_numpy(), d["elo_wp"].to_numpy(), d),
               "market": metrics(d["market_margin"].to_numpy(), d["market_wp"].to_numpy(), d)}
        per_season.append(row)
        chosen.append({"season": int(S), "elo_params": asdict(ELO_GRID[best[0]]), "eff_params": asdict(EFF_GRID[best[1]]),
                       "margin_model": full.to_dict(), "elo_only_model": elo.to_dict(), "market_sigma": msig})
        log(f"  {S}: model MAE {row['model']['mae_vs_actual']:.2f} | Elo {row['elo_only']['mae_vs_actual']:.2f} | "
            f"market {row['market']['mae_vs_actual']:.2f} | ATS {row['model']['ats_wins']}-{row['model']['ats_losses']}")
    allp = pd.concat(preds, ignore_index=True)
    overall = {k: metrics(allp[m].to_numpy(), allp[w].to_numpy(), allp) for k, m, w in
               (("model", "pred_margin", "pred_wp"), ("elo_only", "elo_margin", "elo_wp"),
                ("market", "market_margin", "market_wp"))}
    outcome = (allp["margin"] > 0).to_numpy(dtype=float)
    return {
        "per_season": per_season, "overall": overall, "chosen_params": chosen,
        "calibration": {k: calibration(allp[w].to_numpy(), outcome) for k, w in
                        (("model", "pred_wp"), ("elo_only", "elo_wp"), ("market", "market_wp"))},
        "predictions": allp, "features": feats,
    }


def walk_forward_adjusted(bt: dict, games: pd.DataFrame, adv: pd.DataFrame, ctx: pd.DataFrame,
                          box: pd.DataFrame, wx: pd.DataFrame, log=print) -> dict:
    """Second stage: totals model + adjustments layer, each fitted on earlier seasons only.

    Margin/weather adjustments for season S are fitted on the out-of-sample residuals of
    seasons before S (so the first test season gets no adjustments).
    """
    from model.adjustments import MARGIN_ADJ, TOTAL_ADJ, ResidualFit
    from model.context_features import add_context
    from model.margin import TotalModel

    seasons = sorted(games["season"].unique())
    first_train = seasons[BURN_IN]
    frames, totals_models = [], {}
    for cp in bt["chosen_params"]:
        S = cp["season"]
        eff = EffParams(**cp["eff_params"])
        key = (ELO_GRID.index(EloParams(**cp["elo_params"])), EFF_GRID.index(eff))
        f = add_context(bt["features"][key], games, adv, ctx, box, wx, eff)
        tm = TotalModel().fit(f[eval_mask(f) & f["season"].between(first_train, S - 1)])
        totals_models[S] = tm
        test = f[eval_mask(f) & (f["season"] == S)].copy()
        test["pred_total"] = tm.predict(test)
        frames.append(test)
    allf = pd.concat(frames, ignore_index=True)
    allf = allf.merge(bt["predictions"][["game_id", "pred_margin", "pred_wp", "elo_margin", "elo_wp", "market_wp"]],
                      on="game_id")
    allf["actual_total"] = allf["home_pts"].astype(float) + allf["away_pts"].astype(float)
    allf["resid_margin"] = allf["margin"] - allf["pred_margin"]
    allf["resid_total"] = allf["actual_total"] - allf["pred_total"]

    per_season, fits = [], []
    out = []
    for cp in bt["chosen_params"]:
        S = cp["season"]
        prior = allf[allf["season"] < S]
        mf = ResidualFit([a.key for a in MARGIN_ADJ]).fit(prior, "resid_margin")
        tf = ResidualFit([a.key for a in TOTAL_ADJ]).fit(prior, "resid_total")
        d = allf[allf["season"] == S].copy()
        d["adj_margin"] = d["pred_margin"] + mf.contributions(d).sum(axis=1)
        d["adj_total"] = d["pred_total"] + tf.contributions(d).sum(axis=1)
        sigma = cp["margin_model"]["sigma"]
        d["adj_wp"] = norm.cdf(d["adj_margin"] / sigma)
        out.append(d)
        fits.append({"season": int(S), "fitted_on": f"{first_train + 1}-{S - 1}" if len(prior) else "none",
                     "margin": mf.to_dict(MARGIN_ADJ), "total": tf.to_dict(TOTAL_ADJ),
                     "margin_const": mf.const, "total_const": tf.const, "totals_model": totals_models[S].to_dict()})
        per_season.append({"season": int(S),
                           "model_adjusted": metrics(d["adj_margin"].to_numpy(), d["adj_wp"].to_numpy(), d),
                           "totals": totals_metrics(d)})
        log(f"  {S}: adjusted MAE {per_season[-1]['model_adjusted']['mae_vs_actual']:.2f} | "
            f"total MAE {per_season[-1]['totals']['model_mae']:.2f} (adj {per_season[-1]['totals']['adjusted_mae']:.2f}, "
            f"market {per_season[-1]['totals']['market_mae']:.2f})")
    res = pd.concat(out, ignore_index=True)
    outcome = (res["margin"] > 0).to_numpy(dtype=float)
    return {"per_season": per_season, "fits": fits, "predictions": res,
            "overall": {"model_adjusted": metrics(res["adj_margin"].to_numpy(), res["adj_wp"].to_numpy(), res),
                        "totals": totals_metrics(res)},
            "calibration_adjusted": calibration(res["adj_wp"].to_numpy(), outcome),
            "resid_corr": float(np.corrcoef(res["resid_margin"], res["resid_total"])[0, 1]),
            "totals_models": totals_models}


def totals_metrics(d: pd.DataFrame) -> dict:
    m = d.dropna(subset=["total"])
    return {"games": int(len(d)),
            "model_mae": float(np.mean(np.abs(d["pred_total"] - d["actual_total"]))),
            "adjusted_mae": float(np.mean(np.abs(d["adj_total"] - d["actual_total"]))) if "adj_total" in d else None,
            "market_mae": float(np.mean(np.abs(m["total"] - m["actual_total"]))) if len(m) else None,
            "market_games": int(len(m))}
