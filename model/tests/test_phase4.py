import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from model.adjustments import ResidualFit, injury_points
from model.context_features import pace_pregame, turnover_margin_pregame
from model.margin import TotalModel
from model.simulate import estimate_tau, season_outlook, simulate_game, simulate_season, summarize_game
from pipeline.transforms.context import haversine_km, home_venues, rest_days


def _games():
    t0 = pd.Timestamp("2025-09-06", tz="UTC")
    rows = [(1, "A", "B", 0), (2, "B", "A", 7), (3, "A", "C", 21), (4, "C", "A", 35)]
    return pd.DataFrame([{"game_id": g, "season": 2025, "start_date": t0 + pd.Timedelta(days=d), "home_team": h,
                          "away_team": a, "completed": g < 4, "neutral_site": False, "venue_id": 10 if h == "A" else 20}
                         for g, h, a, d in rows])


def test_haversine_knoxville_to_baton_rouge():
    assert haversine_km(35.955, -83.925, 30.412, -91.184) == pytest.approx(905, abs=15)


def test_rest_days_and_home_venue():
    g = _games()
    r = rest_days(g).set_index(["game_id", "team"])["rest_days"]
    assert np.isnan(r[(1, "A")]) and r[(2, "A")] == 7 and r[(3, "A")] == 14 and r[(4, "A")] == 14
    hv = home_venues(g).set_index("team")["home_venue_id"]
    assert hv["A"] == 10 and hv["B"] == 20


def test_turnover_pregame_uses_only_earlier_games():
    g = _games()
    box = pd.DataFrame({"game_id": [1, 1, 2, 2, 3, 3], "team": ["A", "B", "B", "A", "A", "C"],
                        "turnovers": [0, 3, 1, 1, 2, 0], "season": 2025})
    to = turnover_margin_pregame(g, box)
    # game 1: no prior games -> prior 0; game 3 (A): after g1 (+3) and g2 (0): (3 + 0 + 4*0) / (2 + 4)
    assert to.loc[1, "to_pre_home"] == 0
    assert to.loc[3, "to_pre_home"] == pytest.approx(3 / 6)
    # game 4 is unplayed: A has 3 completed games: +3, 0, -2 -> 1/7
    assert to.loc[4, "to_pre_away"] == pytest.approx(1 / 7)


def test_pace_pregame_shrinks_to_league_mean():
    g = _games()
    adv = pd.DataFrame({"game_id": [1, 1, 2, 2, 3, 3], "team": ["A", "B", "B", "A", "A", "C"],
                        "off_plays": [80, 80, 60, 60, 70, 70]})
    p = pace_pregame(g, adv)
    league = np.mean([160, 120, 140])
    assert p.loc[1, "pace_pre_home"] == pytest.approx(league)
    assert p.loc[2, "pace_pre_away"] == pytest.approx((160 + 3 * league) / 4)


def test_total_model_recovers_and_scores_are_consistent():
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"epa_sum": rng.normal(0, 0.15, 3000), "pace": rng.normal(134, 4, 3000)})
    tot = 55 + 25 * d.epa_sum + 0.8 * (d.pace - 134) + rng.normal(0, 14, 3000)
    d["home_pts"], d["away_pts"] = tot / 2, tot / 2
    m = TotalModel().fit(d)
    assert m.coef["const"] == pytest.approx(55, abs=1) and m.coef["epa_sum"] == pytest.approx(25, abs=5)
    assert m.sigma == pytest.approx(14, abs=0.6)


def test_residual_fit_recovers_slope_and_guards():
    rng = np.random.default_rng(2)
    d = pd.DataFrame({"x": rng.normal(0, 1, 2000), "z": 0.0})
    d["r"] = 1.5 * d.x + 0.7 + rng.normal(0, 5, 2000)
    f = ResidualFit(["x", "z"]).fit(d, "r")
    assert f.coef["x"] == pytest.approx(1.5, abs=0.4) and f.coef["z"] == 0 and np.isnan(f.stderr["z"])
    assert f.const == pytest.approx(0.7, abs=0.4)
    assert (f.contributions(d)["x"] == d.x * f.coef["x"]).all()
    small = ResidualFit(["x"]).fit(d.head(10), "r")
    assert small.coef["x"] == 0.0  # too little data -> no adjustment


def test_injury_points_math():
    inj = pd.DataFrame([{"team": "Tennessee", "player": "QB1", "position": "QB", "status": "Out", "impact_rating": 5},
                        {"team": "Tennessee", "player": "WR2", "position": "WR", "status": "questionable", "impact_rating": 2},
                        {"team": "Kentucky", "player": "X", "position": "RB", "status": "out", "impact_rating": 3}])
    depth = pd.DataFrame([{"team": "Tennessee", "player": "QB1", "string": 1}, {"team": "Tennessee", "player": "WR2", "string": 2}])
    pts, det = injury_points(inj, depth, "Tennessee", points_per_impact=0.6)
    assert pts == pytest.approx(5 * 0.6 * 1.0 * 1.0 + 2 * 0.6 * 0.5 * 0.5)
    assert len(det) == 2 and injury_points(pd.DataFrame(), None, "Tennessee") == (0.0, [])
    assert injury_points(inj, None, "Kentucky")[0] == pytest.approx(3 * 0.6 * 1.0 * 0.5)  # unlisted depth weight


def test_simulate_game_matches_analytic_probability():
    sim = simulate_game(4.0, 52.0, 16.0, 16.0, 0.05, n=40000, seed=1)
    s = summarize_game(sim, market_spread=-6.5)
    assert s["win_prob"] == pytest.approx(norm.cdf(4 / 16), abs=0.01)
    assert (sim["a"] >= 0).all() and (sim["b"] >= 0).all() and (sim["margin"] != 0).all()
    assert s["cover_prob_vs_market"] == pytest.approx(((sim["margin"] - 6.5) > 0).mean())
    assert sum(h["share"] for h in s["margin_hist"]) == pytest.approx(1.0)


def test_season_sim_correlation_and_tau():
    g = pd.DataFrame({"home_team": ["T"] * 8, "away_team": [f"O{i}" for i in range(8)], "margin": 0.0})
    w0 = simulate_season(g, 16, 0.0, n=20000, seed=3).sum(axis=1)
    w1 = simulate_season(g, 16, 8.0, n=20000, seed=3).sum(axis=1)
    assert w0.mean() == pytest.approx(4, abs=0.05) and w1.var() > w0.var() * 1.3  # shared shock widens spread
    rng = np.random.default_rng(4)
    rows = []
    for season in range(4):
        shock = {t: rng.normal(0, 3) for t in range(60)}
        for _ in range(600):
            h, a = rng.choice(60, 2, replace=False)
            rows.append({"home_team": h, "away_team": a, "season": season,
                         "resid_margin": shock[h] - shock[a] + rng.normal(0, 15)})
    tau = estimate_tau(pd.DataFrame(rows), 15.0)
    assert 1.5 < tau < 4.5


def test_season_outlook_distributions_sum_to_one():
    rem = pd.DataFrame({"game_id": [1, 2], "home_team": ["T", "X"], "away_team": ["Y", "T"], "margin": [3.0, 1.0],
                        "conf": [True, True]})
    st = pd.DataFrame({"team": ["T", "X", "Y"], "wins": [3, 4, 1], "losses": [1, 0, 3]})
    o = season_outlook(rem, 6, 2, "T", rem, st, 16.0, 2.0, n=5000)
    assert sum(x["prob"] for x in o["win_distribution"]) == pytest.approx(1.0)
    c = o["conference"]
    assert sum(x["prob"] for x in c["conf_win_distribution"]) == pytest.approx(1.0)
    assert 0 <= c["p_first_place"] <= c["p_top2_finish"] <= 1
    assert o["expected_wins"] == pytest.approx(6 + sum(p["win_prob"] for p in o["per_game"]))
