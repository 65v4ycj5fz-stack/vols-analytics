import numpy as np
import pandas as pd
import pytest

from model.backtest import calibration, metrics
from model.features import EffParams, game_features
from model.margin import FULL, MarginModel
from model.ratings import EloParams


def _league(seed=0, seasons=(2024, 2025), teams=10, weeks=8):
    rng = np.random.default_rng(seed)
    names = [f"T{i}" for i in range(teams)]
    strength = dict(zip(names, rng.normal(0, 10, teams)))
    games, adv, gid = [], [], 0
    for s in seasons:
        for w in range(1, weeks + 1):
            order = rng.permutation(names)
            for h, a in zip(order[::2], order[1::2]):
                gid += 1
                m = strength[h] - strength[a] + 3 + rng.normal(0, 12)
                hp = max(0, round(28 + m / 2)); ap = max(0, round(28 - m / 2))
                games.append({"game_id": gid, "season": s, "week": w, "season_type": "regular",
                              "start_date": pd.Timestamp(f"{s}-09-01", tz="UTC") + pd.Timedelta(weeks=w),
                              "completed": True, "neutral_site": False, "home_team": h, "away_team": a,
                              "home_class": "fbs", "away_class": "fbs", "home_pts": hp, "away_pts": ap,
                              "spread_home": -(strength[h] - strength[a] + 3)})
                for t, o in ((h, a), (a, h)):
                    adv.append({"game_id": gid, "team": t, "off_epa": (strength[t] - strength[o]) / 50 + rng.normal(0, 0.1),
                                "off_plays": 70})
    return pd.DataFrame(games), pd.DataFrame(adv)


FEATS = ["home_elo_pre", "away_elo_pre", "home_adj_off", "home_adj_def", "away_adj_off", "away_adj_def", "epa_diff"]


def test_features_have_no_lookahead():
    games, adv = _league()
    base = game_features(games, adv, EloParams(), EffParams()).set_index("game_id")
    cut = (games["season"] == 2025) & (games["week"] >= 4)
    g2, a2 = games.copy(), adv.copy()
    g2.loc[cut, ["home_pts", "away_pts"]] = g2.loc[cut, ["away_pts", "home_pts"]].to_numpy() + 30  # scramble future
    future_ids = set(g2.loc[cut, "game_id"])
    a2.loc[a2["game_id"].isin(future_ids), "off_epa"] *= -5
    pert = game_features(g2, a2, EloParams(), EffParams()).set_index("game_id")
    known = games.loc[~cut | (games["week"] == 4), "game_id"]  # week-4 features use weeks 1-3 only
    pd.testing.assert_frame_equal(base.loc[known, FEATS], pert.loc[known, FEATS])
    later = games.loc[cut & (games["week"] > 4), "game_id"]
    assert not np.allclose(base.loc[later, "epa_diff"], pert.loc[later, "epa_diff"])


def test_week_one_uses_prior_only():
    games, adv = _league()
    f = game_features(games, adv).set_index("game_id")
    wk1_2024 = games[(games.season == 2024) & (games.week == 1)]["game_id"]
    assert (f.loc[wk1_2024, ["home_adj_off", "away_adj_off"]] == 0).all().all()  # no prior before first season
    wk1_2025 = games[(games.season == 2025) & (games.week == 1)]["game_id"]
    assert (f.loc[wk1_2025, "home_games_in_season"] == 0).all() and (f.loc[wk1_2025, "home_adj_off"] != 0).any()


def test_margin_model_recovers_coefficients():
    rng = np.random.default_rng(3)
    d = pd.DataFrame({"site_home": rng.integers(0, 2, 4000).astype(float), "elo_diff": rng.normal(0, 200, 4000),
                      "epa_diff": rng.normal(0, 0.2, 4000)})
    d["margin"] = 2.5 * d.site_home + 0.03 * d.elo_diff + 40 * d.epa_diff + rng.normal(0, 14, 4000)
    m = MarginModel(FULL).fit(d)
    assert m.coef["site_home"] == pytest.approx(2.5, abs=1.0) and m.coef["elo_diff"] == pytest.approx(0.03, abs=0.005)
    assert m.sigma == pytest.approx(14, abs=0.5)
    assert m.win_prob(0.0) == 0.5 and m.win_prob(m.sigma) == pytest.approx(0.8413, abs=1e-3)
    lo, hi = m.interval(3.0, 0.8)
    assert 3.0 - lo == pytest.approx(hi - 3.0)


def test_metrics_ats_and_errors():
    d = pd.DataFrame({"margin": [10, -3, 7, 0], "market_margin": [7, -7, 7, 1]})
    pred = np.array([9.0, -10.0, 8.0, 2.0])
    r = metrics(pred, np.array([0.7, 0.2, 0.6, 0.55]), d)
    # g1: edge +2 picks home, home covered (10>7) -> W; g2: edge -3 picks away, margin -3 > -7 home covered -> L
    # g3: push vs market (7 == 7) -> push; g4: edge +1 picks home, 0-1 <0 -> L
    assert (r["ats_wins"], r["ats_losses"], r["ats_pushes"]) == (1, 2, 1)
    assert r["ats_edge3_wins"] == 0 and r["ats_edge3_losses"] == 1
    assert r["mae_vs_actual"] == pytest.approx(np.mean([1, 7, 1, 2]))
    assert r["straight_up_accuracy"] == pytest.approx(1.0)  # tie game excluded


def test_calibration_bins_cover_all_games():
    rng = np.random.default_rng(0)
    p = rng.random(5000)
    y = (rng.random(5000) < p).astype(float)
    bins = calibration(p, y)
    assert sum(b["n"] for b in bins) == 5000
    for b in bins:
        assert abs(b["mean_predicted"] - b["actual_rate"]) < 0.06 and b["ci95_low"] <= b["actual_rate"] <= b["ci95_high"]
