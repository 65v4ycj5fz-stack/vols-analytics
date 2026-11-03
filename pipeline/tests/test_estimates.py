import pandas as pd

from model.adjustments import STATUS_PROB_OUT, injury_points
from pipeline.manual import SPECS, validate_text
from pipeline.transforms.estimates import absence_alerts, estimated_depth, tennessee_usage

ROSTER = pd.DataFrame([
    {"player_id": "1", "position": "QB", "jersey": 1}, {"player_id": "2", "position": "QB", "jersey": 2},
    {"player_id": "3", "position": "RB", "jersey": 3}, {"player_id": "4", "position": "DB", "jersey": 4},
    {"player_id": "5", "position": "OL", "jersey": 70},
])


def log(week, pid, name, **stats):
    return {"week": week, "player_id": pid, "player": name, **stats}


def test_depth_ranks_by_recent_usage_and_skips_ol():
    logs = pd.DataFrame([
        log(1, "1", "Old Starter", passing_att=40), log(2, "1", "Old Starter", passing_att=35),
        log(3, "2", "New QB", passing_att=30), log(4, "2", "New QB", passing_att=31), log(5, "2", "New QB", passing_att=33),
        log(5, "1", "Old Starter", passing_att=2),
        log(5, "3", "Back", rushing_car=20), log(5, "4", "Safety", defensive_tot=9, defensive_tfl=1),
        log(5, "5", "Tackle"),  # OL never has stats
    ])
    usage, note = tennessee_usage(logs, ROSTER)
    assert "weeks 3, 4, 5" in note
    rows = estimated_depth(usage, "Tennessee", note, "2026-11-03")
    qbs = [(r["player"], r["string"]) for r in rows if r["position"] == "QB"]
    assert qbs == [("New QB", 1), ("Old Starter", 2)]  # recency, not season totals
    assert not any(r["player"] == "Tackle" for r in rows)
    db = next(r for r in rows if r["position"] == "DB")
    assert db["ranking_value"] == 9 + 2 * 1 and db["source"] == "estimate from CFBD box scores"


def test_absence_alert_requires_regular_role_and_latest_absence():
    rows = []
    for w in range(1, 6):
        rows.append(log(w, "3", "Back", rushing_car=15))
        if w < 5:
            rows.append(log(w, "1", "Starter QB", passing_att=30))   # misses week 5
        if w in (1, 5):
            rows.append(log(w, "2", "Backup", passing_att=3))        # not regular
    alerts = absence_alerts(pd.DataFrame(rows), ROSTER, "Tennessee")
    assert list(alerts["player"]) == ["Starter QB"]
    a = alerts.iloc[0]
    assert (a.games_with_stats, a.team_games, a.last_week_with_stats, a.consecutive_games_missing) == (4, 4, 4, 1)
    assert "Not an injury report" in a.note


def test_no_alert_when_player_returns():
    rows = [log(w, "1", "QB", passing_att=30) for w in (1, 2, 3, 5)] + [log(w, "3", "RB", rushing_car=10) for w in range(1, 6)]
    assert absence_alerts(pd.DataFrame(rows), ROSTER, "Tennessee").empty


def test_sec_status_definitions_and_game_time_decision():
    assert STATUS_PROB_OUT["probable"] == 0.25 and STATUS_PROB_OUT["doubtful"] == 0.75
    head = ",".join(next(s for s in SPECS if s.name == "injuries").columns)
    l = validate_text(next(s for s in SPECS if s.name == "injuries"),
                      head + "\nTennessee,P One,QB,Game-Time Decision,,2026-11-07,,,4,2026-11-07,SEC availability report\n")
    assert l.rows[0]["status"] == "game-time decision"
    pts, _ = injury_points(pd.DataFrame(l.rows), None, "Tennessee", points_per_impact=0.6)
    assert pts == 4 * 0.6 * 0.5 * 0.5


def test_estimated_depth_weights_injuries_when_no_manual_chart():
    inj = pd.DataFrame([{"team": "Tennessee", "player": "New QB", "position": "QB", "status": "out", "impact_rating": 5}])
    est = pd.DataFrame([{"team": "Tennessee", "player": "New QB", "string": 1}])
    assert injury_points(inj, est, "Tennessee")[0] == 5 * 0.6 * 1.0 * 1.0  # starter weight from the estimate
