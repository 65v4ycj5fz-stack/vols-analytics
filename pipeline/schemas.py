"""Pydantic schemas for the CFBD fields the pipeline relies on.

Raw responses are validated on ingest so an upstream API change fails loudly with
the offending endpoint and row, instead of silently producing wrong numbers.
Only the fields we use are declared; extra fields are ignored.
"""

from __future__ import annotations

from typing import Any, Iterable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class _Raw(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class GameRaw(_Raw):
    id: int
    season: int
    week: int
    seasonType: str
    startDate: str
    startTimeTBD: bool | None = None
    completed: bool
    neutralSite: bool
    conferenceGame: bool
    homeId: int
    homeTeam: str
    homeClassification: str | None = None
    homeConference: str | None = None
    homePoints: int | None = None
    awayId: int
    awayTeam: str
    awayClassification: str | None = None
    awayConference: str | None = None
    awayPoints: int | None = None
    venue: str | None = None
    venueId: int | None = None
    homePregameElo: int | None = None
    awayPregameElo: int | None = None


class LineEntry(_Raw):
    provider: str
    spread: float | None = None
    spreadOpen: float | None = None
    overUnder: float | None = None


class GameLinesRaw(_Raw):
    id: int
    season: int
    week: int
    homeTeam: str
    awayTeam: str
    lines: list[LineEntry]


class _Split(_Raw):
    ppa: float | None = None
    successRate: float | None = None
    explosiveness: float | None = None


class AdvSide(_Raw):
    plays: float | None = None
    drives: float | None = None
    ppa: float | None = None
    successRate: float | None = None
    explosiveness: float | None = None
    stuffRate: float | None = None
    lineYards: float | None = None
    standardDowns: _Split | None = None
    passingDowns: _Split | None = None
    rushingPlays: _Split | None = None
    passingPlays: _Split | None = None


class AdvGameRaw(_Raw):
    gameId: int
    season: int
    week: int
    team: str
    opponent: str
    offense: AdvSide
    defense: AdvSide


class _Havoc(_Raw):
    total: float | None = None
    frontSeven: float | None = None
    db: float | None = None


class _FieldPos(_Raw):
    averageStart: float | None = None
    averagePredictedPoints: float | None = None


class AdvSeasonSide(AdvSide):
    totalOpportunies: float | None = None  # sic: CFBD's spelling
    pointsPerOpportunity: float | None = None
    fieldPosition: _FieldPos | None = None
    havoc: _Havoc | None = None


class AdvSeasonRaw(_Raw):
    season: int
    team: str
    conference: str | None = None
    offense: AdvSeasonSide
    defense: AdvSeasonSide


class SeasonStatRaw(_Raw):
    season: int
    team: str
    conference: str | None = None
    statName: str
    statValue: float


class TeamRaw(_Raw):
    id: int
    school: str
    abbreviation: str | None = None
    conference: str | None = None
    classification: str | None = None
    color: str | None = None


class _SPUnit(_Raw):
    rating: float | None = None
    ranking: int | None = None


class SPRaw(_Raw):
    year: int
    team: str
    conference: str | None = None
    rating: float | None = None
    ranking: int | None = None
    offense: _SPUnit | None = None
    defense: _SPUnit | None = None
    specialTeams: _SPUnit | None = None


class EloRaw(_Raw):
    year: int
    team: str
    elo: float | None = None


class FPIRaw(_Raw):
    year: int
    team: str
    fpi: float | None = None


class BoxStat(_Raw):
    category: str
    stat: str

    @field_validator("stat", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return "" if v is None else str(v)


class BoxTeam(_Raw):
    teamId: int | None = None
    team: str
    homeAway: str
    points: int | None = None
    stats: list[BoxStat]


class BoxGameRaw(_Raw):
    id: int
    teams: list[BoxTeam]


class _Clock(_Raw):
    minutes: int | None = None
    seconds: int | None = None


class PlayRaw(_Raw):
    gameId: int
    id: str
    driveId: str | None = None
    offense: str
    defense: str
    home: str | None = None
    away: str | None = None
    offenseConference: str | None = None
    defenseConference: str | None = None
    offenseScore: int | None = None
    defenseScore: int | None = None
    period: int
    clock: _Clock | None = None
    yardsToGoal: int | None = None
    down: int | None = None
    distance: int | None = None
    yardsGained: int | None = None
    scoring: bool | None = None
    playType: str
    playText: str | None = None
    ppa: float | None = None


class _PollRank(_Raw):
    rank: int
    school: str


class _Poll(_Raw):
    poll: str
    ranks: list[_PollRank]


class RankingWeekRaw(_Raw):
    season: int
    seasonType: str
    week: int
    polls: list[_Poll]


class PlayerSeasonStatRaw(_Raw):
    season: int
    playerId: str
    player: str
    position: str | None = None
    team: str
    conference: str | None = None
    category: str
    statType: str
    stat: str

    @field_validator("stat", "playerId", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return "" if v is None else str(v)


class _Usage(_Raw):
    overall: float | None = None
    pass_: float | None = Field(default=None, alias="pass")
    rush: float | None = None
    firstDown: float | None = None
    secondDown: float | None = None
    thirdDown: float | None = None
    standardDowns: float | None = None
    passingDowns: float | None = None


class PlayerUsageRaw(_Raw):
    season: int
    id: str
    name: str
    position: str | None = None
    team: str
    usage: _Usage

    @field_validator("id", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return str(v)


class RosterRaw(_Raw):
    id: str
    firstName: str | None = None
    lastName: str | None = None
    team: str
    weight: int | None = None
    height: int | None = None
    jersey: int | None = None
    year: int | None = None
    position: str | None = None
    homeCity: str | None = None
    homeState: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return str(v)


class _Athlete(_Raw):
    id: str
    name: str
    stat: str

    @field_validator("id", "stat", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return "" if v is None else str(v)


class _StatType(_Raw):
    name: str
    athletes: list[_Athlete]


class _StatCategory(_Raw):
    name: str
    types: list[_StatType]


class _PlayerGameTeam(_Raw):
    team: str
    homeAway: str | None = None
    points: int | None = None
    categories: list[_StatCategory]


class PlayerGameRaw(_Raw):
    id: int
    teams: list[_PlayerGameTeam]


class VenueRaw(_Raw):
    id: int
    name: str | None = None
    dome: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None


class SchemaError(ValueError):
    pass


M = TypeVar("M", bound=BaseModel)


def validate_rows(model: type[M], rows: Iterable[dict[str, Any]], source: str) -> list[M]:
    """Validate every row; raise one SchemaError naming the source and first bad rows."""
    out: list[M] = []
    errors: list[str] = []
    bad = 0
    for i, row in enumerate(rows):
        try:
            out.append(model.model_validate(row))
        except ValidationError as exc:
            bad += 1
            if len(errors) < 5:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first["loc"])
                errors.append(f"row {i}: field '{loc}': {first['msg']}")
    if errors:
        raise SchemaError(f"{source}: {bad} invalid row(s) -> " + "; ".join(errors))
    return out
