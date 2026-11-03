from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pipeline.cfbd import CFBDClient
from pipeline.config import ttl_for_season
from pipeline.schemas import validate_rows

T = TypeVar("T")


@dataclass
class Fetched(Generic[T]):
    """Validated rows plus where and when they came from (shown in the UI)."""

    rows: list[T]
    sources: list[dict[str, Any]] = field(default_factory=list)

    def extend(self, other: "Fetched[T]") -> "Fetched[T]":
        self.rows.extend(other.rows)
        self.sources.extend(other.sources)
        return self


def fetch(client: CFBDClient, endpoint: str, params: dict[str, Any], model: type[T],
          season: int, ttl_hours: float | None | str = "auto") -> Fetched[T]:
    ttl = ttl_for_season(season) if ttl_hours == "auto" else ttl_hours
    record = client.get_record(endpoint, params, ttl_hours=ttl)
    rows = validate_rows(model, record["data"], f"{endpoint} {params}")
    src = {"source": "CollegeFootballData.com", "endpoint": endpoint, "params": params,
           "fetched_at": record["fetched_at"]}
    return Fetched(rows, [src])
