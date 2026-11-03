"""Model entry point: ``python -m model.run`` (run after ``python -m pipeline.run``).

Runs the walk-forward backtest and writes backtest.json, model_params.json and
predictions.json (baseline margin + win probability for the team's remaining games).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict

import numpy as np
import pandas as pd

from model import projections as proj
from model.adjustments import (DEPTH_WEIGHT, DEPTH_WEIGHT_UNLISTED, POINTS_PER_IMPACT, STATUS_PROB_OUT,
                               load_manual)
from model.backtest import ATS_EDGE, EFF_GRID, ELO_GRID, walk_forward, walk_forward_adjusted
from model.context_features import add_context
from model.features import EffParams
from model.margin import FULL, MarginModel
from model.simulate import N_SIMS, estimate_tau
from pipeline import config
from pipeline.publish import write_dataset
from pipeline.transforms.games import fbs_games

FIRST_TEST_SEASON = 2021


def log(msg: str) -> None:
    print(f"[model] {msg}", flush=True)


def _sources(games: pd.DataFrame) -> list[dict]:
    return [{"source": "CollegeFootballData.com", "endpoint": "/games, /lines, /stats/game/advanced",
             "fetched_at": None},
            {"source": "derived", "endpoint": "data/processed/games.parquet",
             "fetched_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")}]


def team_view(f: pd.DataFrame, team: str, model: MarginModel) -> pd.DataFrame:
    """Rows for ``team``'s games with margin, win prob and contributions from the team's perspective."""
    g = f[(f["home_team"] == team) | (f["away_team"] == team)].copy()
    sign = np.where(g["home_team"] == team, 1.0, -1.0)
    home_pred = model.predict(g)
    lo, hi = model.interval(home_pred, 0.8)
    g["opponent"] = np.where(sign > 0, g["away_team"], g["home_team"])
    g["site"] = np.where(g["neutral_site"], "neutral", np.where(sign > 0, "home", "away"))
    g["pred_margin"] = sign * home_pred
    g["margin_p10"] = np.where(sign > 0, lo, -hi)
    g["margin_p90"] = np.where(sign > 0, hi, -lo)
    g["win_prob"] = model.win_prob(g["pred_margin"])
    g["market_spread"] = -sign * g["market_margin"]  # negative = team favored
    for k, v in model.coef.items():
        g[f"pts_from_{k}"] = sign * g[k].astype(float) * v
    g["team_elo"] = np.where(sign > 0, g["home_elo_pre"], g["away_elo_pre"])
    g["opp_elo"] = np.where(sign > 0, g["away_elo_pre"], g["home_elo_pre"])
    for col in ("adj_off", "adj_def", "games_in_season"):
        g[f"team_{col}"] = np.where(sign > 0, g[f"home_{col}"], g[f"away_{col}"])
        g[f"opp_{col}"] = np.where(sign > 0, g[f"away_{col}"], g[f"home_{col}"])
    g["actual_margin"] = sign * g["margin"]
    return g


def republish_elo(f: pd.DataFrame, team: str, season: int) -> None:
    """Make the published Elo (ratings + trend) use the Elo settings the backtest selected,
    so every page shows the same Elo the projections use."""
    from model.ratings import elo_history
    from pipeline.transforms.team_stats import Metric, add_ranks

    post = pd.concat([f[["home_team", "home_elo_post", "start_date"]].set_axis(["team", "elo", "t"], axis=1),
                      f[["away_team", "away_elo_post", "start_date"]].set_axis(["team", "elo", "t"], axis=1)])
    latest = post.dropna(subset=["elo"]).sort_values("t").groupby("team")["elo"].last()
    for name in ("ratings", "rating_trend"):
        path = config.PUBLIC_DATA / f"{name}.json"
        doc = json.loads(path.read_text())
        df = pd.DataFrame(doc["data"])
        if name == "ratings":
            df["elo"] = df["team"].map(latest)
            df = add_ranks(df.drop(columns=["elo_rank", "elo_conf_rank"], errors="ignore"),
                           [Metric("elo", "Elo (ours)", "Elo", True, "overall", "")])
        else:
            hist = elo_history(f[f["season"] == season], team).set_index("game_id")["elo"]
            df["elo"] = df["game_id"].map(hist)
        notes = [n for n in doc["meta"]["notes"] if "Elo and adjustment parameters" not in n]
        notes.append("Elo uses the settings selected by the walk-forward backtest (see model_params.json).")
        write_dataset(name, df, sources=doc["meta"]["sources"], season=doc["meta"]["season"],
                      description=doc["meta"]["description"], notes=notes)


def build() -> None:
    t0 = time.time()
    team, season = config.TEAM, config.SEASON
    games = fbs_games(pd.read_parquet(config.PROCESSED / "games.parquet"))
    adv = pd.read_parquet(config.PROCESSED / "adv_games.parquet")
    test_seasons = [s for s in range(FIRST_TEST_SEASON, season + 1) if s in set(games["season"])]
    log(f"walk-forward backtest over {test_seasons} "
        f"({len(ELO_GRID)} Elo x {len(EFF_GRID)} efficiency settings, chosen per season from prior seasons only)")
    bt = walk_forward(games, adv, test_seasons, log=lambda m: None if "grid" in m else log(m))
    P = config.PROCESSED
    ctx, box = pd.read_parquet(P / "game_context.parquet"), pd.read_parquet(P / "box_games.parquet")
    wx = pd.read_parquet(P / "weather.parquet")
    log("second stage: totals model + adjustments (each fitted on earlier seasons only)")
    adj = walk_forward_adjusted(bt, games, adv, ctx, box, wx, log=log)
    src = _sources(games)

    ov = bt["overall"]
    beats_market = ov["model"]["mae_vs_actual"] < ov["market"]["mae_vs_actual"]
    headline = (
        f"Out of sample ({ov['model']['games']:,} FBS games, {test_seasons[0]}-{test_seasons[-1]}), the model's "
        f"average miss is {ov['model']['mae_vs_actual']:.1f} pts vs {ov['elo_only']['mae_vs_actual']:.1f} for Elo alone "
        f"and {ov['market']['mae_vs_actual']:.1f} for the closing spread. "
        + ("It beats the market." if beats_market else
           "It does NOT beat the market: closing spreads are more accurate, and the model's picks against "
           f"the spread went {ov['model']['ats_wins']}-{ov['model']['ats_losses']} "
           f"({ov['model']['ats_win_pct']:.1%}), i.e. no demonstrated edge."))
    write_dataset("backtest", {
        "headline": headline, "beats_market": beats_market, "test_seasons": test_seasons,
        "overall": ov, "per_season": bt["per_season"], "calibration": bt["calibration"],
        "chosen_params": bt["chosen_params"], "ats_edge_threshold": ATS_EDGE,
        "model_adjusted": {"overall": adj["overall"]["model_adjusted"],
                           "per_season": [{"season": x["season"], **x["model_adjusted"]} for x in adj["per_season"]],
                           "calibration": adj["calibration_adjusted"]},
        "totals": {"overall": adj["overall"]["totals"],
                   "per_season": [{"season": x["season"], **x["totals"]} for x in adj["per_season"]]},
        "adjustment_fits": adj["fits"], "margin_total_resid_corr": adj["resid_corr"],
        "grids": {"elo": [asdict(p) for p in ELO_GRID], "efficiency": [asdict(p) for p in EFF_GRID]},
    }, sources=src, season=season, csv=False,
        description="Walk-forward backtest: margin error, win-probability calibration and comparison with "
                    "an Elo-only baseline and the closing spread.",
        notes=["Each season is predicted using only data from before each game; settings are chosen using "
               "earlier seasons only. 2019-2020 are warm-up/training only.",
               "Evaluated on FBS-vs-FBS games with a closing line (median across books listed by CFBD).",
               "Market win probability = normal CDF of the closing spread / its historical error SD.",
               "Spreads are used here only to measure accuracy; this site has no wagering features.",
               "model_adjusted = baseline + fitted adjustments (rest, travel, turnovers, recent form); "
               "adjustments for season S are fitted on earlier seasons' out-of-sample residuals.",
               "Totals: projected combined points vs the actual total and vs the closing total."])

    preds = bt["predictions"]
    cols = ["game_id", "season", "week", "season_type", "start_date", "home_team", "away_team", "neutral_site",
            "margin", "market_margin", "pred_margin", "pred_wp", "elo_margin", "elo_wp", "market_wp"]
    write_dataset("backtest_games", preds[cols], sources=src, season=season, json_out=False,
                  description="Every backtested game: pregame model/Elo/market predictions vs the result "
                              "(home-team perspective).")

    # final model for live predictions = the one chosen for the current season (trained on prior seasons)
    final = bt["chosen_params"][-1]
    key = (ELO_GRID.index(next(p for p in ELO_GRID if asdict(p) == final["elo_params"])),
           EFF_GRID.index(next(p for p in EFF_GRID if asdict(p) == final["eff_params"])))
    f = bt["features"][key]
    model = MarginModel(FULL)
    model.coef, model.stderr = final["margin_model"]["coef"], final["margin_model"]["stderr"]
    model.sigma, model.n_train = final["margin_model"]["sigma"], final["margin_model"]["n_train"]
    write_dataset("model_params", {
        **final, "home_field_points": model.coef["site_home"],
        "home_field_points_se": model.stderr["site_home"],
        "points_per_100_elo": model.coef["elo_diff"] * 100,
        "points_per_0_1_epa_edge": model.coef["epa_diff"] * 0.1,
    }, sources=src, season=season, csv=False,
        description="Parameters of the live model (trained on seasons before the current one).")

    tv = team_view(f[f["season"] == season], team, model)
    keep = ["game_id", "week", "start_date", "opponent", "site", "completed", "pred_margin", "margin_p10",
            "margin_p90", "win_prob", "market_spread", "actual_margin", "team_elo", "opp_elo", "team_adj_off",
            "team_adj_def", "opp_adj_off", "opp_adj_def", "team_games_in_season", "opp_games_in_season"] + \
           [f"pts_from_{k}" for k in model.coef]
    write_dataset("predictions", tv[keep], sources=src, season=season,
                  description=f"Baseline pregame projection for every {team} {season} game "
                              f"(completed games show what the model said beforehand).",
                  notes=[f"80% interval = predicted margin +/- 1.28 x {model.sigma:.1f} pts (historical error SD).",
                         "pred_margin and market_spread use opposite sign conventions: +7 margin ~ -7 spread.",
                         "Baseline only; projections.json adds adjustments, score projection and simulation."])

    # ---- Phase 4: live projections with adjustments + simulation ----
    eff = EffParams(**final["eff_params"])
    fc = add_context(f, games, adv, ctx, box, wx, eff)
    fit = adj["fits"][-1]
    totals_model = adj["totals_models"][season]
    hist = adj["predictions"][adj["predictions"]["season"] < season]
    tau = estimate_tau(hist, model.sigma)
    # validated copies written by the pipeline (local file or Google Sheet)
    injuries = load_manual(P / "manual" / "injuries.csv")
    depth = load_manual(P / "manual" / "depth_chart.csv")
    est = load_manual(P / "manual" / "depth_chart_estimated.csv")
    if len(est):  # estimated depth fills in only for teams with no manual depth chart
        manual_teams = set(depth["team"]) if len(depth) else set()
        depth = pd.concat([depth, est[~est["team"].isin(manual_teams)][["team", "player", "string"]]], ignore_index=True)
    splits = proj.split_ratings(adv, games, P / f"plays_{season}.parquet")
    sched = pd.DataFrame(json.loads((config.PUBLIC_DATA / "schedule.json").read_text())["data"])
    projections, outlook = proj.build(fc, model, totals_model, fit, adj["resid_corr"], tau, injuries, depth,
                                      splits, proj.load_tendencies(), sched)
    common = {"sigma_margin": model.sigma, "sigma_total": totals_model.sigma, "rho": adj["resid_corr"],
              "n_sims": N_SIMS, "margin_coef": model.coef, "totals_coef": totals_model.coef,
              "points_per_impact": POINTS_PER_IMPACT}
    wx_src = [{"source": "Open-Meteo.com (CC BY 4.0)", "endpoint": "archive + forecast",
               "fetched_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")}]
    write_dataset("projections", {"games": projections, "model": common}, sources=src + wx_src, season=season,
                  csv=False, description=f"{team} {season} game projections: baseline, adjustments, projected "
                                         "score, 10,000-game simulation and plain-English factors.",
                  notes=["Factors add up to the projected margin; rush/pass 'split edges' are descriptive and "
                         "already inside the EPA factors.",
                         "Completed games show the pregame projection next to the result.",
                         "cover_prob_vs_market is shown for model evaluation only."])
    flat = pd.DataFrame([{
        "game_id": p["game_id"], "week": p["week"], "start_date": p["start_date"], "opponent": p["opponent"],
        "site": p["site"], "completed": p["completed"], "proj_team_points": p["projection"]["team_points"],
        "proj_opp_points": p["projection"]["opp_points"], "proj_margin": p["projection"]["margin"],
        "margin_p10": p["projection"]["margin_p10"], "margin_p90": p["projection"]["margin_p90"],
        "win_prob": p["projection"]["win_prob"], "baseline_margin": p["baseline"]["margin"],
        "adjustments_pts": sum(a["points"] for a in p["adjustments"]), "market_spread": p["market"]["spread"],
        "actual_margin": p["actual"]["margin"] if p["actual"] else None} for p in projections])
    write_dataset("projections_table", flat, sources=src, season=season,
                  description=f"Flat table of {team} projections (for spreadsheets).")
    write_dataset("season_outlook", outlook, sources=src, season=season, csv=False,
                  description=f"{team} win-total distribution and {config.CONFERENCE} finish from "
                              f"{N_SIMS:,} simulated seasons.")
    pd.DataFrame(outlook["win_distribution"]).to_csv(config.PUBLIC_CSV / "season_win_distribution.csv", index=False)
    write_dataset("adjustments_model", {"live": fit, "history": adj["fits"],
                                        "injury_assumptions": {"points_per_impact": POINTS_PER_IMPACT,
                                                               "status_prob_out": STATUS_PROB_OUT,
                                                               "depth_weight": {**{str(k): v for k, v in DEPTH_WEIGHT.items()},
                                                                                "unlisted": DEPTH_WEIGHT_UNLISTED}}},
                  sources=src, season=season, csv=False,
                  description="Fitted adjustment coefficients (with standard errors) and manual injury assumptions.")
    republish_elo(f, team, season)
    exp = outlook["expected_wins"]
    log(f"projections: {len(projections)} games; expected wins {exp:.2f}; tau {tau:.2f}")
    log(f"done in {time.time() - t0:.1f}s")


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
