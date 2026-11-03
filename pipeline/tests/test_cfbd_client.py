import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline.cfbd import BudgetExceeded, CacheMiss, CFBDClient, CFBDError, cache_key

SECRET = "test-secret-key-123"


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return self.responses.pop(0)


def client(tmp_path, responses=(), **kw):
    kw.setdefault("min_interval_s", 0)
    return CFBDClient(api_key=SECRET, cache_dir=tmp_path, session=FakeSession(responses), **kw)


def test_cache_key_is_order_independent():
    assert cache_key("/games", {"year": 1, "week": 2}) == cache_key("/games", {"week": 2, "year": 1})
    assert cache_key("/games", {"year": 1}) != cache_key("/games", {"year": 2})


def test_second_call_served_from_cache(tmp_path):
    c = client(tmp_path, [FakeResp(200, [{"a": 1}])])
    assert c.get("/games", {"year": 2025}) == [{"a": 1}]
    assert c.get("/games", {"year": 2025}) == [{"a": 1}]
    assert c.calls_made == 1


def test_bearer_header_and_none_params_dropped(tmp_path):
    c = client(tmp_path, [FakeResp(200, [])])
    c.get("/games", {"year": 2025, "week": None})
    url, params, headers = c.session.calls[0]
    assert url.endswith("/games") and params == {"year": 2025}
    assert headers["Authorization"] == f"Bearer {SECRET}"


def test_ttl_expiry_triggers_refetch(tmp_path):
    c = client(tmp_path, [FakeResp(200, [1]), FakeResp(200, [2])])
    c.get("/x", {}, ttl_hours=1)
    path = next(tmp_path.glob("x__*.json.gz"))
    rec = json.loads(gzip.decompress(path.read_bytes()))
    rec["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    path.write_bytes(gzip.compress(json.dumps(rec).encode()))
    assert c.get("/x", {}, ttl_hours=1) == [2]
    assert c.get("/x", {}, ttl_hours=None) == [2]  # never-expire uses cache
    assert c.calls_made == 2


def test_offline_mode_uses_cache_and_never_calls(tmp_path):
    client(tmp_path, [FakeResp(200, [7])]).get("/x", {})
    off = client(tmp_path, [], offline=True)
    assert off.get("/x", {}, ttl_hours=0) == [7]
    with pytest.raises(CacheMiss):
        off.get("/y", {})
    assert off.calls_made == 0


def test_budget_stops_new_calls_but_serves_stale_cache(tmp_path):
    c = client(tmp_path, [FakeResp(200, [1])], max_calls=1)
    c.get("/a", {})
    with pytest.raises(BudgetExceeded):
        c.get("/b", {})
    assert c.get("/a", {}, ttl_hours=0) == [1]  # stale, but budget is spent


def test_retries_on_429_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.cfbd.time.sleep", lambda s: None)
    c = client(tmp_path, [FakeResp(429, {}), FakeResp(200, [3])])
    assert c.get("/x", {}) == [3]
    assert c.calls_made == 2


def test_http_error_message_never_contains_key(tmp_path):
    c = client(tmp_path, [FakeResp(401, {"message": "bad"})])
    with pytest.raises(CFBDError) as exc:
        c.get("/x", {})
    assert SECRET not in str(exc.value) and "401" in str(exc.value)


def test_missing_key_errors_clearly(tmp_path):
    c = CFBDClient(api_key=None, cache_dir=tmp_path, session=FakeSession([]))
    with pytest.raises(CFBDError, match="CFBD_API_KEY"):
        c.get("/x", {})


def test_reads_legacy_uncompressed_cache(tmp_path):
    key = cache_key("/old", {"year": 1})
    (tmp_path / key.removesuffix(".gz")).write_text(json.dumps(
        {"endpoint": "/old", "params": {"year": 1}, "fetched_at": "2025-01-01T00:00:00+00:00", "data": [5]}))
    assert client(tmp_path, [], offline=True).get("/old", {"year": 1}) == [5]
