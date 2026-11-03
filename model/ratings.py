"""Self-computed team ratings.

* ``run_elo``: margin-aware Elo over every game in chronological order. Pregame
  ratings are recorded on each game so later backtests never see the result.
* ``adjusted_efficiency``: ridge regression of per-game offensive EPA/play on
  offense, defense and home-field indicators, which removes schedule strength.

Default parameters are documented starting points; Phase 3 fits them on history.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge


@dataclass(frozen=True)
class EloParams:
    k: float = 25.0
    home_field: float = 55.0          # Elo points; ~2 pts of spread at 25 Elo/pt
    fbs_start: float = 1500.0
    non_fbs_start: float = 1200.0
    season_regression: float = 1 / 3  # share pulled back toward the mean each offseason
    elo_per_point: float = 25.0       # converts an Elo gap into an expected margin


def elo_expected(diff: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + 10 ** (-np.asarray(diff) / 400.0))


def mov_multiplier(margin: float, winner_elo_diff: float) -> float:
    """FiveThirtyEight-style damping so blowouts by favorites don't over-inflate ratings."""
    return np.log(abs(margin) + 1.0) * (2.2 / (winner_elo_diff * 0.001 + 2.2))


def run_elo(games: pd.DataFrame, params: EloParams = EloParams()) -> tuple[pd.DataFrame, dict[str, float]]:
    """Return (games with pregame/postgame Elo columns, final ratings).

    ``games`` needs: game_id, season, start_date, completed, neutral_site, home_team,
    away_team, home_class, away_class, home_pts, away_pts.
    """
    g = games.sort_values(["start_date", "game_id"]).reset_index(drop=True)
    ratings: dict[str, float] = {}
    is_fbs: dict[str, bool] = {}
    season_seen: int | None = None
    pre_h, pre_a, post_h, post_a = (np.full(len(g), np.nan) for _ in range(4))

    def start(team: str, cls: str | None) -> float:
        fbs = cls == "fbs"
        is_fbs[team] = is_fbs.get(team, False) or fbs
        return params.fbs_start if fbs else params.non_fbs_start

    for i, row in enumerate(g.itertuples(index=False)):
        if row.season != season_seen:
            if season_seen is not None:
                for t, r in ratings.items():
                    mean = params.fbs_start if is_fbs.get(t) else params.non_fbs_start
                    ratings[t] = r + (mean - r) * params.season_regression
            season_seen = row.season
        h = ratings.setdefault(row.home_team, start(row.home_team, row.home_class))
        a = ratings.setdefault(row.away_team, start(row.away_team, row.away_class))
        pre_h[i], pre_a[i] = h, a
        if not row.completed or pd.isna(row.home_pts) or pd.isna(row.away_pts):
            continue
        hfa = 0.0 if row.neutral_site else params.home_field
        diff = h + hfa - a
        exp_h = elo_expected(diff)
        margin = float(row.home_pts) - float(row.away_pts)
        actual = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        winner_diff = diff if margin > 0 else -diff if margin < 0 else 0.0
        mult = mov_multiplier(margin, winner_diff) if margin != 0 else 1.0
        delta = params.k * mult * (actual - exp_h)
        ratings[row.home_team] = h + delta
        ratings[row.away_team] = a - delta
        post_h[i], post_a[i] = h + delta, a - delta

    g["home_elo_pre"], g["away_elo_pre"] = pre_h, pre_a
    g["home_elo_post"], g["away_elo_post"] = post_h, post_a
    return g, ratings


def elo_history(elo_games: pd.DataFrame, team: str) -> pd.DataFrame:
    """Postgame Elo after each of ``team``'s completed games."""
    h = elo_games[elo_games["home_team"] == team].assign(elo=lambda d: d["home_elo_post"], opponent=lambda d: d["away_team"])
    a = elo_games[elo_games["away_team"] == team].assign(elo=lambda d: d["away_elo_post"], opponent=lambda d: d["home_team"])
    out = pd.concat([h, a])
    out = out[out["elo"].notna()]
    return out[["game_id", "season", "week", "start_date", "opponent", "elo"]].sort_values("start_date")


@dataclass(frozen=True)
class AdjParams:
    alpha: float = 2.0  # ridge penalty (in units of plays-weighted games); shrinks toward average


def adjusted_efficiency(team_games: pd.DataFrame, metric: str = "off_epa",
                        params: AdjParams = AdjParams()) -> tuple[pd.DataFrame, float]:
    """Opponent-adjusted offense/defense for ``metric`` (e.g. EPA per play).

    ``team_games`` has one row per team-game with columns team, opponent, site
    (home/away/neutral), ``metric`` and off_plays (weights). Model:

        metric[o vs d] = intercept + off[o] + def[d] + hfa * home_indicator

    Returns (DataFrame team, adj_off, adj_def, games; home-field coefficient).
    ``adj_def`` is points/play *allowed* relative to average: lower is better.
    """
    d = team_games.dropna(subset=[metric]).copy()
    if d.empty:
        return pd.DataFrame(columns=["team", "adj_off", "adj_def", "games"]), float("nan")
    teams = sorted(set(d["team"]) | set(d["opponent"]))
    idx = {t: i for i, t in enumerate(teams)}
    n, k = len(d), len(teams)
    rows = np.arange(n)
    off_cols = d["team"].map(idx).to_numpy()
    def_cols = d["opponent"].map(idx).to_numpy() + k
    home = np.select([d["site"] == "home", d["site"] == "away"], [1.0, -1.0], 0.0)
    X = sparse.hstack([
        sparse.csr_matrix((np.ones(2 * n), (np.r_[rows, rows], np.r_[off_cols, def_cols])), shape=(n, 2 * k)),
        sparse.csr_matrix(home.reshape(-1, 1)),
    ]).tocsr()
    w = d["off_plays"].fillna(d["off_plays"].median()).to_numpy(dtype=float) if "off_plays" in d else np.ones(n)
    if "decay" in d:  # optional recency weight (1 = full weight)
        w = w * d["decay"].to_numpy(dtype=float)
    w = w / np.nanmean(w)
    model = Ridge(alpha=params.alpha, fit_intercept=True)
    model.fit(X, d[metric].to_numpy(dtype=float), sample_weight=w)
    coef = model.coef_
    games_played = d.groupby("team").size()
    out = pd.DataFrame({"team": teams, "adj_off": coef[:k], "adj_def": coef[k:2 * k]})
    out["games"] = out["team"].map(games_played).fillna(0).astype(int)
    # half the home/away contrast: one team's home edge vs a neutral site
    return out, float(coef[-1])
