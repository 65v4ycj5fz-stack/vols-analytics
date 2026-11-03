"""Generate docs/data-dictionary.md from the published datasets: ``python -m pipeline.docs``.

Column descriptions come from the metric registry (pipeline/transforms/*) plus the
COMMON table below, so the dictionary always matches what the site actually ships.
"""

from __future__ import annotations

import json
from collections import OrderedDict

from pipeline import config
from pipeline.transforms.tendencies import TENDENCY_METRICS
from pipeline.transforms.team_stats import METRICS

COMMON = {
    "game_id": "CFBD game id", "season": "Season (year the season started)", "week": "CFBD week number",
    "season_type": "regular or postseason", "start_date": "Kickoff, ISO 8601 UTC (TBD kickoffs show 05:00 UTC)",
    "team": "CFBD team name", "opponent": "Opponent (CFBD name)", "conference": "Conference",
    "site": "home / away / neutral (from the team's perspective)", "completed": "Game has been played",
    "points_for": "Points scored", "points_against": "Points allowed", "margin": "points_for - points_against",
    "spread": "Median closing spread, team perspective (negative = favored)", "total": "Median closing over/under",
    "result": "W / L / T", "ats": "Result vs closing spread: covered / not covered / push",
    "ats_margin": "margin + spread", "line_providers": "Sportsbooks CFBD listed for the line",
    "player_id": "CFBD athlete id", "player": "Player name", "position": "Position",
    "split": "Split family (e.g. down, field_zone)", "split_value": "Split bucket label", "side": "offense or defense",
    "plays": "Scrimmage plays in the bucket (non-garbage time)", "pass_rate": "Share of plays that were passes (sacks count)",
    "success_rate": "Success rate (50%/70%/100% of yards-to-go on 1st/2nd/3rd-4th down)",
    "epa_per_play": "Mean CFBD PPA (EPA) per play", "explosive_rate": "Runs >= 10 yds / passes >= 20 yds",
    "small_sample": "True when fewer than 20 plays", "elo": "Our Elo rating (settings chosen by the backtest)",
    "last_updated": "Date the row was last checked (manual data)", "source": "Where the row came from (manual data)",
    "win_prob": "Model win probability for the team", "pred_margin": "Model predicted margin (team perspective)",
    "margin_p10": "10th percentile of the margin (80% interval low)", "margin_p90": "90th percentile (80% interval high)",
    "market_spread": "Closing spread (team perspective, negative = favored)", "actual_margin": "Final margin",
    "xgo": "Probability a typical FBS coach goes for it in this spot", "xpass": "Expected pass probability",
    "over_expected": "Actual rate - expected rate", "ci95_low": "95% interval low", "ci95_high": "95% interval high",
    "adj_off_epa": "Opponent-adjusted offensive EPA/play vs average", "adj_def_epa": "Opponent-adjusted EPA/play allowed vs average (lower is better)",
    "adj_net_epa": "adj_off_epa - adj_def_epa", "model_points": "Expected points lost (injury assumption; see Model page)",
}


COMMON.update({
    "games": "Games played", "conference_game": "Conference game", "venue": "Stadium name",
    "sack_rate": "Sacks / dropbacks", "havoc_rate": "Plays with a sack, TFL, INT, fumble or PBU / plays",
    "opponent_conf": "Opponent's conference", "opponent_class": "Opponent's division (fbs, fcs, ...)",
    "dist_bucket": "Yards-to-go bucket", "down": "Down", "team_id": "CFBD team id", "abbreviation": "Team abbreviation",
    "color": "Team color from CFBD (not used for team identity on the site)", "home_away": "home or away",
    "venue_id": "CFBD venue id",
})
COMMON.update({
    "actual_rate": "Observed rate", "expected_rate": "Model-expected rate for the same situations",
    "n": "Plays or games in the sample", "adj_off_success": "Opponent-adjusted success rate vs average",
    "adj_def_success": "Opponent-adjusted success rate allowed vs average (lower is better)",
    "adjustments_pts": "Sum of all adjustments to the margin, points", "baseline_margin": "Margin before adjustments",
    "proj_margin": "Projected margin after adjustments", "proj_team_points": "Projected team points",
    "proj_opp_points": "Projected opponent points", "base_rate": "Share of positives in training data",
    "cv_log_loss": "Held-out log loss (grouped by game)", "baseline_log_loss": "Log loss of a constant rate",
    "cv_auc": "Held-out AUC", "n_train": "Training rows", "validation": "How the model was validated", "model": "Model name",
    "cfbd_elo": "CFBD's published Elo", "fpi": "ESPN FPI as relayed by CFBD", "sp_rating": "SP+ overall",
    "sp_off": "SP+ offense", "sp_def": "SP+ defense (points allowed; lower is better)", "sp_st": "SP+ special teams",
    "class_year": "Class year from CFBD (blank when CFBD's data is unreliable)", "height_in": "Height, inches",
    "weight_lb": "Weight, pounds", "hometown": "Hometown", "jersey": "Jersey number",
    "clock": "Game clock (m:ss) when the play started", "period": "Quarter (5+ = overtime)",
    "distance": "Yards to go for a first down", "ytg": "Yards to the opponent end zone",
    "fourth_decision": "go / punt / fg", "converted": "1 if a go-for-it attempt gained the first down",
    "epa": "CFBD PPA (EPA) of the play", "text": "Official play-by-play text (4th downs only)", "defense": "Defending team",
    "def_proe_faced": "PROE of offenses against this defense", "rz_trips": "Red-zone trips (drives with a snap at opp 20 or closer)",
    "def_rz_trips": "Opponent red-zone trips", "fourth_downs": "Non-garbage 4th downs", "go_rate_expected": "Typical-coach go rate in the same spots",
    "go_oe_ci_low": "95% interval low for go rate over expected", "go_oe_ci_high": "95% interval high for go rate over expected",
    "proe_ci_low": "95% interval low for PROE", "proe_ci_high": "95% interval high for PROE",
    "team_elo": "Team Elo before the game", "opp_elo": "Opponent Elo before the game",
    "team_adj_off": "Team adjusted offensive EPA/play before the game", "team_adj_def": "Team adjusted EPA/play allowed before the game",
    "opp_adj_off": "Opponent adjusted offensive EPA/play before the game", "opp_adj_def": "Opponent adjusted EPA/play allowed before the game",
    "team_games_in_season": "Team games played before this one", "opp_games_in_season": "Opponent games played before this one",
    "off_plays": "Offensive plays (CFBD advanced stats)", "def_plays": "Opponent offensive plays",
    "off_rush_success": "Rush success rate", "off_pass_success": "Pass success rate",
    "def_rush_success": "Rush success rate allowed", "def_pass_success": "Pass success rate allowed",
    "total_yards": "Total yards (box score)", "rush_att": "Rush attempts", "rush_yards": "Rushing yards",
    "pass_att": "Pass attempts", "pass_comp": "Completions", "pass_yards": "Net passing yards", "turnovers": "Turnovers",
    "third_conv": "3rd-down conversions", "third_att": "3rd-down attempts", "fourth_conv": "4th-down conversions",
    "fourth_att": "4th-down attempts", "penalties": "Penalties", "penalty_yards": "Penalty yards",
    "possession_sec": "Time of possession, seconds", "sacks": "Sacks by this team's defense", "tfl": "Tackles for loss",
    "opp_total_yards": "Opponent total yards", "opp_rush_att": "Opponent rush attempts", "opp_pass_att": "Opponent pass attempts",
    "opp_turnovers": "Opponent turnovers", "unit": "offense / defense / special teams",
    "key": "Metric key", "label": "Display label", "group": "offense / defense / special / overall",
    "definition": "How it's computed", "higher_is_better": "Rank direction", "neutral": "Style stat (no good/bad coloring)",
    "rank_in_group": "Rank within the position group (estimate)", "ranking_stat": "Stat used to rank the group",
    "ranking_value": "Value of the ranking stat", "basis": "Games/totals the estimate is based on",
    "position_group": "offense / defense / special teams", "string": "1 = starter, 2 = backup, ...",
    "games_with_stats": "Earlier games with a stat line", "team_games": "Team games before the latest",
    "avg_involvement": "Pass att/5 + carries + receptions + tackles per game", "last_week_with_stats": "Latest week with a stat line",
    "consecutive_games_missing": "Straight games without a stat line", "note": "Explanation",
    "dataset": "Dataset name", "origin": "local file or Google Sheet", "rows": "Row count", "warnings": "Validation warnings",
})
STAT_CATS = {"passing": "Passing", "rushing": "Rushing", "receiving": "Receiving", "defensive": "Defense",
             "interceptions": "Interceptions (defense)", "fumbles": "Fumbles", "kicking": "Kicking", "punting": "Punting",
             "kickreturns": "Kick returns", "puntreturns": "Punt returns"}
STAT_ABBR = {"yds": "yards", "td": "touchdowns", "att": "attempts", "car": "carries", "rec": "receptions",
             "long": "longest", "avg": "average", "int": "interceptions", "pct": "percentage (fraction 0-1)",
             "no": "number", "tb": "touchbacks", "in_20": "inside the 20", "ypa": "yards per attempt",
             "ypc": "yards per carry", "ypr": "yards per reception", "ypp": "yards per punt", "tot": "total tackles",
             "solo": "solo tackles", "tfl": "tackles for loss", "sacks": "sacks", "pd": "passes defended",
             "qb_hur": "QB hurries", "fum": "fumbles", "lost": "fumbles lost", "comp": "completions",
             "completions": "completions", "qbr": "ESPN QBR", "pts": "points", "xpm": "extra points made",
             "xpa": "extra points attempted", "fgm": "field goals made", "fga": "field goals attempted",
             "fg_made": "field goals made", "fg_att": "field goals attempted", "xp_made": "extra points made",
             "xp_att": "extra points attempted"}


def describe(col: str, registry: dict[str, str]) -> str:
    cat, _, stat = col.partition("_")
    if cat in STAT_CATS and stat:
        return f"CFBD player stat: {STAT_CATS[cat]}, {STAT_ABBR.get(stat, stat)}"
    if col in COMMON:
        return COMMON[col]
    if col.startswith("usage_"):
        return f"CFBD usage rate: share of team plays involving the player ({col[6:].replace('_', ' ')})"
    if col.startswith("pts_from_"):
        return f"Points the `{col[9:]}` term adds to the predicted margin"
    if col in registry:
        return registry[col]
    for suffix, word in (("_conf_rank", "conference rank"), ("_rank", "national (FBS) rank")):
        if col.endswith(suffix) and (col[: -len(suffix)] in registry or col[: -len(suffix)] in COMMON):
            return f"{word.capitalize()} of `{col[: -len(suffix)]}` (1 = best; for style stats 1 = most)"
    return ""


def kind(values: list) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "—"
    v = vals[0]
    return {bool: "boolean", int: "number", float: "number", str: "text", dict: "object", list: "list"}.get(type(v), type(v).__name__)


def build() -> str:
    registry = {m.key: f"{m.label} ({m.unit}). {m.definition}" for m in METRICS + TENDENCY_METRICS}
    lines = ["# Data dictionary", "",
             "_Generated by `python -m pipeline.docs` from the files in `public/data/`. Every JSON file is "
             "`{\"meta\": {...}, \"data\": ...}`; `meta` holds the description, sources, fetch times "
             "(`data_as_of` = oldest input) and notes. CSV versions are in `public/data/csv/`._", ""]
    for path in sorted(config.PUBLIC_DATA.glob("*.json")):
        doc = json.loads(path.read_text())
        meta, data = doc["meta"], doc["data"]
        lines += [f"## `{path.stem}`", "", meta["description"], ""]
        srcs = sorted({s["source"] for s in meta["sources"]}) or ["derived"]
        lines.append(f"Sources: {', '.join(srcs)}. Rows: {meta['rows'] if meta['rows'] is not None else '—'}. "
                     f"CSV: {'yes' if (config.PUBLIC_CSV / f'{path.stem}.csv').exists() else 'no'}.")
        lines.append("")
        for n in meta["notes"]:
            lines.append(f"- {n}")
        if meta["notes"]:
            lines.append("")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            cols: OrderedDict[str, list] = OrderedDict()
            for r in data[:500]:
                for k, v in r.items():
                    cols.setdefault(k, []).append(v)
            lines += ["| Column | Type | Description |", "|---|---|---|"]
            for c, vals in cols.items():
                lines.append(f"| `{c}` | {kind(vals)} | {describe(c, registry)} |")
            lines.append("")
        elif isinstance(data, dict):
            lines += ["Object with keys: " + ", ".join(f"`{k}`" for k in data), ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    out = config.REPO_ROOT / "docs" / "data-dictionary.md"
    out.write_text(build())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
