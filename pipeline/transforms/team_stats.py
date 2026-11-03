"""Season and per-game team stat tables with national and conference ranks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline.schemas import AdvGameRaw, AdvSeasonRaw, BoxGameRaw, SeasonStatRaw, TeamRaw


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    higher_is_better: bool
    group: str  # offense | defense | special | overall
    definition: str


# The website reads this registry (via metrics.json) for labels, units and rank direction.
METRICS: list[Metric] = [
    Metric("points_pg", "Points per game", "pts", True, "offense", "Points scored / games played (all opponents)."),
    Metric("points_allowed_pg", "Points allowed per game", "pts", False, "defense", "Points allowed / games played."),
    Metric("off_ypp", "Yards per play", "yds", True, "offense", "Total yards / (rush attempts + pass attempts). Sacks count as rushes in NCAA stats."),
    Metric("def_ypp", "Yards per play allowed", "yds", False, "defense", "Opponent total yards / opponent plays."),
    Metric("off_epa", "EPA per play", "pts/play", True, "offense", "CFBD predicted points added (PPA, an EPA measure) per offensive play; excludes garbage time per CFBD."),
    Metric("off_rush_epa", "Rush EPA per play", "pts/play", True, "offense", "PPA per rushing play."),
    Metric("off_pass_epa", "Pass EPA per play", "pts/play", True, "offense", "PPA per passing play."),
    Metric("off_success", "Success rate", "%", True, "offense", "Share of plays gaining 50% of needed yards on 1st down, 70% on 2nd, 100% on 3rd/4th."),
    Metric("off_explosiveness", "Explosiveness", "pts/play", True, "offense", "Average PPA on successful plays (CFBD definition)."),
    Metric("def_epa", "EPA per play allowed", "pts/play", False, "defense", "PPA per opponent play."),
    Metric("def_rush_epa", "Rush EPA allowed", "pts/play", False, "defense", "PPA per opponent rushing play."),
    Metric("def_pass_epa", "Pass EPA allowed", "pts/play", False, "defense", "PPA per opponent passing play."),
    Metric("def_success", "Success rate allowed", "%", False, "defense", "Opponent success rate."),
    Metric("def_explosiveness", "Explosiveness allowed", "pts/play", False, "defense", "Opponent average PPA on successful plays."),
    Metric("def_havoc", "Havoc rate", "%", True, "defense", "Share of opponent plays with a TFL, forced fumble, INT or PBU (CFBD)."),
    Metric("off_havoc_allowed", "Havoc allowed", "%", False, "offense", "Share of own plays with a havoc event."),
    Metric("third_down_pct", "3rd-down conversion", "%", True, "offense", "3rd-down conversions / attempts."),
    Metric("third_down_pct_allowed", "3rd-down conversion allowed", "%", False, "defense", "Opponent 3rd-down conversions / attempts."),
    Metric("fourth_down_pct", "4th-down conversion", "%", True, "offense", "4th-down conversions / attempts."),
    Metric("fourth_down_att_pg", "4th-down attempts per game", "att", True, "offense", "4th-down attempts / games (aggressiveness proxy, not a quality measure)."),
    Metric("off_pts_per_opp", "Points per trip inside the 40", "pts", True, "offense", "CFBD points per scoring opportunity (drive reaching the opponent 40). Our 'finishing drives' measure."),
    Metric("def_pts_per_opp", "Points per trip inside the 40 allowed", "pts", False, "defense", "Opponent points per scoring opportunity."),
    Metric("off_field_pos", "Avg. starting field position", "yds to goal", False, "special", "CFBD averageStart for own drives: yards from the opponent end zone (lower = shorter field)."),
    Metric("def_field_pos", "Opp. avg. starting field position", "yds to goal", True, "special", "CFBD averageStart for opponent drives (higher = longer field for the opponent)."),
    Metric("turnovers_pg", "Turnovers per game", "TO", False, "offense", "Interceptions thrown + fumbles lost, per game."),
    Metric("takeaways_pg", "Takeaways per game", "TO", True, "defense", "Opponent turnovers per game."),
    Metric("turnover_margin", "Turnover margin", "TO", True, "overall", "Takeaways - turnovers (season total)."),
    Metric("penalties_pg", "Penalties per game", "pen", False, "overall", "Accepted penalties per game."),
    Metric("penalty_yards_pg", "Penalty yards per game", "yds", False, "overall", "Penalty yards per game."),
    Metric("plays_pg", "Plays per game", "plays", True, "overall", "Offensive plays per game (CFBD advanced stats). Pace measure; not good or bad."),
    Metric("sec_per_play", "Seconds of possession per play", "sec", False, "overall", "Possession time / offensive plays. Lower = faster tempo; not good or bad."),
    Metric("stuff_rate_allowed", "Stuff rate allowed", "%", False, "offense", "Share of own runs stopped at or behind the line."),
    Metric("def_stuff_rate", "Stuff rate", "%", True, "defense", "Share of opponent runs stopped at or behind the line."),
]
NEUTRAL_RANK = {"plays_pg", "sec_per_play", "fourth_down_att_pg"}  # ranked, but no "edge" coloring


def _div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return np.where((b > 0) & b.notna(), a / b.where(b != 0, np.nan), np.nan)


def points_by_team(games: pd.DataFrame) -> pd.DataFrame:
    done = games[games["completed"] & games["home_pts"].notna()]
    home = done[["home_team", "home_pts", "away_pts"]].set_axis(["team", "pf", "pa"], axis=1)
    away = done[["away_team", "away_pts", "home_pts"]].set_axis(["team", "pf", "pa"], axis=1)
    both = pd.concat([home, away])
    both[["pf", "pa"]] = both[["pf", "pa"]].astype(float)
    return both.groupby("team").agg(games_scored=("pf", "size"), pf=("pf", "sum"), pa=("pa", "sum")).reset_index()


def season_table(stats: list[SeasonStatRaw], adv: list[AdvSeasonRaw], games: pd.DataFrame,
                 teams: list[TeamRaw]) -> pd.DataFrame:
    """One row per FBS team: metrics from METRICS plus *_rank and *_conf_rank columns."""
    wide = (pd.DataFrame([s.model_dump() for s in stats])
            .pivot_table(index="team", columns="statName", values="statValue", aggfunc="first"))
    s = wide.reindex(columns=sorted(set(wide.columns) | {
        "games", "totalYards", "totalYardsOpponent", "rushingAttempts", "passAttempts",
        "rushingAttemptsOpponent", "passAttemptsOpponent", "thirdDowns", "thirdDownConversions",
        "thirdDownsOpponent", "thirdDownConversionsOpponent", "fourthDowns", "fourthDownConversions",
        "turnovers", "turnoversOpponent", "penalties", "penaltyYards", "possessionTime"}))
    a = {r.team: r for r in adv}
    fbs = pd.DataFrame([{"team": t.school, "conference": t.conference, "team_id": t.id,
                         "abbreviation": t.abbreviation, "color": t.color} for t in teams])
    df = fbs.merge(s, left_on="team", right_index=True, how="left")
    df = df.merge(points_by_team(games), on="team", how="left")
    g = df["games"]

    def adv_get(team: str, side: str, path: str):
        r = a.get(team)
        if r is None:
            return np.nan
        obj = getattr(r, side)
        for p in path.split("."):
            obj = getattr(obj, p, None) if obj is not None else None
        return np.nan if obj is None else obj

    def col(side, path):
        return df["team"].map(lambda t: adv_get(t, side, path)).astype(float)

    out = df[["team", "conference", "team_id", "abbreviation", "color"]].copy()
    out["games"] = g
    out["points_pg"] = _div(df["pf"], df["games_scored"])
    out["points_allowed_pg"] = _div(df["pa"], df["games_scored"])
    out["off_ypp"] = _div(df["totalYards"], df["rushingAttempts"] + df["passAttempts"])
    out["def_ypp"] = _div(df["totalYardsOpponent"], df["rushingAttemptsOpponent"] + df["passAttemptsOpponent"])
    for side, pre in (("offense", "off"), ("defense", "def")):
        out[f"{pre}_epa"] = col(side, "ppa")
        out[f"{pre}_rush_epa"] = col(side, "rushingPlays.ppa")
        out[f"{pre}_pass_epa"] = col(side, "passingPlays.ppa")
        out[f"{pre}_success"] = col(side, "successRate")
        out[f"{pre}_explosiveness"] = col(side, "explosiveness")
        out[f"{pre}_pts_per_opp"] = col(side, "pointsPerOpportunity")
        out[f"{pre}_field_pos"] = col(side, "fieldPosition.averageStart")
    out["def_havoc"] = col("defense", "havoc.total")
    out["off_havoc_allowed"] = col("offense", "havoc.total")
    out["stuff_rate_allowed"] = col("offense", "stuffRate")
    out["def_stuff_rate"] = col("defense", "stuffRate")
    out["third_down_pct"] = _div(df["thirdDownConversions"], df["thirdDowns"])
    out["third_down_pct_allowed"] = _div(df["thirdDownConversionsOpponent"], df["thirdDownsOpponent"])
    out["fourth_down_pct"] = _div(df["fourthDownConversions"], df["fourthDowns"])
    out["fourth_down_att_pg"] = _div(df["fourthDowns"], g)
    out["turnovers_pg"] = _div(df["turnovers"], g)
    out["takeaways_pg"] = _div(df["turnoversOpponent"], g)
    out["turnover_margin"] = df["turnoversOpponent"] - df["turnovers"]
    out["penalties_pg"] = _div(df["penalties"], g)
    out["penalty_yards_pg"] = _div(df["penaltyYards"], g)
    off_plays = col("offense", "plays")
    out["plays_pg"] = _div(off_plays, g)
    out["sec_per_play"] = _div(df["possessionTime"], off_plays)
    return add_ranks(out)


def add_ranks(df: pd.DataFrame, metrics: list[Metric] = METRICS) -> pd.DataFrame:
    """1 = best nationally / in conference. Ties share the best rank; missing values stay unranked."""
    df = df.copy()
    for m in metrics:
        if m.key not in df:
            continue
        asc = not m.higher_is_better
        df[f"{m.key}_rank"] = df[m.key].rank(ascending=asc, method="min").astype("Int64")
        df[f"{m.key}_conf_rank"] = (df.groupby("conference")[m.key]
                                    .rank(ascending=asc, method="min").astype("Int64"))
    return df


# ---- per-game --------------------------------------------------------------

def _made_att(s: str) -> tuple[float, float]:
    try:
        made, att = s.split("-")
        return float(made), float(att)
    except (ValueError, AttributeError):
        return np.nan, np.nan


def _clock(s: str) -> float:
    try:
        m, sec = s.split(":")
        return int(m) * 60 + int(sec)
    except (ValueError, AttributeError):
        return np.nan


def box_frame(box: list[BoxGameRaw]) -> pd.DataFrame:
    rows = []
    for g in box:
        for t in g.teams:
            st = {s.category: s.stat for s in t.stats}
            comp, att = _made_att(st.get("completionAttempts", ""))
            c3, a3 = _made_att(st.get("thirdDownEff", ""))
            c4, a4 = _made_att(st.get("fourthDownEff", ""))
            pen, pen_yds = _made_att(st.get("totalPenaltiesYards", ""))

            def num(k):
                return pd.to_numeric(st.get(k), errors="coerce")

            rows.append({
                "game_id": g.id, "team": t.team, "home_away": t.homeAway,
                "total_yards": num("totalYards"), "rush_att": num("rushingAttempts"),
                "rush_yards": num("rushingYards"), "pass_att": att, "pass_comp": comp,
                "pass_yards": num("netPassingYards"), "turnovers": num("turnovers"),
                "third_conv": c3, "third_att": a3, "fourth_conv": c4, "fourth_att": a4,
                "penalties": pen, "penalty_yards": pen_yds, "possession_sec": _clock(st.get("possessionTime", "")),
                "sacks": num("sacks"), "tfl": num("tacklesForLoss"),
            })
    return pd.DataFrame(rows).drop_duplicates(["game_id", "team"]) if rows else pd.DataFrame()


def adv_game_frame(adv: list[AdvGameRaw]) -> pd.DataFrame:
    rows = []
    for r in adv:
        row = {"game_id": r.gameId, "season": r.season, "week": r.week, "team": r.team, "opponent": r.opponent}
        for side, pre in ((r.offense, "off"), (r.defense, "def")):
            row[f"{pre}_plays"] = side.plays
            row[f"{pre}_epa"] = side.ppa
            row[f"{pre}_success"] = side.successRate
            row[f"{pre}_explosiveness"] = side.explosiveness
            row[f"{pre}_rush_epa"] = side.rushingPlays.ppa if side.rushingPlays else None
            row[f"{pre}_pass_epa"] = side.passingPlays.ppa if side.passingPlays else None
            row[f"{pre}_rush_success"] = side.rushingPlays.successRate if side.rushingPlays else None
            row[f"{pre}_pass_success"] = side.passingPlays.successRate if side.passingPlays else None
        rows.append(row)
    df = pd.DataFrame(rows)
    return df.drop_duplicates(["game_id", "team"]) if not df.empty else df


def game_table(games: pd.DataFrame, adv: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """One row per team per completed game, with points, efficiency and box-score stats."""
    done = games[games["completed"]]
    home = done.assign(team=done["home_team"], opponent=done["away_team"], pf=done["home_pts"],
                       pa=done["away_pts"], site=np.where(done["neutral_site"], "neutral", "home"),
                       spread=done["spread_home"])
    away = done.assign(team=done["away_team"], opponent=done["home_team"], pf=done["away_pts"],
                       pa=done["home_pts"], site=np.where(done["neutral_site"], "neutral", "away"),
                       spread=-done["spread_home"])
    base = pd.concat([home, away])[["game_id", "season", "week", "season_type", "start_date", "team",
                                    "opponent", "site", "conference_game", "pf", "pa", "spread"]]
    base = base.rename(columns={"pf": "points_for", "pa": "points_against"})
    if not adv.empty:
        base = base.merge(adv.drop(columns=["season", "week", "opponent"]), on=["game_id", "team"], how="left")
    if not box.empty:
        opp = box[["game_id", "team", "total_yards", "rush_att", "pass_att", "turnovers"]].rename(columns={
            "team": "opponent", "total_yards": "opp_total_yards", "rush_att": "opp_rush_att",
            "pass_att": "opp_pass_att", "turnovers": "opp_turnovers"})
        base = base.merge(box.drop(columns=["home_away"]), on=["game_id", "team"], how="left")
        base = base.merge(opp, on=["game_id", "opponent"], how="left")
        base["off_ypp"] = _div(base["total_yards"], base["rush_att"] + base["pass_att"])
        base["def_ypp"] = _div(base["opp_total_yards"], base["opp_rush_att"] + base["opp_pass_att"])
    base["margin"] = base["points_for"].astype(float) - base["points_against"].astype(float)
    return base.sort_values(["start_date", "game_id", "team"]).reset_index(drop=True)
