"""Write datasets to public/data/<name>.json (with provenance) and public/data/csv/<name>.csv."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline import config

SCHEMA_VERSION = 1


def _clean(v: Any) -> Any:
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) or math.isinf(v) else round(float(v), 6)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    return v


def records(df: pd.DataFrame, drop_nulls: bool = False) -> list[dict[str, Any]]:
    out = [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]
    if drop_nulls:  # wide, sparse tables: a missing key means null (the CSV keeps every column)
        out = [{k: v for k, v in r.items() if v is not None} for r in out]
    return out


def write_dataset(name: str, data: pd.DataFrame | list | dict, *, sources: list[dict[str, Any]],
                  description: str, season: int | None = None, notes: list[str] | None = None,
                  csv: bool = True, json_out: bool = True, drop_nulls: bool = False,
                  out_dir: Path | None = None, csv_dir: Path | None = None) -> Path:
    """Every published file carries when it was generated and which fetches it came from."""
    out_dir = out_dir or config.PUBLIC_DATA
    csv_dir = csv_dir or config.PUBLIC_CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    payload_data = records(data, drop_nulls) if isinstance(data, pd.DataFrame) else _clean(data)
    fetched = [s["fetched_at"] for s in sources if s.get("fetched_at")]
    meta = {
        "dataset": name,
        "description": description,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": season,
        "data_as_of": min(fetched) if fetched else None,  # oldest input = freshness floor
        "sources": _dedupe_sources(sources),
        "notes": notes or [],
        "rows": len(payload_data) if isinstance(payload_data, list) else None,
    }
    path = out_dir / f"{name}.json"
    if json_out:
        path.write_text(json.dumps({"meta": meta, "data": payload_data}, separators=(",", ":")))
    elif path.exists():
        path.unlink()
    if csv and isinstance(data, pd.DataFrame):
        csv_dir.mkdir(parents=True, exist_ok=True)
        data.to_csv(csv_dir / f"{name}.csv", index=False, float_format="%.6g")
    return path


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse per-week fetches of one endpoint into a single entry with the oldest fetch time."""
    merged: dict[tuple, dict[str, Any]] = {}
    for s in sources:
        key = (s.get("source"), s.get("endpoint"))
        cur = merged.get(key)
        if cur is None:
            merged[key] = {"source": s.get("source"), "endpoint": s.get("endpoint"),
                           "fetched_at": s.get("fetched_at"), "requests": 1}
        else:
            cur["requests"] += 1
            if s.get("fetched_at") and (cur["fetched_at"] is None or s["fetched_at"] < cur["fetched_at"]):
                cur["fetched_at"] = s["fetched_at"]
    return list(merged.values())
