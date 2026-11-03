import numpy as np
import pandas as pd
import pytest

from model.ratings import AdjParams, EloParams, adjusted_efficiency, elo_expected, run_elo


def _games(rows):
    return pd.DataFrame([{
        "game_id": i, "season": s, "start_date": pd.Timestamp("2025-09-01", tz="UTC") + pd.Timedelta(days=7 * i),
        "completed": hp is not None, "neutral_site": n, "home_team": h, "away_team": a,
        "home_class": "fbs", "away_class": "fbs", "home_pts": hp, "away_pts": ap,
    } for i, (s, h, a, hp, ap, n) in enumerate(rows)])


def test_elo_is_zero_sum_and_winner_gains():
    g, r = run_elo(_games([(2025, "A", "B", 30, 10, False)]))
    assert r["A"] > 1500 > r["B"]
    assert r["A"] + r["B"] == pytest.approx(3000)
    assert g.loc[0, "home_elo_pre"] == 1500 and g.loc[0, "home_elo_post"] == pytest.approx(r["A"])


def test_bigger_margin_moves_more_and_upset_moves_more():
    _, r1 = run_elo(_games([(2025, "A", "B", 21, 20, True)]))
    _, r2 = run_elo(_games([(2025, "A", "B", 41, 0, True)]))
    assert r2["A"] - 1500 > r1["A"] - 1500 > 0
    # home team (expected to win via HFA) losing costs more than an away loss
    _, home_loss = run_elo(_games([(2025, "A", "B", 10, 20, False)]))
    _, away_loss = run_elo(_games([(2025, "B", "A", 20, 10, False)]))
    assert 1500 - home_loss["A"] > 1500 - away_loss["A"]


def test_pregame_rating_excludes_that_games_result():
    g, _ = run_elo(_games([(2025, "A", "B", 30, 10, False), (2025, "A", "C", None, None, False)]))
    assert g.loc[1, "home_elo_pre"] == pytest.approx(g.loc[0, "home_elo_post"])
    assert np.isnan(g.loc[1, "home_elo_post"])  # unplayed: no update


def test_offseason_regression_toward_mean():
    p = EloParams(season_regression=0.5)
    g, _ = run_elo(_games([(2024, "A", "B", 40, 0, False), (2025, "A", "B", None, None, False)]), p)
    post = g.loc[0, "home_elo_post"]
    assert g.loc[1, "home_elo_pre"] == pytest.approx(1500 + (post - 1500) * 0.5)


def test_elo_expected_home_edge():
    assert elo_expected(0) == 0.5 and elo_expected(55) > 0.5


def test_adjusted_efficiency_recovers_synthetic_truth():
    rng = np.random.default_rng(0)
    teams = [f"T{i}" for i in range(20)]
    off = dict(zip(teams, rng.normal(0, 0.10, 20)))
    dfn = dict(zip(teams, rng.normal(0, 0.08, 20)))
    hfa, rows = 0.03, []
    for _ in range(12):  # 12 random rounds -> each team ~12 games
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2]):
            for o, d, site in ((h, a, "home"), (a, h, "away")):
                y = 0.05 + off[o] + dfn[d] + (hfa if site == "home" else -hfa) + rng.normal(0, 0.03)
                rows.append({"team": o, "opponent": d, "site": site, "off_epa": y, "off_plays": 70})
    est, hfa_hat = adjusted_efficiency(pd.DataFrame(rows), params=AdjParams(alpha=0.5))
    est = est.set_index("team")
    assert np.corrcoef(est["adj_off"], [off[t] for t in est.index])[0, 1] > 0.95
    assert np.corrcoef(est["adj_def"], [dfn[t] for t in est.index])[0, 1] > 0.95
    assert hfa_hat == pytest.approx(hfa, abs=0.01)


def test_adjusted_efficiency_empty_input():
    est, hfa = adjusted_efficiency(pd.DataFrame(columns=["team", "opponent", "site", "off_epa"]))
    assert est.empty and np.isnan(hfa)
