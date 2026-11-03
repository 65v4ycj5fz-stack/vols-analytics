"""Project-wide settings. Override with environment variables where noted."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = REPO_ROOT / "public" / "data"
PUBLIC_CSV = PUBLIC_DATA / "csv"
PROCESSED = REPO_ROOT / "data" / "processed"
MANUAL = REPO_ROOT / "data" / "manual"

TEAM = os.environ.get("TEAM", "Tennessee")
CONFERENCE = os.environ.get("CONFERENCE", "SEC")


def default_season(today: date | None = None) -> int:
    """College football seasons start in late August; Jan-Jul belongs to the prior season."""
    today = today or date.today()
    return today.year if today.month >= 8 else today.year - 1


SEASON = int(os.environ.get("SEASON", default_season()))
# Seasons used for rating burn-in, calibration and backtesting (2019 onward gives two
# burn-in years before the five evaluated seasons 2021-2025).
FIRST_HISTORY_SEASON = int(os.environ.get("FIRST_HISTORY_SEASON", "2019"))
HISTORY_SEASONS = list(range(FIRST_HISTORY_SEASON, SEASON))
ALL_SEASONS = HISTORY_SEASONS + [SEASON]

# Cached responses for the in-progress season are re-fetched after this many hours.
CURRENT_TTL_HOURS = float(os.environ.get("CFBD_TTL_HOURS", "20"))
# A finished week's data is treated as final this many days after its last game.
FINAL_AFTER_DAYS = 4


def ttl_for_season(season: int) -> float | None:
    """Finished seasons never expire; the current season refreshes on a TTL."""
    return None if season < SEASON else CURRENT_TTL_HOURS
