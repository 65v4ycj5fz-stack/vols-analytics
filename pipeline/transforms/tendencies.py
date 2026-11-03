"""Aggregate classified plays into tendency and situational tables (no raw PBP leaves the pipeline)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from model.situational import over_expected
from pipeline.transforms.plays import DIST_LABELS, MARGIN_LABELS, ZONE_LABELS

SMALL_SAMPLE = 20  # rows with fewer plays are flagged in the UI

SPLITS: dict[str, list[str]] = {
    "down": ["down"],
    "distance": ["dist_bucket"],
    "down_distance": ["down", "dist_bucket"],
    "field_zone": ["field_zone"],
    "score_margin": ["margin_bucket"],
    "quarter": ["quarter"],
    "game_state": ["game_state"],
    "formation": ["shotgun"],
    "tempo": ["no_huddle"],
}
SPLIT_ORDER = {"dist_bucket": DIST_LABELS, "field_zone": ZONE_LABELS[::-1], "margin_bucket": MARGIN_LABELS}


def _agg(g: pd.core.groupby.DataFrameGroupBy) -> pd.DataFrame:
    out = pd.DataFrame({
        "plays": g.size(),
        "pass_rate": g["is_pass"].mean(),
        "success_rate": g["success"].mean(),
        "epa_per_play": g["epa"].mean(),
        "explosive_rate": g["explosive"].mean(),
        "havoc_rate": g["havoc"].mean(),
        "sack_rate": g.apply(lambda d: d["is_sack"].sum() / d["is_pass"].sum() if d["is_pass"].sum() else np.nan,
                             include_groups=False),
    })
    out["small_sample"] = out["plays"] < SMALL_SAMPLE
    return out


def scrimmage(plays: pd.DataFrame, include_garbage: bool = False) -> pd.DataFrame:
    p = plays[plays["is_scrimmage"]]
    return p if include_garbage else p[~p["garbage"]]


def _label(split: str, keys: tuple) -> str:
    if split == "formation":
        return "Shotgun/pistol" if keys[0] else "Not shotgun (under center or not noted)"
    if split == "tempo":
        return "No huddle" if keys[0] else "Huddle"
    if split == "down":
        return f"{int(keys[0])}{['st', 'nd', 'rd', 'th'][int(keys[0]) - 1]} down"
    if split == "down_distance":
        return f"{int(keys[0])}{['st', 'nd', 'rd', 'th'][int(keys[0]) - 1]} & {keys[1]}"
    return str(keys[0])


def split_table(plays: pd.DataFrame, teams: list[str], fbs_teams: set[str]) -> pd.DataFrame:
    """Run/pass and efficiency by situation for each team's offense and defense, plus an FBS baseline."""
    p = scrimmage(plays)
    frames = []
    groups = [(t, side, p[p[col] == t]) for t in teams for side, col in (("offense", "offense"), ("defense", "defense"))]
    groups.append(("FBS average", "offense", p[p["offense"].isin(fbs_teams) & p["defense"].isin(fbs_teams)]))
    for team, side, d in groups:
        for split, cols in SPLITS.items():
            if d.empty:
                continue
            a = _agg(d.groupby(cols, observed=True)).reset_index()
            a = a[~a[cols].isin(["nan"]).any(axis=1)]
            a.insert(0, "split_value", [_label(split, tuple(r)) for r in a[cols].itertuples(index=False)])
            a.insert(0, "split", split)
            a.insert(0, "side", side)
            a.insert(0, "team", team)
            a["down"] = a["down"] if "down" in a else np.nan
            a["dist_bucket"] = a["dist_bucket"] if "dist_bucket" in a else None
            a["sort"] = _sort_key(split, a, cols)
            frames.append(a.drop(columns=[c for c in cols if c not in ("down", "dist_bucket")]))
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["team", "side", "split", "sort"]).drop(columns="sort").reset_index(drop=True)


def _sort_key(split: str, a: pd.DataFrame, cols: list[str]) -> pd.Series:
    key = pd.Series(0.0, index=a.index)
    for i, c in enumerate(cols):
        order = SPLIT_ORDER.get(c)
        vals = a[c].map({v: j for j, v in enumerate(order)}) if order else pd.to_numeric(
            a[c].astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0)
        key = key * 100 + vals.astype(float)
    return key


def red_zone(plays: pd.DataFrame) -> pd.DataFrame:
    """Drive-level red-zone results: a trip is a drive with a scrimmage snap at the opponent 20 or closer."""
    p = plays[plays["drive_id"].notna()]
    rz_drives = p[p["is_scrimmage"] & (p["ytg"] <= 20)].groupby("drive_id").agg(
        offense=("offense", "first"), defense=("defense", "first"), game_id=("game_id", "first"))
    if rz_drives.empty:
        return pd.DataFrame(columns=["drive_id", "offense", "defense", "game_id", "td", "fg", "score"])
    td = p[p["is_off_td"]].groupby("drive_id").size()
    fg = p[p["play_type"] == "Field Goal Good"].groupby("drive_id").size()
    rz_drives["td"] = rz_drives.index.map(td).notna()
    rz_drives["fg"] = rz_drives.index.map(fg).notna() & ~rz_drives["td"]
    rz_drives["score"] = rz_drives["td"] | rz_drives["fg"]
    return rz_drives.reset_index()


def team_summary(plays: pd.DataFrame, pass_s: pd.DataFrame, fourth_s: pd.DataFrame,
                 fbs_teams: set[str]) -> pd.DataFrame:
    """One row per FBS team with tendency metrics (offense and defense)."""
    p = scrimmage(plays)
    early = p[p["down"].isin([1, 2])]
    passes = p[p["is_pass"]]
    rush = p[p["is_rush"]]
    rz = red_zone(plays)
    by_off, by_def = p.groupby("offense"), p.groupby("defense")
    proe = over_expected(pass_s, "pass", "xpass", ["offense"]).set_index("offense")
    proe_def = over_expected(pass_s, "pass", "xpass", ["defense"]).set_index("defense")
    go = over_expected(fourth_s, "go", "xgo", ["offense"]).set_index("offense")
    out = pd.DataFrame(index=sorted(fbs_teams))
    out.index.name = "team"
    out["plays"] = by_off.size()
    out["early_down_pass_rate"] = early.groupby("offense")["is_pass"].mean()
    out["proe"] = proe["over_expected"]
    out["proe_ci_low"], out["proe_ci_high"] = proe["ci95_low"], proe["ci95_high"]
    out["def_proe_faced"] = proe_def["over_expected"]
    out["shotgun_rate"] = by_off["shotgun"].mean()
    out["no_huddle_rate"] = by_off["no_huddle"].mean()
    dn = passes[passes["depth_noted"]]
    out["deep_pass_rate"] = dn.groupby("offense")["deep"].mean()
    out["explosive_rate"] = by_off["explosive"].mean()
    out["explosive_rush_rate"] = rush.groupby("offense")["explosive"].mean()
    out["explosive_pass_rate"] = passes.groupby("offense")["explosive"].mean()
    out["def_explosive_allowed"] = by_def["explosive"].mean()
    out["sack_rate_allowed"] = passes.groupby("offense")["is_sack"].mean()
    out["def_sack_rate"] = passes.groupby("defense")["is_sack"].mean()
    out["def_havoc_pbp"] = by_def["havoc"].mean()
    out["rz_trips"] = rz.groupby("offense").size()
    out["rz_td_rate"] = rz.groupby("offense")["td"].mean()
    out["rz_score_rate"] = rz.groupby("offense")["score"].mean()
    out["def_rz_trips"] = rz.groupby("defense").size()
    out["def_rz_td_rate"] = rz.groupby("defense")["td"].mean()
    out["def_rz_score_rate"] = rz.groupby("defense")["score"].mean()
    out["fourth_downs"] = go["n"]
    out["go_rate"] = go["actual_rate"]
    out["go_rate_expected"] = go["expected_rate"]
    out["go_over_expected"] = go["over_expected"]
    out["go_oe_ci_low"], out["go_oe_ci_high"] = go["ci95_low"], go["ci95_high"]
    for side, col in (("off", "offense"), ("def", "defense")):
        sd = p[p["down"].isin([1, 2])].groupby(col)["success"].mean()
        out[f"{side}_early_down_success"] = sd
        pd3 = p[(p["down"] == 3) & (p["distance"] >= 7)].groupby(col)["success"].mean()
        out[f"{side}_third_long_success"] = pd3
    return out.reset_index()


def situational_splits(plays: pd.DataFrame, games: pd.DataFrame, teams: list[str],
                       ranked: dict[int, set[str]]) -> pd.DataFrame:
    """Leading/trailing, home/away, vs AP-ranked, conference vs non-conference for each team.

    ``ranked`` maps week -> AP Top 25 schools entering that week.
    """
    p = scrimmage(plays)
    gmeta = games.set_index("game_id")
    p = p.join(gmeta[["neutral_site", "conference_game", "week"]].rename(columns={"week": "gweek"}), on="game_id")
    rows = []
    for team in teams:
        for side, col, opp_col in (("offense", "offense", "defense"), ("defense", "defense", "offense")):
            d = p[p[col] == team].copy()
            if d.empty:
                continue
            team_home = (d["home"] == team)
            d["site"] = np.where(d["neutral_site"], "Neutral", np.where(team_home, "Home", "Away"))
            d["opp_ranked"] = [o in ranked.get(int(w), set()) for o, w in zip(d[opp_col], d["gweek"])]
            team_state = d["game_state"] if side == "offense" else d["game_state"].map(
                {"Leading": "Trailing", "Trailing": "Leading", "Tied": "Tied"})
            for split, key in (("Game state", team_state), ("Site", d["site"]),
                               ("Opponent", np.where(d["opp_ranked"], "vs AP Top 25", "vs unranked")),
                               ("Game type", np.where(d["conference_game"], "Conference", "Non-conference"))):
                a = _agg(d.groupby(pd.Series(key, index=d.index).rename("split_value")))
                a["games"] = d.groupby(pd.Series(key, index=d.index).rename("split_value"))["game_id"].nunique()
                a = a.reset_index()
                a.insert(0, "split", split)
                a.insert(0, "side", side)
                a.insert(0, "team", team)
                rows.append(a)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def fourth_down_log(fourth_s: pd.DataFrame, teams: list[str], games: pd.DataFrame) -> pd.DataFrame:
    """Each 4th-down decision for the given teams with the typical-coach go probability."""
    d = fourth_s[fourth_s["offense"].isin(teams)].copy()
    d = d.drop(columns=["week"], errors="ignore").join(games.set_index("game_id")[["week", "start_date"]], on="game_id")
    d["converted"] = np.where(d["fourth_decision"] == "go", d["success"], np.nan)
    d["clock"] = (d["clock_sec"] // 60).astype("Int64").astype(str) + ":" + (d["clock_sec"] % 60).astype("Int64").astype(str).str.zfill(2)
    cols = ["team", "game_id", "week", "start_date", "defense", "period", "clock", "distance", "ytg", "margin",
            "fourth_decision", "xgo", "converted", "epa", "text"]
    return d.rename(columns={"offense": "team"})[cols].sort_values(["team", "start_date", "period", "clock"],
                                                                   ascending=[True, True, True, False])


def proe_by_game(pass_s: pd.DataFrame, teams: list[str], games: pd.DataFrame) -> pd.DataFrame:
    d = pass_s[pass_s["offense"].isin(teams)]
    out = over_expected(d, "pass", "xpass", ["offense", "game_id", "defense"])
    out = out.join(games.set_index("game_id")[["week", "start_date"]], on="game_id")
    return out.rename(columns={"offense": "team", "defense": "opponent"}).sort_values(["team", "start_date"])


def _m(key, label, unit, hib, group, definition):
    from pipeline.transforms.team_stats import Metric
    return Metric(key, label, unit, hib, group, definition)


TENDENCY_METRICS = [
    _m("early_down_pass_rate", "Early-down pass rate", "%", True, "offense", "Share of non-garbage 1st/2nd-down snaps that were passes (sacks count as passes)."),
    _m("proe", "Pass rate over expected (PROE)", "%", True, "offense", "Actual minus model-expected pass rate on 1st-3rd down, non-garbage. Expected = average FBS team in the same situation."),
    _m("shotgun_rate", "Shotgun/pistol rate", "%", True, "offense", "Share of snaps whose play-by-play text says 'Shotgun' (pistol is usually logged as shotgun)."),
    _m("no_huddle_rate", "No-huddle rate", "%", True, "offense", "Share of snaps whose play-by-play text says 'No Huddle' (tempo proxy; under-reported by some scorers)."),
    _m("deep_pass_rate", "Deep-pass rate", "%", True, "offense", "Share of pass attempts described as 'deep' among those with a depth noted (deep = 15+ air yards in ESPN charting)."),
    _m("explosive_rate", "Explosive play rate", "%", True, "offense", "Runs of 10+ yards and passes of 20+ yards / scrimmage plays."),
    _m("explosive_rush_rate", "Explosive run rate", "%", True, "offense", "Runs of 10+ yards / runs."),
    _m("explosive_pass_rate", "Explosive pass rate", "%", True, "offense", "Passes of 20+ yards / dropbacks."),
    _m("def_explosive_allowed", "Explosive plays allowed", "%", False, "defense", "Opponent explosive plays / opponent scrimmage plays."),
    _m("sack_rate_allowed", "Sack rate allowed", "%", False, "offense", "Sacks / dropbacks."),
    _m("def_sack_rate", "Sack rate", "%", True, "defense", "Sacks / opponent dropbacks (the only pressure measure in public PBP)."),
    _m("def_havoc_pbp", "Havoc rate (PBP)", "%", True, "defense", "Sacks, TFLs, INTs, fumbles and pass breakups noted in play text / opponent scrimmage plays."),
    _m("rz_td_rate", "Red-zone TD rate", "%", True, "offense", "Drives with a snap at the opponent 20 or closer that ended in an offensive TD."),
    _m("rz_score_rate", "Red-zone scoring rate", "%", True, "offense", "Red-zone trips ending in a TD or made FG."),
    _m("def_rz_td_rate", "Red-zone TD rate allowed", "%", False, "defense", "Opponent red-zone trips ending in a TD."),
    _m("def_rz_score_rate", "Red-zone scoring rate allowed", "%", False, "defense", "Opponent red-zone trips ending in a TD or made FG."),
    _m("go_rate", "4th-down go rate", "%", True, "offense", "Share of non-garbage 4th downs where the offense ran a play (vs punt/FG)."),
    _m("go_over_expected", "4th-down go rate over expected", "%", True, "offense", "Go rate minus what a typical FBS coach does in the same situations. Aggressiveness, not decision quality."),
    _m("off_early_down_success", "Early-down success rate", "%", True, "offense", "Success rate on 1st and 2nd down."),
    _m("def_early_down_success", "Early-down success allowed", "%", False, "defense", "Opponent success rate on 1st and 2nd down."),
    _m("off_third_long_success", "3rd-and-7+ success", "%", True, "offense", "Conversion-level success on 3rd and 7 or longer."),
    _m("def_third_long_success", "3rd-and-7+ success allowed", "%", False, "defense", "Opponent success on 3rd and 7 or longer."),
]
NEUTRAL_TENDENCIES = {"early_down_pass_rate", "proe", "shotgun_rate", "no_huddle_rate", "deep_pass_rate", "go_rate",
                      "go_over_expected"}
