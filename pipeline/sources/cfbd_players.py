"""Player season stats, usage, per-game box scores and roster."""

from __future__ import annotations

from pipeline.cfbd import CFBDClient
from pipeline.schemas import GameRaw, PlayerGameRaw, PlayerSeasonStatRaw, PlayerUsageRaw, RosterRaw
from pipeline.sources.base import Fetched, fetch
from pipeline.sources.cfbd_games import week_is_final


def season_stats(client: CFBDClient, season: int) -> Fetched[PlayerSeasonStatRaw]:
    """All FBS players' season totals (one call)."""
    return fetch(client, "/stats/player/season", {"year": season}, PlayerSeasonStatRaw, season)


def usage(client: CFBDClient, season: int) -> Fetched[PlayerUsageRaw]:
    return fetch(client, "/player/usage", {"year": season}, PlayerUsageRaw, season)


def roster(client: CFBDClient, season: int, team: str) -> Fetched[RosterRaw]:
    return fetch(client, "/roster", {"year": season, "team": team}, RosterRaw, season)


def game_logs(client: CFBDClient, season: int, team: str, season_games: list[GameRaw]) -> Fetched[PlayerGameRaw]:
    """Per-game player box scores for ``team``: one call per game week."""
    out: Fetched[PlayerGameRaw] = Fetched([])
    for g in season_games:
        if not g.completed or team not in (g.homeTeam, g.awayTeam):
            continue
        final = week_is_final(season_games, season, g.week, g.seasonType)
        params = {"year": season, "week": g.week, "team": team}
        if g.seasonType != "regular":
            params["seasonType"] = g.seasonType
        out.extend(fetch(client, "/games/players", params, PlayerGameRaw, season,
                         ttl_hours=None if final else "auto"))
    return out
