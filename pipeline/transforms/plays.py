"""Turn raw CFBD plays into a slim, classified play table.

Everything here is derived from CFBD fields or from the official play-by-play text
(e.g. "Shotgun", "No Huddle", "pass incomplete deep left"). Definitions are in
docs/data-dictionary.md and repeated in the dataset notes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.schemas import PlayRaw

RUSH_TYPES = {"Rush", "Rushing Touchdown"}
PASS_TYPES = {"Pass Reception", "Pass Incompletion", "Passing Touchdown", "Sack", "Interception",
              "Pass Interception Return", "Interception Return Touchdown", "Pass Completion", "Pass"}
FUMBLE_TYPES = {"Fumble Recovery (Own)", "Fumble Recovery (Opponent)", "Fumble Return Touchdown", "Fumble"}
INT_TYPES = {"Interception", "Pass Interception Return", "Interception Return Touchdown"}
OFF_TD_TYPES = {"Rushing Touchdown", "Passing Touchdown"}
PUNT_TYPES = {"Punt", "Blocked Punt", "Blocked Punt Touchdown", "Punt Return", "Punt Return Touchdown"}
FG_TYPES = {"Field Goal Good", "Field Goal Missed", "Blocked Field Goal", "Blocked Field Goal Touchdown",
            "Missed Field Goal Return", "Missed Field Goal Return Touchdown"}

# CFBD's garbage-time definition: absolute score margin above this in the given quarter.
GARBAGE_MARGIN = {2: 38, 3: 28, 4: 22}
EXPLOSIVE_RUSH_YDS = 10
EXPLOSIVE_PASS_YDS = 20

DIST_BINS = [0, 3, 6, 10, 99]
DIST_LABELS = ["1-3", "4-6", "7-10", "11+"]
ZONE_BINS = [0, 20, 49, 79, 100]
ZONE_LABELS = ["Red zone (opp 1-20)", "Opp 21-49", "Own 21-50", "Backed up (own 1-20)"]
MARGIN_BINS = [-99, -15, -8, -1, 0, 7, 14, 99]
MARGIN_LABELS = ["Down 15+", "Down 8-14", "Down 1-7", "Tied", "Up 1-7", "Up 8-14", "Up 15+"]


def plays_frame(plays: list[PlayRaw], season: int | None = None, week_of_game: dict[int, int] | None = None) -> pd.DataFrame:
    if not plays:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "game_id": p.gameId, "play_id": int(p.id), "drive_id": p.driveId, "offense": p.offense,
        "defense": p.defense, "home": p.home, "off_conf": p.offenseConference, "def_conf": p.defenseConference,
        "off_score_post": p.offenseScore, "def_score_post": p.defenseScore, "period": p.period,
        "clock_sec": (p.clock.minutes or 0) * 60 + (p.clock.seconds or 0) if p.clock else np.nan,
        "ytg": p.yardsToGoal, "down": p.down, "distance": p.distance, "yards": p.yardsGained,
        "play_type": p.playType, "text": p.playText or "", "epa": p.ppa,
    } for p in plays])
    df = df.drop_duplicates("play_id").sort_values(["game_id", "play_id"]).reset_index(drop=True)
    if season is not None:
        df["season"] = season
    if week_of_game is not None:
        df["week"] = df["game_id"].map(week_of_game)
    return classify(df)


def _pre_play_margin(df: pd.DataFrame) -> pd.Series:
    """CFBD scores on a play are *after* the play; rebuild the score at the snap.

    Track home/away score after each play, then shift by one within each game.
    """
    is_home_off = df["offense"] == df["home"]
    home_post = np.where(is_home_off, df["off_score_post"], df["def_score_post"]).astype(float)
    away_post = np.where(is_home_off, df["def_score_post"], df["off_score_post"]).astype(float)
    g = pd.DataFrame({"game_id": df["game_id"], "h": home_post, "a": away_post})
    g[["h", "a"]] = g.groupby("game_id")[["h", "a"]].ffill()
    h_pre = g.groupby("game_id")["h"].shift(1).fillna(0)
    a_pre = g.groupby("game_id")["a"].shift(1).fillna(0)
    return pd.Series(np.where(is_home_off, h_pre - a_pre, a_pre - h_pre), index=df.index)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    text = df["text"].str.lower()
    pt = df["play_type"]
    fumble_on_pass = pt.isin(FUMBLE_TYPES) & text.str.contains(r"\bpass\b|sacked", regex=True)
    fumble_on_rush = pt.isin(FUMBLE_TYPES) & text.str.contains(r"\brush\b|\brun\b|scramble", regex=True) & ~fumble_on_pass
    kneel = text.str.contains("kneel")
    spike = text.str.contains("spike")
    df["is_pass"] = (pt.isin(PASS_TYPES) | fumble_on_pass) & ~spike
    df["is_rush"] = (pt.isin(RUSH_TYPES) | fumble_on_rush) & ~kneel & ~df["is_pass"]
    df["is_scrimmage"] = (df["is_pass"] | df["is_rush"]) & df["down"].between(1, 4)
    df["is_sack"] = (pt == "Sack") | (df["is_pass"] & text.str.contains("sacked"))
    df["is_int"] = pt.isin(INT_TYPES)
    df["is_fumble"] = pt.isin(FUMBLE_TYPES)
    df["is_fumble_lost"] = pt.isin({"Fumble Recovery (Opponent)", "Fumble Return Touchdown"})
    df["is_turnover"] = df["is_int"] | df["is_fumble_lost"]
    df["is_off_td"] = pt.isin(OFF_TD_TYPES)
    df["shotgun"] = text.str.contains("shotgun")
    df["no_huddle"] = text.str.contains("no huddle")
    df["deep"] = df["is_pass"] & text.str.contains(r"\bdeep\b", regex=True)
    df["depth_noted"] = df["is_pass"] & text.str.contains(r"\b(?:deep|short)\b", regex=True)
    df["pbu"] = df["is_pass"] & text.str.contains("broken up")
    df["tfl"] = df["is_rush"] & (df["yards"] < 0)
    # Havoc (defense credit): sack, TFL, INT, any fumble, or pass broken up noted in the text.
    df["havoc"] = df["is_scrimmage"] & (df["is_sack"] | df["tfl"] | df["is_int"] | df["is_fumble"] | df["pbu"])

    need = np.select([df["down"] == 1, df["down"] == 2], [0.5, 0.7], 1.0) * df["distance"]
    df["success"] = np.where(df["is_scrimmage"], (df["yards"] >= need) | df["is_off_td"], np.nan)
    df["explosive"] = np.where(df["is_scrimmage"], np.where(df["is_pass"], df["yards"] >= EXPLOSIVE_PASS_YDS,
                                                             df["yards"] >= EXPLOSIVE_RUSH_YDS), np.nan)
    df["margin"] = _pre_play_margin(df)
    df["garbage"] = [abs(m) > GARBAGE_MARGIN.get(p, 999) for m, p in zip(df["margin"], df["period"])]
    # seconds left in the half (periods 1/3: + 15 min); overtime gets 0
    df["half_sec_left"] = np.where(df["period"].isin([1, 3]), df["clock_sec"] + 900,
                                   np.where(df["period"].isin([2, 4]), df["clock_sec"], 0))
    df["is_home"] = df["offense"] == df["home"]

    df["dist_bucket"] = pd.cut(df["distance"], DIST_BINS, labels=DIST_LABELS).astype(str)
    df["field_zone"] = pd.cut(df["ytg"], ZONE_BINS, labels=ZONE_LABELS).astype(str)
    df["margin_bucket"] = pd.cut(df["margin"], MARGIN_BINS, labels=MARGIN_LABELS).astype(str)
    df["quarter"] = np.where(df["period"] >= 5, "OT", "Q" + df["period"].astype(str))
    df["game_state"] = np.select([df["margin"] > 0, df["margin"] < 0], ["Leading", "Trailing"], "Tied")
    df["fourth_decision"] = np.select(
        [(df["down"] == 4) & df["is_scrimmage"], (df["down"] == 4) & pt.isin(PUNT_TYPES),
         (df["down"] == 4) & pt.isin(FG_TYPES)], ["go", "punt", "fg"], "")
    return df
