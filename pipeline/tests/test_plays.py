import numpy as np
import pandas as pd
import pytest

from model.situational import over_expected
from pipeline.schemas import PlayRaw
from pipeline.transforms.plays import plays_frame
from pipeline.transforms.tendencies import red_zone, split_table

_seq = iter(range(1, 10_000))


def play(play_type, text="", *, off="A", de="B", home="A", down=1, dist=10, ytg=75, yds=0, period=1,
         osc=0, dsc=0, game=1, drive="d1", ppa=0.0, mins=10):
    return PlayRaw.model_validate({
        "gameId": game, "id": str(game * 1000 + next(_seq)), "driveId": drive, "offense": off, "defense": de,
        "home": home, "away": de if home == off else off, "offenseScore": osc, "defenseScore": dsc,
        "period": period, "clock": {"minutes": mins, "seconds": 0}, "yardsToGoal": ytg, "down": down,
        "distance": dist, "yardsGained": yds, "playType": play_type, "playText": text, "ppa": ppa})


def test_classification_rules():
    df = plays_frame([
        play("Rush", "Shotgun J.Doe rush middle for 4 yards", yds=4),                     # 0 rush, fail (needs 5)
        play("Rush", "Kneel down by QB for loss of 1 yard", yds=-1),                      # 1 kneel -> excluded
        play("Pass Incompletion", "No Huddle-Shotgun QB pass incomplete, Spike"),         # 2 spike -> excluded
        play("Sack", "QB sacked by X for a loss of 7", yds=-7),                           # 3 pass + sack + havoc
        play("Fumble Recovery (Own)", "RB rush middle for 12 yards fumbled", yds=12),     # 4 rush, havoc
        play("Pass Reception", "QB pass complete deep left to WR for 25 yds", yds=25),    # 5 explosive pass, deep
        play("Pass Incompletion", "QB pass incomplete short right to WR broken up by CB"),# 6 PBU havoc
        play("Rush", "RB rush for 10 yards", yds=10, down=3, dist=10),                    # 7 success on 3rd, explosive
        play("Punt", "P punt 40 yards", down=4),                                          # 8 punt decision
        play("Rush", "QB rush for 2 yards", down=4, dist=1, yds=2),                       # 9 go + success
        play("Field Goal Good", "K 40 yd FG GOOD", down=4),                               # 10 fg
    ])
    assert df["is_rush"].tolist() == [1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0]
    assert df["is_pass"].tolist() == [0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 0]
    assert df.loc[3, "is_sack"] and df.loc[3, "havoc"] and df.loc[4, "havoc"] and df.loc[6, "havoc"]
    assert df.loc[0, "success"] == 0 and df.loc[7, "success"] == 1 and df.loc[9, "success"] == 1
    assert df.loc[5, "explosive"] == 1 and df.loc[5, "deep"] and df.loc[6, "depth_noted"] and not df.loc[6, "deep"]
    assert df.loc[7, "explosive"] == 1 and df.loc[0, "explosive"] == 0
    assert df.loc[0, "shotgun"] and df.loc[2, "no_huddle"]
    assert df["fourth_decision"].tolist()[8:] == ["punt", "go", "fg"]
    assert np.isnan(df.loc[1, "success"])  # non-scrimmage rows have no success value


def test_pre_play_margin_uses_score_before_the_snap():
    df = plays_frame([
        play("Passing Touchdown", "QB pass complete to WR for 30 yds TD", yds=30, osc=7, dsc=0),
        play("Kickoff", "kickoff", off="B", de="A", osc=0, dsc=7),
        play("Rush", "RB rush for 3", off="B", de="A", osc=0, dsc=7),
    ])
    # CFBD shows 7-0 on the TD play itself; the snap happened at 0-0
    assert df["margin"].tolist() == [0, -7, -7]


def test_garbage_time_flag():
    df = plays_frame([play("Rush", "x", osc=30, dsc=0, period=4), play("Rush", "x", osc=30, dsc=0, period=3)])
    # scores are post-play; second play's pre-snap margin is 30 -> garbage in Q3 (>28)
    assert df["garbage"].tolist() == [False, True]


def test_red_zone_trips():
    df = plays_frame([
        play("Rush", "r", ytg=15, drive="d1"), play("Rushing Touchdown", "r TD", ytg=5, drive="d1", yds=5),
        play("Rush", "r", ytg=18, drive="d2"), play("Field Goal Good", "fg", ytg=18, down=4, drive="d2"),
        play("Rush", "r", ytg=19, drive="d3"), play("Rush", "r", ytg=40, drive="d4"),
    ])
    rz = red_zone(df).set_index("drive_id")
    assert list(rz.index) == ["d1", "d2", "d3"]
    assert rz["td"].tolist() == [True, False, False] and rz["score"].tolist() == [True, True, False]


def test_split_table_counts_add_up():
    rows = [play("Rush", "r", down=d, dist=dist) for d, dist in [(1, 10), (2, 4), (3, 2), (1, 10)]]
    rows += [play("Pass Reception", "p", down=2, dist=8, yds=8)]
    df = plays_frame(rows)
    t = split_table(df, ["A"], {"A", "B"})
    off = t[(t.team == "A") & (t.side == "offense")]
    for split in ("down", "distance", "field_zone", "quarter"):
        assert off[off.split == split]["plays"].sum() == 5, split
    d2 = off[(off.split == "down") & (off.split_value == "2nd down")].iloc[0]
    assert d2.plays == 2 and d2.pass_rate == 0.5 and d2.small_sample
    assert set(t.team) == {"A", "FBS average"}


def test_over_expected_and_interval():
    df = pd.DataFrame({"team": ["A"] * 100, "pass": [1] * 60 + [0] * 40, "xpass": [0.5] * 100})
    r = over_expected(df, "pass", "xpass", ["team"]).iloc[0]
    assert r.over_expected == pytest.approx(0.10)
    assert r.ci95_high - r.over_expected == pytest.approx(1.96 * np.sqrt(25) / 100)
