"""Synthetic test rows. Test-only: never written to public/data."""

from __future__ import annotations

from pipeline.schemas import GameLinesRaw, GameRaw


def game(id, home, away, hp=None, ap=None, *, week=1, season=2025, neutral=False, conf=False,
         completed=True, date="2025-09-06T19:00:00.000Z", hc="fbs", ac="fbs") -> GameRaw:
    return GameRaw.model_validate({
        "id": id, "season": season, "week": week, "seasonType": "regular", "startDate": date,
        "completed": completed, "neutralSite": neutral, "conferenceGame": conf,
        "homeId": hash(home) % 10000, "homeTeam": home, "homeClassification": hc, "homeConference": "SEC",
        "homePoints": hp, "awayId": hash(away) % 10000, "awayTeam": away, "awayClassification": ac,
        "awayConference": "SEC", "awayPoints": ap,
    })


def lines(id, home, away, *spreads, week=1) -> GameLinesRaw:
    return GameLinesRaw.model_validate({
        "id": id, "season": 2025, "week": week, "homeTeam": home, "awayTeam": away,
        "lines": [{"provider": f"book{i}", "spread": s, "overUnder": 50.0} for i, s in enumerate(spreads)],
    })
