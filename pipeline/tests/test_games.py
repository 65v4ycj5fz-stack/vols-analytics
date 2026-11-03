from datetime import datetime, timezone

import pytest

from pipeline.schemas import GameRaw, SchemaError, validate_rows
from pipeline.sources.cfbd_games import week_is_final
from pipeline.tests.factories import game, lines
from pipeline.transforms.games import consensus_lines, games_frame, record, team_schedule


def test_consensus_is_median_of_providers():
    df = consensus_lines([lines(1, "A", "B", -3.0, -4.0, -7.0)])
    assert df.loc[0, "spread_home"] == -4.0


def test_schedule_from_home_team_perspective_favorite_covers():
    g = games_frame([game(1, "Tennessee", "Kentucky", 31, 10)], [lines(1, "Tennessee", "Kentucky", -14.0)])
    s = team_schedule(g, "Tennessee").iloc[0]
    assert (s.site, s.result, s.margin, s.spread, s.ats) == ("home", "W", 21, -14.0, "covered")


def test_schedule_from_away_team_perspective_flips_spread():
    g = games_frame([game(1, "Alabama", "Tennessee", 24, 20)], [lines(1, "Alabama", "Tennessee", -7.0)])
    s = team_schedule(g, "Tennessee").iloc[0]
    # Tennessee was a 7-pt underdog (+7) and lost by 4 -> covered
    assert (s.site, s.result, s.spread, s.ats_margin, s.ats) == ("away", "L", 7.0, 3.0, "covered")


def test_push_neutral_site_and_unplayed_game():
    g = games_frame([
        game(1, "Tennessee", "X", 24, 21, neutral=True),
        game(2, "Y", "Tennessee", completed=False, date="2025-11-01T19:00:00.000Z"),
    ], [lines(1, "Tennessee", "X", -3.0), lines(2, "Y", "Tennessee", 2.5)])
    s = team_schedule(g, "Tennessee")
    assert s.loc[0, "site"] == "neutral" and s.loc[0, "ats"] == "push"
    assert s.loc[1, "result"] == "" and s.loc[1, "ats"] == "" and s.loc[1, "spread"] == -2.5


def test_missing_line_leaves_ats_blank():
    g = games_frame([game(1, "Tennessee", "X", 24, 21)], [])
    s = team_schedule(g, "Tennessee").iloc[0]
    assert s.ats == "" and s.spread != s.spread  # NaN


def test_record_counts_conference_games_separately():
    g = games_frame([game(1, "Tennessee", "A", 10, 0, conf=True),
                     game(2, "B", "Tennessee", 10, 0, date="2025-09-13T19:00:00.000Z")])
    s = team_schedule(g, "Tennessee")
    assert record(s) == {"wins": 1, "losses": 1, "ties": 0}
    assert record(s, conference_only=True) == {"wins": 1, "losses": 0, "ties": 0}


def test_schema_error_names_source_and_field():
    good = game(1, "A", "B").model_dump()
    with pytest.raises(SchemaError, match=r"^/games .*1 invalid row\(s\).*row 1: field 'homeTeam'"):
        validate_rows(GameRaw, [good, {**good, "homeTeam": None}], "/games {'year': 2025}")


def test_week_is_final_requires_completion_and_delay(monkeypatch):
    monkeypatch.setattr("pipeline.sources.cfbd_games.SEASON", 2025)
    gs = [game(1, "A", "B", 1, 0, date="2025-09-06T19:00:00.000Z"),
          game(2, "C", "D", completed=False, date="2025-09-06T19:00:00.000Z")]
    now = datetime(2025, 9, 20, tzinfo=timezone.utc)
    assert not week_is_final(gs, 2025, 1, "regular", now)
    gs[1] = game(2, "C", "D", 3, 0, date="2025-09-06T19:00:00.000Z")
    assert week_is_final(gs, 2025, 1, "regular", now)
    assert not week_is_final(gs, 2025, 1, "regular", datetime(2025, 9, 8, tzinfo=timezone.utc))
    assert week_is_final(gs, 2024, 1, "regular", now)  # past seasons are always final
