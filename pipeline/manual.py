"""Manual datasets: schemas, validation, and loading (local CSV or a published Google Sheet).

Run ``python -m pipeline.manual`` (or ``make validate``) to check the files and get
plain-English error messages with spreadsheet row numbers. The main pipeline runs
the same validation and stops the build if anything is wrong.

To edit in Google Sheets instead of the repo, publish each tab as CSV
(File > Share > Publish to web > CSV) and set the matching environment variable or
GitHub repository variable, e.g. SHEET_INJURIES_URL. The sheet then wins over the local file.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from pipeline import config

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _blank_to_none(v):
    return None if isinstance(v, str) and v.strip() == "" else v


class _Manual(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    last_updated: date
    source: str

    @field_validator("*", mode="before")
    @classmethod
    def _blanks(cls, v):
        return _blank_to_none(v)

    @field_validator("last_updated", mode="before")
    @classmethod
    def _date(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("is required (YYYY-MM-DD)")
        if isinstance(v, str) and not ISO_DATE.match(v):
            raise ValueError(f"'{v}' is not a date in YYYY-MM-DD format")
        return v

    @field_validator("source")
    @classmethod
    def _source(cls, v):
        if not v:
            raise ValueError("is required: say where this came from (URL, 'team release', 'own observation', ...)")
        return v


class DepthChartRow(_Manual):
    team: str
    position_group: Literal["offense", "defense", "special teams"]
    position: str
    string: int
    player: str
    jersey: int | None = None
    # named class_year in code; the CSV column is "class"
    class_: Literal["FR", "SO", "JR", "SR", "GR", "RS-FR", "RS-SO", "RS-JR", "RS-SR"] | None = None
    height: str | None = None
    weight: int | None = None
    snap_pct: float | None = None
    notes: str | None = None

    @field_validator("position_group", mode="before")
    @classmethod
    def _grp(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("position", mode="before")
    @classmethod
    def _pos(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("class_", mode="before")
    @classmethod
    def _cls(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("string")
    @classmethod
    def _string(cls, v):
        if not 1 <= v <= 4:
            raise ValueError("must be 1 (starter), 2, 3 or 4")
        return v

    @field_validator("height")
    @classmethod
    def _height(cls, v):
        if v is not None and not re.match(r"^\d-\d{1,2}$", v):
            raise ValueError(f"'{v}' should look like 6-2 (feet-inches)")
        return v

    @field_validator("snap_pct")
    @classmethod
    def _snap(cls, v):
        if v is not None and not 0 <= v <= 100:
            raise ValueError("must be between 0 and 100 (percent)")
        return v


STATUSES = ("out", "doubtful", "questionable", "game-time decision", "probable", "available")


class InjuryRow(_Manual):
    team: str
    player: str
    position: str
    status: Literal["out", "doubtful", "questionable", "game-time decision", "probable", "available"]
    injury_area: str | None = None
    date_reported: date
    expected_return: str | None = None
    source_url: str | None = None
    impact_rating: int

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        if isinstance(v, str):
            v = " ".join(v.strip().lower().replace("-", " ").split())  # "Game-Time Decision" -> "game time decision"
            return "game-time decision" if v in ("game time decision", "gtd") else v
        return v

    @field_validator("position", mode="before")
    @classmethod
    def _pos(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("date_reported", mode="before")
    @classmethod
    def _rep(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("is required (YYYY-MM-DD)")
        if isinstance(v, str) and not ISO_DATE.match(v):
            raise ValueError(f"'{v}' is not a date in YYYY-MM-DD format")
        return v

    @field_validator("impact_rating")
    @classmethod
    def _impact(cls, v):
        if not 0 <= v <= 5:
            raise ValueError("must be a whole number from 0 (no impact) to 5 (star starter)")
        return v

    @field_validator("source_url")
    @classmethod
    def _url(cls, v):
        if v is not None and not re.match(r"^https?://", v):
            raise ValueError("must start with http:// or https://")
        return v


class SchemeRow(_Manual):
    team: str
    unit: Literal["offense", "defense", "special teams"]
    base_scheme: str
    tempo: str | None = None
    personnel_groupings: str | None = None
    coverage_shells: str | None = None
    front: str | None = None
    blitz_style: str | None = None
    key_concepts: str | None = None
    notes: str | None = None

    @field_validator("unit", mode="before")
    @classmethod
    def _unit(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


@dataclass(frozen=True)
class ManualSpec:
    name: str
    model: type[_Manual]
    columns: list[str]
    sheet_env: str
    description: str


SCHEME_COLS = ["team", "unit", "base_scheme", "tempo", "personnel_groupings", "coverage_shells", "front",
               "blitz_style", "key_concepts", "notes", "last_updated", "source"]
SPECS = [
    ManualSpec("depth_chart", DepthChartRow,
               ["team", "position_group", "position", "string", "player", "jersey", "class", "height", "weight",
                "snap_pct", "notes", "last_updated", "source"], "SHEET_DEPTH_CHART_URL",
               "Depth chart (manual entry)"),
    ManualSpec("injuries", InjuryRow,
               ["team", "player", "position", "status", "injury_area", "date_reported", "expected_return",
                "source_url", "impact_rating", "last_updated", "source"], "SHEET_INJURIES_URL",
               "Injury report (manual entry)"),
    ManualSpec("schemes", SchemeRow, SCHEME_COLS, "SHEET_SCHEMES_URL", "Tennessee scheme notes (manual entry)"),
    ManualSpec("opponent_scouting", SchemeRow, SCHEME_COLS, "SHEET_OPPONENT_SCOUTING_URL",
               "Opponent scheme notes (manual entry)"),
]


class ManualDataError(ValueError):
    pass


@dataclass
class Loaded:
    spec: ManualSpec
    rows: list[dict]
    origin: str           # "local file" or "Google Sheet"
    warnings: list[str]


def read_text(spec: ManualSpec, manual_dir: Path) -> tuple[str, str, list[str]]:
    url = os.environ.get(spec.sheet_env, "").strip()
    path = manual_dir / f"{spec.name}.csv"
    if url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.content.decode("utf-8-sig"), "Google Sheet", []
        except requests.RequestException as exc:
            warn = f"{spec.name}: could not download the Google Sheet ({exc.__class__.__name__}); using {path.name}"
            return path.read_text(encoding="utf-8-sig") if path.exists() else "", "local file", [warn]
    return (path.read_text(encoding="utf-8-sig") if path.exists() else ""), "local file", []


def validate_text(spec: ManualSpec, text: str, origin: str = "local file",
                  known_teams: set[str] | None = None) -> Loaded:
    errors: list[str] = []
    warnings: list[str] = []
    where = f"{spec.name}.csv" if origin == "local file" else f"{spec.name} (Google Sheet)"
    if not text.strip():
        raise ManualDataError(f"{where}: file is empty. It must at least have the header row:\n  {','.join(spec.columns)}")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in spec.columns if c not in header]
    extra = [c for c in header if c not in spec.columns]
    if missing or extra:
        msg = f"{where}: the header row doesn't match the template."
        if missing:
            msg += f"\n  Missing column(s): {', '.join(missing)}"
        if extra:
            msg += f"\n  Unexpected column(s): {', '.join(extra)} (check spelling; extra columns aren't allowed)"
        msg += f"\n  Expected: {','.join(spec.columns)}"
        raise ManualDataError(msg)
    rows = []
    for i, raw in enumerate(reader):
        line = i + 2  # spreadsheet row number (row 1 is the header)
        raw = {k.strip(): v for k, v in raw.items() if k is not None}
        if not any((v or "").strip() for v in raw.values()):
            continue  # ignore fully blank lines
        data = {("class_" if k == "class" else k): v for k, v in raw.items()}
        try:
            obj = spec.model.model_validate(data)
        except ValidationError as exc:
            for e in exc.errors():
                col = str(e["loc"][0]).replace("class_", "class") if e["loc"] else "?"
                msg = e["msg"].removeprefix("Value error, ")
                if e["type"] == "missing" or (e["type"].endswith("_type") and raw.get(col, "").strip() == ""):
                    msg = "is required but empty"
                elif e["type"] == "literal_error":
                    msg = f"'{raw.get(col)}' is not allowed. {e['msg'].replace('Input should be', 'Use one of:')}"
                elif e["type"] in ("int_parsing", "float_parsing"):
                    msg = f"'{raw.get(col)}' is not a number"
                errors.append(f"  row {line}, column '{col}': {msg}")
            continue
        row = obj.model_dump()
        if "class_" in row:
            row["class"] = row.pop("class_")
        if known_teams and row["team"] not in known_teams:
            warnings.append(f"{where} row {line}: team '{row['team']}' doesn't match any CFBD team name "
                            f"(use the exact name, e.g. 'Tennessee', 'Texas A&M'); the row won't link to model data")
        rows.append(row)
    if errors:
        raise ManualDataError(f"{where}: {len(errors)} problem(s) found\n" + "\n".join(errors[:40])
                              + ("\n  ..." if len(errors) > 40 else ""))
    if spec.name == "depth_chart":
        seen: dict[tuple, int] = {}
        for r in rows:
            k = (r["team"], r["position"], r["string"])
            seen[k] = seen.get(k, 0) + 1
        for (t, p, s), n in seen.items():
            if n > 1 and p not in {"WR", "CB", "S", "DE", "DT", "LB", "OL", "DL", "EDGE", "OLB", "ILB"}:
                warnings.append(f"{where}: {n} players listed as {t} {p} string {s} (OK for co-starters, otherwise check)")
    return Loaded(spec, rows, origin, warnings)


def load_all(manual_dir: Path | None = None, known_teams: set[str] | None = None) -> dict[str, Loaded]:
    """Validate every manual dataset; raise ManualDataError listing every file's problems."""
    manual_dir = manual_dir or config.MANUAL
    out, problems = {}, []
    for spec in SPECS:
        text, origin, warns = read_text(spec, manual_dir)
        try:
            loaded = validate_text(spec, text, origin, known_teams)
            loaded.warnings[:0] = warns
            out[spec.name] = loaded
        except ManualDataError as exc:
            problems.append(str(exc))
    if problems:
        raise ManualDataError("Manual data needs fixing before the site can be built:\n\n" + "\n\n".join(problems)
                              + "\n\nSee data/manual/README.md for the allowed values in each column.")
    return out


def seed_depth_chart(path: Path | None = None) -> Path:
    """Write depth_chart_seed.csv from the CFBD roster (positions, jerseys, sizes) for a person to
    finish: fill in position_group/string, delete players who aren't on the depth chart, then copy
    the rows into depth_chart.csv. The string column is left blank on purpose."""
    import json
    roster = json.loads((config.PUBLIC_DATA / "roster.json").read_text())["data"]
    path = path or config.MANUAL / "depth_chart_seed.csv"
    years = {1: "FR", 2: "SO", 3: "JR", 4: "SR", 5: "GR"}
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(SPECS[0].columns)
        for r in sorted(roster, key=lambda r: (r.get("position") or "", r.get("jersey") or 99)):
            h = r.get("height_in")
            w.writerow([r["team"], "", r.get("position") or "", "", r["player"], r.get("jersey") or "",
                        years.get(r.get("class_year"), ""), f"{h // 12}-{h % 12}" if h else "", r.get("weight_lb") or "",
                        "", "", date.today().isoformat(), "CFBD roster; depth order entered by hand"])
    return path


def main() -> int:
    if sys.argv[1:] == ["seed-depth"]:
        print(f"wrote {seed_depth_chart()}")
        return 0
    try:
        loaded = load_all()
    except ManualDataError as exc:
        print(exc)
        return 1
    for name, l in loaded.items():
        print(f"OK  {name}: {len(l.rows)} row(s) from {l.origin}")
        for w in l.warnings:
            print(f"    warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
