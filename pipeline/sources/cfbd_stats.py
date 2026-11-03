"""Team season stats, advanced (PPA/EPA-based) stats, and per-game box scores."""

from __future__ import annotations

from pipeline.cfbd import CFBDClient
from pipeline.schemas import AdvGameRaw, AdvSeasonRaw, BoxGameRaw, GameRaw, SeasonStatRaw, TeamRaw
from pipeline.sources.base import Fetched, fetch
from pipeline.sources.cfbd_games import week_is_final


def fbs_teams(client: CFBDClient, season: int) -> Fetched[TeamRaw]:
    return fetch(client, "/teams/fbs", {"year": season}, TeamRaw, season)


def season_stats(client: CFBDClient, season: int) -> Fetched[SeasonStatRaw]:
    return fetch(client, "/stats/season", {"year": season}, SeasonStatRaw, season)


def season_advanced(client: CFBDClient, season: int) -> Fetched[AdvSeasonRaw]:
    return fetch(client, "/stats/season/advanced", {"year": season}, AdvSeasonRaw, season)


def game_advanced(client: CFBDClient, season: int) -> Fetched[AdvGameRaw]:
    """Per team-game advanced stats for every game in a season (regular season only)."""
    out = fetch(client, "/stats/game/advanced", {"year": season}, AdvGameRaw, season)
    post = fetch(client, "/stats/game/advanced", {"year": season, "seasonType": "postseason"},
                 AdvGameRaw, season)
    return out.extend(post)


def box_scores(client: CFBDClient, season: int, season_games: list[GameRaw]) -> Fetched[BoxGameRaw]:
    """Team box scores, one call per week that has completed FBS games.

    Weeks that are final are cached forever; the latest week refreshes on the season TTL.
    """
    out: Fetched[BoxGameRaw] = Fetched([])
    weeks = sorted({(g.seasonType, g.week) for g in season_games
                    if g.completed and "fbs" in (g.homeClassification, g.awayClassification)})
    for season_type, week in weeks:
        final = week_is_final(season_games, season, week, season_type)
        out.extend(fetch(client, "/games/teams",
                         {"year": season, "week": week, "seasonType": season_type},
                         BoxGameRaw, season, ttl_hours=None if final else "auto"))
    return out
