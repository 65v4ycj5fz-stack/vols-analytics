"""Games/results, betting lines and the season calendar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline.cfbd import CFBDClient
from pipeline.config import FINAL_AFTER_DAYS, SEASON
from pipeline.schemas import GameLinesRaw, GameRaw
from pipeline.sources.base import Fetched, fetch


def games(client: CFBDClient, season: int) -> Fetched[GameRaw]:
    """All games (every division) for the regular season and postseason."""
    return fetch(client, "/games", {"year": season, "seasonType": "both"}, GameRaw, season)


def lines(client: CFBDClient, season: int) -> Fetched[GameLinesRaw]:
    return fetch(client, "/lines", {"year": season, "seasonType": "both"}, GameLinesRaw, season)


def week_is_final(season_games: list[GameRaw], season: int, week: int, season_type: str,
                  now: datetime | None = None) -> bool:
    """True once every FBS game that week is complete and FINAL_AFTER_DAYS have passed.

    Used to stop re-fetching per-week data that can no longer change.
    """
    if season < SEASON:
        return True
    now = now or datetime.now(timezone.utc)
    wk = [g for g in season_games if g.week == week and g.seasonType == season_type
          and "fbs" in (g.homeClassification, g.awayClassification)]
    if not wk or not all(g.completed for g in wk):
        return False
    last = max(datetime.fromisoformat(g.startDate.replace("Z", "+00:00")) for g in wk)
    return now - last > timedelta(days=FINAL_AFTER_DAYS)
