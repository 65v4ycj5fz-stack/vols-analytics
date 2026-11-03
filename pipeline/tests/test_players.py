from pipeline.schemas import PlayerGameRaw, PlayerSeasonStatRaw
from pipeline.tests.factories import game
from pipeline.transforms.games import games_frame
from pipeline.transforms.players import game_logs, season_stats


def test_season_stats_pivot_and_team_filter():
    rows = [PlayerSeasonStatRaw(season=2026, playerId="1", player="QB One", position="QB", team="Tennessee",
                                category=c, statType=t, stat=v)
            for c, t, v in [("passing", "YDS", "300"), ("passing", "TD", "3"), ("rushing", "CAR", "5")]]
    rows.append(PlayerSeasonStatRaw(season=2026, playerId="2", player="X", team="Other", category="passing",
                                    statType="YDS", stat="1"))
    df = season_stats(rows, {"Tennessee"})
    assert len(df) == 1 and df.loc[0, "passing_yds"] == 300 and df.loc[0, "rushing_car"] == 5


def test_game_logs_split_compound_stats():
    raw = PlayerGameRaw.model_validate({"id": 5, "teams": [
        {"team": "Tennessee", "categories": [
            {"name": "passing", "types": [{"name": "C/ATT", "athletes": [{"id": "1", "name": "QB", "stat": "20/30"}]},
                                          {"name": "YDS", "athletes": [{"id": "1", "name": "QB", "stat": "250"}]}]},
            {"name": "kicking", "types": [{"name": "XP", "athletes": [{"id": "9", "name": "K", "stat": "4/5"}]}]}]},
        {"team": "Kentucky", "categories": []}]})
    games = games_frame([game(5, "Tennessee", "Kentucky", 30, 10)])
    df = game_logs([raw], "Tennessee", games).set_index("player")
    assert (df.loc["QB", "passing_comp"], df.loc["QB", "passing_att"], df.loc["QB", "passing_yds"]) == (20, 30, 250)
    assert (df.loc["K", "kicking_xp_made"], df.loc["K", "kicking_xp_att"]) == (4, 5)
    assert (df["opponent"] == "Kentucky").all() and (df["week"] == 1).all()
