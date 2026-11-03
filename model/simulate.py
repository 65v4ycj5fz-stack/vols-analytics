"""Monte Carlo simulation of games and the rest of the season.

Game: (margin, total) drawn from a bivariate normal using the model's error SDs and
their historical correlation; team points = (total +/- margin) / 2, rounded, floored at 0.
Ties go to a simplified overtime (winner drawn from the win probability, +7 points).

Season: each team gets one strength shock per simulation (SD ``tau``, the typical
season-level rating error) shared across its remaining games, so outcomes are correlated
the way they are in reality (if a team is better than rated, it shows up every week).
Per-game noise is shrunk so each single game still has the model's total error SD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

N_SIMS = 10_000
SEED = 20261102


def simulate_game(margin: float, total: float, sigma_m: float, sigma_t: float, rho: float,
                  n: int = N_SIMS, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    cov = [[sigma_m ** 2, rho * sigma_m * sigma_t], [rho * sigma_m * sigma_t, sigma_t ** 2]]
    m, t = rng.multivariate_normal([margin, total], cov, size=n).T
    t = np.maximum(t, np.abs(m))  # a total can't be smaller than the margin
    a = np.maximum(np.rint((t + m) / 2), 0)
    b = np.maximum(np.rint((t - m) / 2), 0)
    ties = a == b
    ot_a = rng.random(n) < norm.cdf(margin / sigma_m)
    a = a + np.where(ties & ot_a, 7, 0)
    b = b + np.where(ties & ~ot_a, 7, 0)
    sim_margin = a - b
    return {"a": a, "b": b, "margin": sim_margin, "n": n, "seed": seed}


def summarize_game(sim: dict, market_spread: float | None) -> dict:
    a, b, m = sim["a"], sim["b"], sim["margin"]
    out = {
        "n_sims": sim["n"], "seed": sim["seed"],
        "win_prob": float((m > 0).mean()),
        "team_points": _dist(a), "opp_points": _dist(b), "margin": _dist(m),
        "margin_hist": _hist(m, -60, 60), "team_points_hist": _hist(a, 0, 80), "opp_points_hist": _hist(b, 0, 80),
        "most_likely_scores": _top_scores(a, b),
        "p_win_by_8_plus": float((m >= 8).mean()), "p_lose_by_8_plus": float((m <= -8).mean()),
        "p_one_score_game": float((np.abs(m) <= 8).mean()),
    }
    if market_spread is not None and not np.isnan(market_spread):
        # backtesting context only: share of simulations where the team beats the closing spread
        out["cover_prob_vs_market"] = float((m + market_spread > 0).mean())
        out["push_prob_vs_market"] = float((m + market_spread == 0).mean())
    return out


def _dist(x: np.ndarray) -> dict:
    q = np.percentile(x, [10, 25, 50, 75, 90])
    return {"mean": float(x.mean()), "p10": float(q[0]), "p25": float(q[1]), "median": float(q[2]),
            "p75": float(q[3]), "p90": float(q[4])}


def _hist(x: np.ndarray, lo: int, hi: int) -> list[dict]:
    clipped = np.clip(x, lo, hi).astype(int)
    vals, counts = np.unique(clipped, return_counts=True)
    return [{"value": int(v), "share": float(c / len(x))} for v, c in zip(vals, counts)]


def _top_scores(a: np.ndarray, b: np.ndarray, k: int = 5) -> list[dict]:
    s = pd.Series(list(zip(a.astype(int), b.astype(int)))).value_counts(normalize=True).head(k)
    return [{"team": int(x[0]), "opp": int(x[1]), "share": float(v)} for x, v in s.items()]


def estimate_tau(preds: pd.DataFrame, sigma: float) -> float:
    """Season-level rating error SD from out-of-sample residuals.

    For each team-season, average the residual from that team's perspective. Its variance is
    roughly tau^2 + sigma^2 / n_games, so tau^2 ~ var(mean residual) - mean(sigma^2 / n).
    """
    rows = pd.concat([
        pd.DataFrame({"team": preds["home_team"], "season": preds["season"], "r": preds["resid_margin"]}),
        pd.DataFrame({"team": preds["away_team"], "season": preds["season"], "r": -preds["resid_margin"]}),
    ])
    g = rows.groupby(["team", "season"])["r"].agg(["mean", "size"])
    g = g[g["size"] >= 6]
    tau2 = g["mean"].var() - float(np.mean(sigma ** 2 / g["size"]))
    return float(np.sqrt(max(tau2, 0.0)))


def simulate_season(games: pd.DataFrame, sigma: float, tau: float, n: int = N_SIMS, seed: int = SEED) -> np.ndarray:
    """Simulate remaining games. ``games`` has home_team, away_team, margin (home, predicted).

    Returns a (n, len(games)) boolean array: True where the home team wins.
    """
    rng = np.random.default_rng(seed)
    teams = pd.unique(pd.concat([games["home_team"], games["away_team"]]))
    idx = {t: i for i, t in enumerate(teams)}
    shocks = rng.normal(0, tau, size=(n, len(teams)))
    h = games["home_team"].map(idx).to_numpy()
    a = games["away_team"].map(idx).to_numpy()
    noise_sd = np.sqrt(max(sigma ** 2 - 2 * tau ** 2, 1.0))
    draws = games["margin"].to_numpy()[None, :] + shocks[:, h] - shocks[:, a] + rng.normal(0, noise_sd, (n, len(games)))
    ties = draws == 0
    draws[ties] = rng.choice([-1, 1], size=ties.sum())
    return draws > 0


def season_outlook(remaining: pd.DataFrame, current_wins: int, current_losses: int, team: str,
                   conf_remaining: pd.DataFrame, conf_standings: pd.DataFrame, sigma: float, tau: float,
                   n: int = N_SIMS, seed: int = SEED) -> dict:
    """Win-total and conference-finish distributions for ``team``.

    ``conf_remaining``: all remaining conference games (home_team, away_team, margin, conf flag).
    ``conf_standings``: current conference wins/losses per team.
    """
    all_rem = pd.concat([remaining, conf_remaining]).drop_duplicates("game_id").reset_index(drop=True)
    home_wins = simulate_season(all_rem, sigma, tau, n, seed)
    team_games = all_rem["game_id"].isin(set(remaining["game_id"])).to_numpy()
    is_home = (all_rem["home_team"] == team).to_numpy()
    team_win = np.where(is_home, home_wins, ~home_wins)[:, team_games]
    wins = current_wins + team_win.sum(axis=1)
    total_games = current_wins + current_losses + int(team_games.sum())

    out = {"n_sims": n, "seed": seed, "tau": tau, "games_remaining": int(team_games.sum()),
           "current_record": {"wins": current_wins, "losses": current_losses},
           "expected_wins": float(wins.mean()),
           "win_distribution": [{"wins": int(w), "prob": float((wins == w).mean())}
                                for w in range(current_wins, current_wins + int(team_games.sum()) + 1)],
           "p_at_least": {str(w): float((wins >= w).mean()) for w in range(6, total_games + 1)},
           "per_game": [{"game_id": int(g), "win_prob": float(p)} for g, p in
                        zip(all_rem.loc[team_games, "game_id"], team_win.mean(axis=0))]}

    conf_games = all_rem["conf"].fillna(False).astype(bool).to_numpy() if "conf" in all_rem else np.zeros(len(all_rem), bool)
    if conf_games.any() and not conf_standings.empty:
        teams = list(conf_standings["team"])
        cw = np.tile(conf_standings["wins"].to_numpy(dtype=float), (n, 1))
        cl = np.tile(conf_standings["losses"].to_numpy(dtype=float), (n, 1))
        ti = {t: i for i, t in enumerate(teams)}
        for j in np.flatnonzero(conf_games):
            h, a = all_rem.loc[j, "home_team"], all_rem.loc[j, "away_team"]
            if h not in ti or a not in ti:
                continue
            hw = home_wins[:, j]
            cw[:, ti[h]] += hw; cl[:, ti[h]] += ~hw
            cw[:, ti[a]] += ~hw; cl[:, ti[a]] += hw
        pct = cw / np.maximum(cw + cl, 1)
        rng = np.random.default_rng(seed + 1)
        order = np.argsort(-(pct + rng.random(pct.shape) * 1e-6), axis=1)  # random tiebreak (approximation)
        rank = np.empty_like(order)
        rank[np.arange(n)[:, None], order] = np.arange(len(teams))[None, :]
        me = ti.get(team)
        if me is not None:
            out["conference"] = {
                "current": {"wins": int(conf_standings.loc[conf_standings.team == team, "wins"].iloc[0]),
                            "losses": int(conf_standings.loc[conf_standings.team == team, "losses"].iloc[0])},
                "expected_conf_wins": float(cw[:, me].mean()),
                "conf_win_distribution": [{"wins": int(w), "prob": float((cw[:, me] == w).mean())}
                                          for w in np.unique(cw[:, me])],
                "p_top2_finish": float((rank[:, me] < 2).mean()),
                "p_first_place": float((rank[:, me] == 0).mean()),
                "tiebreak_note": "Ties in conference win % are broken at random; the real SEC tiebreakers "
                                 "(head-to-head, common opponents, etc.) are not modeled.",
                "standings_projection": [{"team": t, "expected_conf_wins": float(cw[:, i].mean()),
                                          "p_top2": float((rank[:, i] < 2).mean())} for t, i in ti.items()],
            }
    return out
