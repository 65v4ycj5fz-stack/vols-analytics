"""End-to-end rebuild from the local CFBD cache (no network). Skipped on a clean clone."""

import json

import pytest

from pipeline import config
from pipeline.cfbd import DEFAULT_CACHE_DIR, CFBDClient

pytestmark = pytest.mark.skipif(not any(DEFAULT_CACHE_DIR.glob("games__*.json*")),
                                reason="no cached CFBD responses; run `make data` first")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from pipeline import run
    out = tmp_path_factory.mktemp("public")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "PUBLIC_DATA", out)
    mp.setattr(config, "PUBLIC_CSV", out / "csv")
    mp.setattr(config, "PROCESSED", out / "processed")
    client = CFBDClient.from_env(offline=True)
    run.build(client)
    from model import run as model_run
    model_run.build()
    mp.undo()
    assert client.calls_made == 0
    return out


def load(out, name):
    return json.loads((out / f"{name}.json").read_text())


def test_every_dataset_has_provenance(built):
    for name in ("schedule", "team_season_stats", "team_game_stats", "ratings", "rating_trend", "results_history"):
        meta = load(built, name)["meta"]
        assert meta["sources"] and meta["data_as_of"], name
        assert (built / "csv" / f"{name}.csv").exists()


def test_schedule_consistency(built):
    rows = load(built, "schedule")["data"]
    assert rows and all(r["season"] == config.SEASON for r in rows)
    for r in rows:
        if r["completed"]:
            assert r["result"] in ("W", "L", "T")
            assert r["margin"] == r["points_for"] - r["points_against"]
        else:
            assert r["result"] == "" and r["points_for"] is None


def test_ranks_are_within_bounds(built):
    rows = load(built, "team_season_stats")["data"]
    n = len(rows)
    assert 120 <= n <= 140  # FBS size
    for r in rows:
        for k, v in r.items():
            if k.endswith("_rank") and v is not None:
                assert 1 <= v <= n, (r["team"], k, v)


def test_team_games_match_scores(built):
    rows = load(built, "team_game_stats")["data"]
    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    for pair in by_game.values():
        if len(pair) == 2:
            a, b = pair
            assert a["points_for"] == b["points_against"] and a["margin"] == -b["margin"]


def test_tendency_outputs_are_aggregated(built):
    splits = load(built, "tendency_splits")
    assert splits["meta"]["notes"] and all("text" not in r for r in splits["data"])
    summary = {r["team"]: r for r in load(built, "tendency_summary")["data"]}
    tn = summary[config.TEAM]
    assert tn["proe_ci_low"] <= tn["proe"] <= tn["proe_ci_high"]
    # down split play counts equal the team's non-garbage scrimmage plays
    off = [r for r in splits["data"] if r["team"] == config.TEAM and r["side"] == "offense"]
    assert sum(r["plays"] for r in off if r["split"] == "down") == sum(r["plays"] for r in off if r["split"] == "quarter")
    assert not list(built.glob("plays*"))  # raw plays never land in the public folder


def test_model_diagnostics_published(built):
    for m in load(built, "tendency_models")["data"]:
        assert m["cv_log_loss"] < m["baseline_log_loss"] and 0.5 < m["cv_auc"] <= 1


def test_backtest_report_is_honest(built):
    b = load(built, "backtest")["data"]
    ov = b["overall"]
    assert b["beats_market"] == (ov["model"]["mae_vs_actual"] < ov["market"]["mae_vs_actual"])
    assert ("NOT beat the market" in b["headline"]) == (not b["beats_market"])
    assert len(b["test_seasons"]) >= 5 and all(s["train_seasons"].endswith(str(s["season"] - 1)) for s in b["per_season"])
    assert ov["model"]["mae_vs_actual"] < ov["elo_only"]["mae_vs_actual"] + 1  # sanity, not a target


def test_predictions_carry_uncertainty(built):
    p = load(built, "predictions")
    assert any("80% interval" in n for n in p["meta"]["notes"])
    for r in p["data"]:
        assert 0 < r["win_prob"] < 1 and r["margin_p10"] < r["pred_margin"] < r["margin_p90"]
        parts = sum(v for k, v in r.items() if k.startswith("pts_from_"))
        assert parts == pytest.approx(r["pred_margin"], abs=1e-3)


def test_projection_factors_and_scores_add_up(built):
    p = load(built, "projections")["data"]
    for g in p["games"]:
        pr = g["projection"]
        assert sum(f["points"] for f in g["factors"]) == pytest.approx(pr["margin"], abs=1e-4)
        assert pr["team_points"] + pr["opp_points"] == pytest.approx(pr["total"])
        assert pr["team_points"] - pr["opp_points"] == pytest.approx(pr["margin"])
        assert any(a["key"] == "injuries" and a["source"] == "manual assumption" for a in g["adjustments"])
        assert 0 < pr["win_prob"] < 1 and pr["margin_p10"] < pr["margin"] < pr["margin_p90"]
    o = load(built, "season_outlook")["data"]
    assert sum(x["prob"] for x in o["win_distribution"]) == pytest.approx(1.0, abs=1e-6)
    assert o["n_sims"] >= 10000


def test_manual_datasets_published(built):
    status = {s["dataset"]: s for s in load(built, "manual_status")["data"]}
    assert set(status) == {"depth_chart", "injuries", "schemes", "opponent_scouting"}
    for name in status:
        assert (built / f"{name}.json").exists() and (built / "csv" / f"{name}.csv").exists()


# ---- provenance: published numbers must equal the raw API responses they came from ----

def _raw(endpoint, params):
    return CFBDClient.from_env(offline=True).get(endpoint, params)


def test_schedule_matches_raw_games_and_lines(built):
    import statistics
    games = {g["id"]: g for g in _raw("/games", {"year": config.SEASON, "seasonType": "both"})}
    lines = {g["id"]: g for g in _raw("/lines", {"year": config.SEASON, "seasonType": "both"})}
    rows = load(built, "schedule")["data"]
    assert rows
    for r in rows:
        g = games[r["game_id"]]
        home = g["homeTeam"] == config.TEAM
        assert r["opponent"] == (g["awayTeam"] if home else g["homeTeam"])
        if r["completed"]:
            assert r["points_for"] == (g["homePoints"] if home else g["awayPoints"])
            assert r["points_against"] == (g["awayPoints"] if home else g["homePoints"])
        spreads = [x["spread"] for x in lines.get(r["game_id"], {}).get("lines", []) if x["spread"] is not None]
        if spreads:
            med = statistics.median(spreads)
            assert r["spread"] == pytest.approx(med if home else -med)
        else:
            assert r["spread"] is None  # never invented when no book posted a line


def test_ratings_and_season_stats_match_raw(built):
    sp = {r["team"]: r["rating"] for r in _raw("/ratings/sp", {"year": config.SEASON})}
    fpi = {r["team"]: r["fpi"] for r in _raw("/ratings/fpi", {"year": config.SEASON})}
    adv = {r["team"]: r for r in _raw("/stats/season/advanced", {"year": config.SEASON})}
    stats = {}
    for r in _raw("/stats/season", {"year": config.SEASON}):
        stats.setdefault(r["team"], {})[r["statName"]] = r["statValue"]
    ratings = {r["team"]: r for r in load(built, "ratings")["data"]}
    season = {r["team"]: r for r in load(built, "team_season_stats")["data"]}
    for team in [config.TEAM, "Kentucky", "LSU", "Ohio State"]:
        if sp.get(team) is None:
            assert ratings[team]["sp_rating"] is None
        else:
            assert ratings[team]["sp_rating"] == pytest.approx(sp[team])
        assert ratings[team]["fpi"] == pytest.approx(fpi[team], abs=1e-5)
        s, a, st = season[team], adv[team], stats[team]
        assert s["off_epa"] == pytest.approx(a["offense"]["ppa"], abs=1e-5)
        assert s["def_success"] == pytest.approx(a["defense"]["successRate"], abs=1e-5)
        assert s["third_down_pct"] == pytest.approx(st["thirdDownConversions"] / st["thirdDowns"], abs=1e-5)
        assert s["turnover_margin"] == st["turnoversOpponent"] - st["turnovers"]


def test_player_stats_match_raw(built):
    raw = {}
    for r in _raw("/stats/player/season", {"year": config.SEASON}):
        if r["team"] == config.TEAM:
            raw[(r["playerId"], f"{r['category']}_{r['statType']}".lower())] = float(r["stat"])
    pub = [r for r in load(built, "player_season_stats")["data"] if r["team"] == config.TEAM]
    checked = 0
    for p in pub:
        for col in ("passing_yds", "rushing_yds", "receiving_yds", "defensive_tot"):
            if col in p:
                assert p[col] == pytest.approx(raw[(p["player_id"], col)])
                checked += 1
    assert checked > 20


def test_projection_inputs_match_published_ratings(built):
    """The Elo shown in each projection is the published Elo history (one source of truth)."""
    trend = {r["game_id"]: r["elo"] for r in load(built, "rating_trend")["data"]}
    games = load(built, "projections")["data"]["games"]
    done = [g for g in games if g["completed"]]
    for prev, nxt in zip(done, done[1:]):
        assert nxt["inputs"]["team_elo"] == pytest.approx(trend[prev["game_id"]], abs=1e-3)
