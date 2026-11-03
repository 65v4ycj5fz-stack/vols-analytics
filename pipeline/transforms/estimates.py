"""Estimates derived from box-score stats when no manual entry exists.

* Estimated depth chart: players ranked within each position group by recent usage.
  This is a model estimate, not a team release. It can't see snaps, so the offensive line
  (no individual stats) is omitted, and CB vs S can't be separated (CFBD lists "DB").
* Absence alerts: regular contributors with no recorded stats in the latest game. This is
  an absence signal, not an injury report (benchings, game script and missing box-score
  lines look the same).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RECENT_GAMES = 3

# position group, CFBD positions, ranking stat expression, number of starters, backups shown
RULES: list[tuple[str, str, list[str], str, int, int]] = [
    ("offense", "QB", ["QB"], "passing_att", 1, 1),
    ("offense", "RB", ["RB"], "rushing_car", 1, 1),
    ("offense", "WR", ["WR"], "receiving_rec", 3, 2),
    ("offense", "TE", ["TE"], "receiving_rec", 1, 1),
    ("defense", "DL", ["DL", "DE", "DT", "NT", "EDGE"], "def_score", 4, 2),
    ("defense", "LB", ["LB", "OLB", "ILB"], "def_score", 2, 2),
    ("defense", "DB", ["DB", "CB", "S", "FS", "SS"], "def_score", 5, 2),
    ("special teams", "K", ["PK", "K"], "kick_att", 1, 0),
    ("special teams", "P", ["P"], "punting_no", 1, 0),
]
BASIS = {
    "passing_att": "pass attempts", "rushing_car": "carries", "receiving_rec": "receptions",
    "def_score": "tackles + 2x(TFL + sacks) + PBUs", "kick_att": "FG + XP attempts", "punting_no": "punts",
}


def _col(df: pd.DataFrame, c: str) -> pd.Series:
    return pd.to_numeric(df[c], errors="coerce").fillna(0) if c in df else pd.Series(0.0, index=df.index)


def _scores(df: pd.DataFrame, fg_att: str, xp_att: str) -> pd.DataFrame:
    df = df.copy()
    df["def_score"] = (_col(df, "defensive_tot") + 2 * (_col(df, "defensive_tfl") + _col(df, "defensive_sacks"))
                       + _col(df, "defensive_pd"))
    df["kick_att"] = _col(df, fg_att) + _col(df, xp_att)
    for c in ("passing_att", "rushing_car", "receiving_rec", "punting_no"):
        df[c] = _col(df, c)
    return df


def estimated_depth(usage: pd.DataFrame, team: str, basis_note: str, as_of: str) -> list[dict]:
    """``usage``: one row per player with player, position, jersey and the ranking stats."""
    rows = []
    for group, label, positions, stat, n_start, n_back in RULES:
        pool = usage[usage["position"].isin(positions) & (usage[stat] > 0)].sort_values(stat, ascending=False)
        for i, r in enumerate(pool.head(n_start + n_back).itertuples(index=False)):
            rows.append({
                "team": team, "position_group": group, "position": label,
                "string": 1 if i < n_start else 2, "player": r.player,
                "jersey": None if pd.isna(getattr(r, "jersey", np.nan)) else int(r.jersey),
                "rank_in_group": i + 1, "ranking_stat": BASIS[stat], "ranking_value": float(getattr(r, stat)),
                "basis": basis_note, "last_updated": as_of, "source": "estimate from CFBD box scores",
            })
    return rows


def tennessee_usage(logs: pd.DataFrame, roster: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Usage over the team's last RECENT_GAMES games, with roster positions and jerseys."""
    weeks = sorted(logs["week"].dropna().unique())[-RECENT_GAMES:]
    recent = _scores(logs[logs["week"].isin(weeks)], "kicking_fg_att", "kicking_xp_att")
    stats = ["passing_att", "rushing_car", "receiving_rec", "def_score", "kick_att", "punting_no"]
    agg = recent.groupby(["player_id", "player"])[stats].sum().reset_index()
    agg = agg.merge(roster[["player_id", "position", "jersey"]], on="player_id", how="left")
    note = f"ranked by usage over the last {len(weeks)} games (weeks {', '.join(str(int(w)) for w in weeks)})"
    return agg, note


def season_usage(stats: pd.DataFrame, team: str) -> tuple[pd.DataFrame, str]:
    s = _scores(stats[stats["team"] == team], "kicking_fga", "kicking_xpa")
    s["jersey"] = np.nan
    return s, "ranked by season-total usage (per-game logs are only pulled for Tennessee)"


def absence_alerts(logs: pd.DataFrame, roster: pd.DataFrame, team: str, min_games: int = 3,
                   min_share: float = 0.6, min_involvement: float = 2.0) -> pd.DataFrame:
    """Regular contributors with no stat line in the most recent game(s)."""
    cols = ["team", "player", "position", "games_with_stats", "team_games", "avg_involvement",
            "last_week_with_stats", "consecutive_games_missing", "note"]
    if logs.empty:
        return pd.DataFrame(columns=cols)
    weeks = sorted(logs["week"].dropna().unique())
    latest = weeks[-1]
    df = _scores(logs, "kicking_fg_att", "kicking_xp_att")
    df["involvement"] = df["passing_att"] / 5 + df["rushing_car"] + df["receiving_rec"] + _col(df, "defensive_tot")
    out = []
    for (pid, name), g in df.groupby(["player_id", "player"]):
        prior = g[g["week"] < latest]
        played_weeks = set(g["week"])
        prior_weeks = [w for w in weeks if w < latest]
        if len(prior) < min_games or len(prior) / max(len(prior_weeks), 1) < min_share:
            continue
        if prior["involvement"].mean() < min_involvement or latest in played_weeks:
            continue
        missing = 0
        for w in reversed(weeks):
            if w in played_weeks:
                break
            missing += 1
        pos = roster.loc[roster["player_id"] == pid, "position"]
        out.append({"team": team, "player": name, "position": pos.iloc[0] if len(pos) else None,
                    "games_with_stats": int(len(prior)), "team_games": int(len(prior_weeks)),
                    "avg_involvement": float(prior["involvement"].mean()),
                    "last_week_with_stats": int(max(played_weeks)), "consecutive_games_missing": missing,
                    "note": "No stats recorded in the latest game. Not an injury report: could be injury, "
                            "a coaching decision, or simply no stat-producing plays."})
    return pd.DataFrame(out, columns=cols).sort_values("avg_involvement", ascending=False) if out else pd.DataFrame(columns=cols)
