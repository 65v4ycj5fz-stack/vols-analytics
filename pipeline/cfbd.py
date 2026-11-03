"""Cached, budget-aware client for the CollegeFootballData.com (CFBD) API.

The free CFBD tier allows 1,000 calls per month, so every response is written to
``data/cache`` and reused. Responses for finished seasons never expire; responses
for the in-progress season expire after ``ttl_hours``. A per-run call budget
(``CFBD_MAX_CALLS``) stops a runaway refresh from draining the monthly quota.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.collegefootballdata.com"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache" / "cfbd"


class CFBDError(RuntimeError):
    pass


class BudgetExceeded(CFBDError):
    pass


class CacheMiss(CFBDError):
    pass


def load_dotenv_if_present() -> None:
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cache_key(endpoint: str, params: dict[str, Any]) -> str:
    canonical = json.dumps({"e": endpoint, "p": {k: params[k] for k in sorted(params)}}, sort_keys=True)
    slug = endpoint.strip("/").replace("/", "_") or "root"
    return f"{slug}__{hashlib.sha1(canonical.encode()).hexdigest()[:16]}.json.gz"


@dataclass
class CFBDClient:
    api_key: str | None = None
    cache_dir: Path = DEFAULT_CACHE_DIR
    max_calls: int = 60
    offline: bool = False
    min_interval_s: float = 0.4
    base_url: str = BASE_URL
    send_auth: bool = True
    session: requests.Session = field(default_factory=requests.Session)
    calls_made: int = 0
    _last_call: float = 0.0

    @classmethod
    def from_env(cls, **overrides: Any) -> "CFBDClient":
        load_dotenv_if_present()
        kwargs: dict[str, Any] = {
            "api_key": os.environ.get("CFBD_API_KEY") or None,
            "max_calls": int(os.environ.get("CFBD_MAX_CALLS", "60")),
            "offline": os.environ.get("CFBD_OFFLINE", "") == "1",
        }
        if os.environ.get("CFBD_CACHE_DIR"):
            kwargs["cache_dir"] = Path(os.environ["CFBD_CACHE_DIR"])
        kwargs.update(overrides)
        return cls(**kwargs)

    # -- cache -----------------------------------------------------------------
    def _path(self, endpoint: str, params: dict[str, Any]) -> Path:
        return Path(self.cache_dir) / cache_key(endpoint, params)

    def read_cache(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
        path = self._path(endpoint, params)
        if path.exists():
            return json.loads(gzip.decompress(path.read_bytes()))
        legacy = path.with_suffix("")  # uncompressed .json from older runs
        if legacy.exists():
            return json.loads(legacy.read_text())
        return None

    def _write_cache(self, endpoint: str, params: dict[str, Any], data: Any) -> dict[str, Any]:
        path = self._path(endpoint, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "endpoint": endpoint,
            "params": params,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": data,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(json.dumps(record).encode(), compresslevel=6))
        tmp.replace(path)
        return record

    @staticmethod
    def _is_fresh(record: dict[str, Any], ttl_hours: float | None) -> bool:
        if ttl_hours is None:
            return True
        fetched = datetime.fromisoformat(record["fetched_at"])
        age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        return age_h < ttl_hours

    # -- network ---------------------------------------------------------------
    def get_record(self, endpoint: str, params: dict[str, Any] | None = None,
                   ttl_hours: float | None = None) -> dict[str, Any]:
        """Return ``{"data", "fetched_at", ...}``; ``ttl_hours=None`` means never expire."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cached = self.read_cache(endpoint, params)
        if cached is not None and (self.offline or self._is_fresh(cached, ttl_hours)):
            return cached
        if self.offline:
            raise CacheMiss(f"offline mode and no cache for {endpoint} {params}")
        if self.send_auth and not self.api_key:
            if cached is not None:
                return cached  # stale is better than nothing; fetched_at is shown in the UI
            raise CFBDError("CFBD_API_KEY is not set (see .env.example)")
        if self.calls_made >= self.max_calls:
            if cached is not None:
                return cached
            raise BudgetExceeded(
                f"per-run CFBD call budget ({self.max_calls}) exhausted before {endpoint} {params}; "
                "raise CFBD_MAX_CALLS or rerun later (cache is kept)"
            )
        data = self._fetch(endpoint, params)
        return self._write_cache(endpoint, params, data)

    def get(self, endpoint: str, params: dict[str, Any] | None = None,
            ttl_hours: float | None = None) -> Any:
        return self.get_record(endpoint, params, ttl_hours)["data"]

    def _fetch(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = self.base_url + endpoint
        headers = {"Accept": "application/json"}
        if self.send_auth:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(4):
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            self.calls_made += 1
            resp = self.session.get(url, params=params, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                per_minute = resp.status_code == 429 and "minute" in resp.text.lower()
                time.sleep(65 if per_minute else 2 ** attempt * 2)
                continue
            # never echo headers (they contain the key)
            raise CFBDError(f"{self.base_url} {endpoint} {params} -> HTTP {resp.status_code}: {resp.text[:200]}")
        raise CFBDError(f"CFBD {endpoint} failed after retries")

    def info(self) -> dict[str, Any]:
        """Quota info; always live (not cached), counts as a call."""
        return self._fetch("/info", {})
