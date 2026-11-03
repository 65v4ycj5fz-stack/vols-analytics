"""Player tables: season stats (wide), usage, game logs and roster."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from pipeline.schemas import PlayerGameRaw, PlayerSeasonStatRaw, PlayerUsageRaw, RosterRaw


def _num(s: str) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return np.nan


def _col(category: str, stat: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{category}_{stat}".lower()).strip("_")


def season_stats(rows: list[PlayerSeasonStatRaw], teams: set[str] | None = None) -> pd.DataFrame:
    """One row per player; columns like passing_yds, rushing_car, defensive_tfl."""
    df = pd.DataFrame([{
        "player_id": r.playerId, "player": r.player, "position": r.position, "team": r.team,
        "conference": r.conference, "col": _col(r.category, r.statType), "value": _num(r.stat),
    } for r in rows if teams is None or r.team in teams])
    if df.empty:
        return df
    keys = ["player_id", "player", "position", "team", "conference"]
    df[keys] = df[keys].fillna("")  # pivot_table silently drops rows with a missing index value
    wide = df.pivot_table(index=keys, columns="col", values="value", aggfunc="first").reset_index()
    wide.columns.name = None
    return wide.sort_values(["team", "player"]).reset_index(drop=True)


def usage(rows: list[PlayerUsageRaw], teams: set[str] | None = None) -> pd.DataFrame:
    return pd.DataFrame([{
        "player_id": r.id, "player": r.name, "position": r.position, "team": r.team,
        "usage_overall": r.usage.overall, "usage_pass": r.usage.pass_, "usage_rush": r.usage.rush,
        "usage_first_down": r.usage.firstDown, "usage_second_down": r.usage.secondDown,
        "usage_third_down": r.usage.thirdDown, "usage_standard_downs": r.usage.standardDowns,
        "usage_passing_downs": r.usage.passingDowns,
    } for r in rows if teams is None or r.team in teams])


def _split_made_att(col: str, val: str) -> dict[str, float]:
    """'C/ATT' -> completions + attempts; 'XP'/'FG' '3/4' -> made + att."""
    if "/" in val:
        a, b = val.split("/", 1)
        base = col.removesuffix("_c_att").removesuffix("_xp").removesuffix("_fg")
        kind = "comp" if col.endswith("c_att") else col.rsplit("_", 1)[-1]
        if kind == "comp":
            return {f"{base}_comp": _num(a), f"{base}_att": _num(b)}
        return {f"{base}_{kind}_made": _num(a), f"{base}_{kind}_att": _num(b)}
    return {col: _num(val)}


def game_logs(rows: list[PlayerGameRaw], team: str, games: pd.DataFrame) -> pd.DataFrame:
    """One row per player per game for ``team``."""
    recs: dict[tuple, dict] = {}
    for g in rows:
        opp = next((t.team for t in g.teams if t.team != team), None)
        for t in g.teams:
            if t.team != team:
                continue
            for cat in t.categories:
                for st in cat.types:
                    col = _col(cat.name, st.name)
                    for a in st.athletes:
                        r = recs.setdefault((g.id, a.id), {"game_id": g.id, "player_id": a.id, "player": a.name,
                                                           "team": team, "opponent": opp})
                        r.update(_split_made_att(col, a.stat))
    df = pd.DataFrame(list(recs.values()))
    if df.empty:
        return df
    df = df.join(games.set_index("game_id")[["week", "start_date"]], on="game_id")
    lead = ["game_id", "week", "start_date", "player_id", "player", "team", "opponent"]
    return df[lead + sorted(c for c in df.columns if c not in lead)].sort_values(["player", "start_date"])


def roster(rows: list[RosterRaw]) -> pd.DataFrame:
    df = pd.DataFrame([{
        "player_id": r.id, "player": f"{r.firstName or ''} {r.lastName or ''}".strip(), "team": r.team,
        "jersey": r.jersey, "position": r.position, "class_year": r.year,
        "height_in": r.height, "weight_lb": r.weight, "hometown": ", ".join(x for x in (r.homeCity, r.homeState) if x),
    } for r in rows])
    return df.sort_values(["position", "jersey"]).reset_index(drop=True) if not df.empty else df
