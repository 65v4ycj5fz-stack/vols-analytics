"""Game-level tables: all games with consensus lines, and one team's schedule."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.schemas import GameLinesRaw, GameRaw


def consensus_lines(lines: list[GameLinesRaw]) -> pd.DataFrame:
    """Median closing spread/total across the providers CFBD lists for each game.

    CFBD's ``spread`` is from the home team's perspective (negative = home favored).
    """
    rows = []
    for g in lines:
        spreads = [ln.spread for ln in g.lines if ln.spread is not None]
        opens = [ln.spreadOpen for ln in g.lines if ln.spreadOpen is not None]
        totals = [ln.overUnder for ln in g.lines if ln.overUnder is not None]
        if not spreads and not totals:
            continue
        rows.append({
            "game_id": g.id,
            "spread_home": float(np.median(spreads)) if spreads else np.nan,
            "spread_open_home": float(np.median(opens)) if opens else np.nan,
            "total": float(np.median(totals)) if totals else np.nan,
            "line_providers": ", ".join(sorted({ln.provider for ln in g.lines})),
        })
    cols = ["game_id", "spread_home", "spread_open_home", "total", "line_providers"]
    return pd.DataFrame(rows, columns=cols)


def games_frame(games: list[GameRaw], lines: list[GameLinesRaw] | None = None) -> pd.DataFrame:
    df = pd.DataFrame([{
        "game_id": g.id, "season": g.season, "week": g.week, "season_type": g.seasonType,
        "start_date": g.startDate, "start_time_tbd": bool(g.startTimeTBD), "completed": g.completed, "neutral_site": g.neutralSite,
        "conference_game": g.conferenceGame, "venue": g.venue, "venue_id": g.venueId,
        "home_team": g.homeTeam, "home_id": g.homeId, "home_class": g.homeClassification,
        "home_conf": g.homeConference, "home_pts": g.homePoints,
        "away_team": g.awayTeam, "away_id": g.awayId, "away_class": g.awayClassification,
        "away_conf": g.awayConference, "away_pts": g.awayPoints,
    } for g in games])
    if df.empty:
        return df
    df = df.drop_duplicates("game_id")
    df["start_date"] = pd.to_datetime(df["start_date"], utc=True)
    for c in ("home_pts", "away_pts"):
        df[c] = df[c].astype("Float64")
    if lines is not None:
        df = df.merge(consensus_lines(lines), on="game_id", how="left")
    else:
        for c in ("spread_home", "spread_open_home", "total"):
            df[c] = np.nan
        df["line_providers"] = None
    return df.sort_values(["start_date", "game_id"]).reset_index(drop=True)


def fbs_games(df: pd.DataFrame) -> pd.DataFrame:
    """Games with at least one FBS team."""
    return df[(df["home_class"] == "fbs") | (df["away_class"] == "fbs")].copy()


def team_schedule(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """One row per game from ``team``'s perspective.

    ``spread`` follows the usual convention: negative means ``team`` was favored.
    ``ats`` is "covered" / "push" / "not covered" for completed games with a line.
    """
    g = df[(df["home_team"] == team) | (df["away_team"] == team)].copy()
    is_home = g["home_team"] == team
    out = pd.DataFrame({
        "game_id": g["game_id"], "season": g["season"], "week": g["week"],
        "season_type": g["season_type"], "start_date": g["start_date"],
        "opponent": np.where(is_home, g["away_team"], g["home_team"]),
        "opponent_conf": np.where(is_home, g["away_conf"], g["home_conf"]),
        "opponent_class": np.where(is_home, g["away_class"], g["home_class"]),
        "site": np.where(g["neutral_site"], "neutral", np.where(is_home, "home", "away")),
        "conference_game": g["conference_game"], "venue": g["venue"], "completed": g["completed"],
        "points_for": np.where(is_home, g["home_pts"], g["away_pts"]),
        "points_against": np.where(is_home, g["away_pts"], g["home_pts"]),
        "spread": np.where(is_home, g["spread_home"], -g["spread_home"]),
        "total": g["total"], "line_providers": g["line_providers"],
    })
    for c in ("points_for", "points_against", "spread", "total"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    done = out["completed"] & out["points_for"].notna()
    out["margin"] = np.where(done, out["points_for"] - out["points_against"], np.nan)
    out["result"] = np.select([done & (out["margin"] > 0), done & (out["margin"] < 0), done],
                              ["W", "L", "T"], default="")
    ats_margin = out["margin"] + out["spread"]
    has_line = done & out["spread"].notna()
    out["ats_margin"] = np.where(has_line, ats_margin, np.nan)
    out["ats"] = np.select([has_line & (ats_margin > 0), has_line & (ats_margin < 0), has_line],
                           ["covered", "not covered", "push"], default="")
    return out.sort_values("start_date").reset_index(drop=True)


def record(schedule: pd.DataFrame, conference_only: bool = False) -> dict[str, int]:
    s = schedule[schedule["result"] != ""]
    if conference_only:
        s = s[s["conference_game"]]
    return {k: int((s["result"] == v).sum()) for k, v in (("wins", "W"), ("losses", "L"), ("ties", "T"))}
