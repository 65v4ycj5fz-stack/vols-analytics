"""Pregame features with no lookahead.

Every feature for a game is computed only from games that *started before it*:

* Elo: sequential by construction (``run_elo`` records the pregame rating).
* Opponent-adjusted EPA: for each (season, week) we refit the ridge model on that
  season's earlier games and blend it with last season's final rating (regressed
  toward average), weighted by games played. Week 1 uses the prior alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from model.ratings import AdjParams, EloParams, adjusted_efficiency, run_elo


@dataclass(frozen=True)
class EffParams:
    alpha: float = 2.0          # ridge penalty for the in-season fit
    prior_games: float = 4.0    # last season's rating counts as this many games
    prior_keep: float = 0.5     # share of last season's rating carried over (rest regresses to 0)
    half_life: float | None = None  # weeks; None = every earlier game counts equally


def team_game_rows(games: pd.DataFrame, adv: pd.DataFrame) -> pd.DataFrame:
    """Two rows per completed game (one per offense) with site and offensive EPA/play."""
    done = games[games["completed"]]
    rows = []
    for side, opp, site_home in (("home", "away", "home"), ("away", "home", "away")):
        rows.append(pd.DataFrame({
            "game_id": done["game_id"], "season": done["season"], "week": done["week"],
            "season_type": done["season_type"], "start_date": done["start_date"],
            "team": done[f"{side}_team"], "opponent": done[f"{opp}_team"],
            "site": np.where(done["neutral_site"], "neutral", site_home),
        }))
    tg = pd.concat(rows, ignore_index=True)
    return tg.merge(adv[["game_id", "team", "off_epa", "off_plays"]], on=["game_id", "team"], how="left")


def _slots(games: pd.DataFrame) -> pd.DataFrame:
    """Ordered (season, slot) feature checkpoints; postseason comes after the last regular week."""
    s = games[["season", "season_type", "week"]].drop_duplicates()
    s["slot"] = np.where(s["season_type"] == "postseason", 100 + s["week"], s["week"])
    s = s.sort_values(["season", "slot"])
    s["slot"] = s.groupby("season").cumcount()  # ordinal, so recency decay counts game-weeks
    return s


def adjusted_pregame(games: pd.DataFrame, adv: pd.DataFrame, p: EffParams = EffParams()) -> pd.DataFrame:
    """Return per (game_id, team) pregame adj_off / adj_def (EPA/play vs average) and games used."""
    tg = team_game_rows(games, adv)
    slots = _slots(games)
    tg_slot = tg.merge(slots, on=["season", "season_type", "week"])
    g_slot = games.merge(slots, on=["season", "season_type", "week"])
    out, prior = [], pd.DataFrame(columns=["team", "adj_off", "adj_def"]).set_index("team")
    for season, sl in slots.groupby("season", sort=True):
        for slot in sl["slot"]:
            past = tg_slot[(tg_slot["season"] == season) & (tg_slot["slot"] < slot)]
            if p.half_life:
                past = past.assign(decay=0.5 ** ((slot - past["slot"].clip(upper=slot - 1)) / p.half_life))
            cur, _ = adjusted_efficiency(past, "off_epa", AdjParams(alpha=p.alpha))
            cur = cur.set_index("team")
            here = g_slot[(g_slot["season"] == season) & (g_slot["slot"] == slot)]
            teams = pd.unique(pd.concat([here["home_team"], here["away_team"]]))
            r = pd.DataFrame(index=pd.Index(teams, name="team"))
            n = cur["games"].reindex(r.index).fillna(0)
            for col in ("adj_off", "adj_def"):
                pri = prior[col].reindex(r.index).fillna(0) * p.prior_keep if len(prior) else 0.0
                c = cur[col].reindex(r.index).fillna(0)
                r[col] = (n * c + p.prior_games * pri) / (n + p.prior_games)
            r["games_in_season"] = n
            for side in ("home", "away"):
                sub = here[["game_id", f"{side}_team"]].rename(columns={f"{side}_team": "team"})
                out.append(sub.join(r, on="team"))
        full, _ = adjusted_efficiency(tg_slot[tg_slot["season"] == season], "off_epa", AdjParams(alpha=p.alpha))
        prior = full.set_index("team")
    return pd.concat(out, ignore_index=True).drop_duplicates(["game_id", "team"])


def game_features(games: pd.DataFrame, adv: pd.DataFrame, elo_p: EloParams = EloParams(),
                  eff_p: EffParams = EffParams()) -> pd.DataFrame:
    """One row per game with pregame features from the home team's perspective."""
    elo_games, _ = run_elo(games, elo_p)
    adj = adjusted_pregame(games, adv, eff_p).set_index(["game_id", "team"])
    f = elo_games.copy()
    for side in ("home", "away"):
        a = adj.reindex(pd.MultiIndex.from_arrays([f["game_id"], f[f"{side}_team"]]))
        f[f"{side}_adj_off"] = a["adj_off"].to_numpy(dtype=float)
        f[f"{side}_adj_def"] = a["adj_def"].to_numpy(dtype=float)
        f[f"{side}_games_in_season"] = a["games_in_season"].to_numpy(dtype=float)
    f["site_home"] = np.where(f["neutral_site"], 0.0, 1.0)
    f["elo_diff"] = f["home_elo_pre"] - f["away_elo_pre"]
    # expected EPA/play edge: home offense vs away defense minus away offense vs home defense
    f["epa_diff"] = (f["home_adj_off"] + f["away_adj_def"]) - (f["away_adj_off"] + f["home_adj_def"])
    f["margin"] = f["home_pts"].astype(float) - f["away_pts"].astype(float)
    f["market_margin"] = -f["spread_home"]
    return f
