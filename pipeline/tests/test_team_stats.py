import json

import numpy as np
import pandas as pd

from pipeline.publish import write_dataset
from pipeline.schemas import AdvSeasonRaw, BoxGameRaw, SeasonStatRaw, TeamRaw
from pipeline.tests.factories import game
from pipeline.transforms.games import games_frame
from pipeline.transforms.team_stats import Metric, add_ranks, box_frame, season_table


def test_ranks_respect_direction_ties_and_missing():
    df = pd.DataFrame({"team": list("ABCD"), "conference": ["X", "X", "Y", "Y"],
                       "good": [3.0, 1.0, 3.0, np.nan], "bad": [3.0, 1.0, 2.0, 5.0]})
    out = add_ranks(df, [Metric("good", "", "", True, "", ""), Metric("bad", "", "", False, "", "")])
    assert out["good_rank"].tolist()[:3] == [1, 3, 1] and pd.isna(out["good_rank"].iloc[3])
    assert out["bad_rank"].tolist() == [3, 1, 2, 4]
    assert out["bad_conf_rank"].tolist() == [2, 1, 1, 2]


def test_box_frame_parses_compound_fields():
    box = BoxGameRaw.model_validate({"id": 9, "teams": [{"team": "A", "homeAway": "home", "points": 21, "stats": [
        {"category": "completionAttempts", "stat": "20-31"}, {"category": "thirdDownEff", "stat": "5-12"},
        {"category": "totalPenaltiesYards", "stat": "7-55"}, {"category": "possessionTime", "stat": "31:05"},
        {"category": "totalYards", "stat": "402"}, {"category": "rushingAttempts", "stat": "40"}]}]})
    r = box_frame([box]).iloc[0]
    assert (r.pass_comp, r.pass_att, r.third_conv, r.third_att) == (20, 31, 5, 12)
    assert (r.penalties, r.penalty_yards, r.possession_sec, r.total_yards) == (7, 55, 1865, 402)


def _season_inputs():
    stats = [SeasonStatRaw(season=2025, team=t, statName=k, statValue=v) for t, d in {
        "A": {"games": 2, "totalYards": 800, "rushingAttempts": 60, "passAttempts": 40,
              "totalYardsOpponent": 500, "rushingAttemptsOpponent": 50, "passAttemptsOpponent": 50,
              "thirdDowns": 20, "thirdDownConversions": 10, "turnovers": 2, "turnoversOpponent": 5,
              "possessionTime": 3600},
        "B": {"games": 2, "totalYards": 500, "rushingAttempts": 50, "passAttempts": 50,
              "totalYardsOpponent": 800, "rushingAttemptsOpponent": 60, "passAttemptsOpponent": 40,
              "thirdDowns": 20, "thirdDownConversions": 5, "turnovers": 5, "turnoversOpponent": 2,
              "possessionTime": 3000},
    }.items() for k, v in d.items()]
    adv = [AdvSeasonRaw.model_validate({"season": 2025, "team": t, "offense": {"ppa": o, "plays": 100},
                                        "defense": {"ppa": -o, "havoc": {"total": 0.2}}})
           for t, o in (("A", 0.2), ("B", -0.1))]
    teams = [TeamRaw(id=i, school=t, conference="SEC") for i, t in enumerate("AB")]
    games = games_frame([game(1, "A", "B", 30, 20), game(2, "B", "A", 14, 28, date="2025-09-13T19:00:00.000Z")])
    return stats, adv, games, teams


def test_season_table_values_and_ranks():
    t = season_table(*_season_inputs()).set_index("team")
    assert t.loc["A", "off_ypp"] == 8.0 and t.loc["A", "def_ypp"] == 5.0
    assert t.loc["A", "points_pg"] == 29.0 and t.loc["A", "points_allowed_pg"] == 17.0
    assert t.loc["A", "third_down_pct"] == 0.5 and t.loc["A", "turnover_margin"] == 3
    assert t.loc["A", "sec_per_play"] == 36.0 and t.loc["A", "plays_pg"] == 50.0
    # defense EPA is "allowed": A's -0.2 beats B's +0.1
    assert t.loc["A", "off_epa_rank"] == 1 and t.loc["A", "def_epa_rank"] == 1
    assert t.loc["B", "def_epa"] == 0.1 and t.loc["B", "def_epa_rank"] == 2


def test_season_table_missing_inputs_are_null_not_zero():
    stats, adv, games, teams = _season_inputs()
    teams.append(TeamRaw(id=99, school="NoData", conference="SEC"))
    t = season_table(stats, adv, games, teams).set_index("team")
    assert pd.isna(t.loc["NoData", "off_epa"]) and pd.isna(t.loc["NoData", "points_pg"])
    assert pd.isna(t.loc["NoData", "off_epa_rank"])


def test_publish_writes_meta_nulls_and_csv(tmp_path):
    df = pd.DataFrame({"a": [1.0, np.nan], "b": ["x", None]})
    p = write_dataset("t", df, sources=[{"source": "CFBD", "endpoint": "/g", "fetched_at": "2025-01-02T00:00:00+00:00"},
                                         {"source": "CFBD", "endpoint": "/g", "fetched_at": "2025-01-01T00:00:00+00:00"}],
                      description="d", out_dir=tmp_path, csv_dir=tmp_path / "csv")
    j = json.loads(p.read_text())
    assert j["data"][1]["a"] is None and j["meta"]["rows"] == 2
    assert j["meta"]["data_as_of"] == "2025-01-01T00:00:00+00:00"
    assert j["meta"]["sources"] == [{"source": "CFBD", "endpoint": "/g", "fetched_at": "2025-01-01T00:00:00+00:00", "requests": 2}]
    assert (tmp_path / "csv" / "t.csv").read_text().splitlines()[0] == "a,b"
