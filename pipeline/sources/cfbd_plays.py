"""Play-by-play (one call per week, all teams) and AP poll rankings."""

from __future__ import annotations

from pipeline.cfbd import CFBDClient
from pipeline.schemas import GameRaw, PlayRaw, RankingWeekRaw
from pipeline.sources.base import Fetched, fetch
from pipeline.sources.cfbd_games import week_is_final


def plays(client: CFBDClient, season: int, season_games: list[GameRaw]) -> Fetched[PlayRaw]:
    """Every play for each week that has a completed FBS game. Final weeks never re-fetch."""
    out: Fetched[PlayRaw] = Fetched([])
    weeks = sorted({(g.seasonType, g.week) for g in season_games
                    if g.completed and "fbs" in (g.homeClassification, g.awayClassification)})
    for season_type, week in weeks:
        final = week_is_final(season_games, season, week, season_type)
        params = {"year": season, "week": week}
        if season_type != "regular":
            params["seasonType"] = season_type
        out.extend(fetch(client, "/plays", params, PlayRaw, season, ttl_hours=None if final else "auto"))
    return out


def rankings(client: CFBDClient, season: int) -> Fetched[RankingWeekRaw]:
    return fetch(client, "/rankings", {"year": season}, RankingWeekRaw, season)
