"""Published ratings from CFBD: SP+, CFBD Elo and ESPN FPI (as relayed by CFBD)."""

from __future__ import annotations

from pipeline.cfbd import CFBDClient
from pipeline.schemas import EloRaw, FPIRaw, SPRaw
from pipeline.sources.base import Fetched, fetch


def sp_plus(client: CFBDClient, season: int) -> Fetched[SPRaw]:
    return fetch(client, "/ratings/sp", {"year": season}, SPRaw, season)


def elo(client: CFBDClient, season: int) -> Fetched[EloRaw]:
    return fetch(client, "/ratings/elo", {"year": season}, EloRaw, season)


def fpi(client: CFBDClient, season: int) -> Fetched[FPIRaw]:
    return fetch(client, "/ratings/fpi", {"year": season}, FPIRaw, season)
