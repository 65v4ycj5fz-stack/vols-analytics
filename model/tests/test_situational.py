import numpy as np
import pandas as pd

from model.situational import fit_fourth_model, fit_pass_model


def _synthetic(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    down = rng.integers(1, 5, n)
    dist = rng.integers(1, 16, n)
    ytg = rng.integers(1, 99, n)
    margin = rng.integers(-21, 22, n)
    df = pd.DataFrame({"game_id": rng.integers(0, 300, n), "down": down, "distance": dist, "ytg": ytg,
                       "margin": margin, "period": rng.integers(1, 5, n), "half_sec_left": rng.integers(0, 1800, n),
                       "is_home": rng.random(n) < 0.5, "garbage": False, "is_scrimmage": True})
    # pass more on later downs / longer distance / when trailing
    logit = -1.0 + 0.6 * (down - 1) + 0.15 * dist - 0.03 * margin
    df["is_pass"] = rng.random(n) < 1 / (1 + np.exp(-logit))
    # go for it more on short distance near midfield
    go_logit = 1.5 - 0.6 * dist + 0.02 * (60 - abs(ytg - 45))
    go = rng.random(n) < 1 / (1 + np.exp(-go_logit))
    df["fourth_decision"] = np.where(down == 4, np.where(go, "go", np.where(ytg <= 35, "fg", "punt")), "")
    return df


def test_pass_model_learns_situation_and_reports_validation():
    df = _synthetic()
    m, s = fit_pass_model(df)
    summ = m.summary()
    assert summ["cv_auc"] > 0.7 and summ["cv_log_loss"] < summ["baseline_log_loss"]
    third = s[s.down == 3]
    assert third[third.distance >= 10]["xpass"].mean() > third[third.distance <= 2]["xpass"].mean()
    assert (s["down"] < 4).all()  # 4th downs are excluded from the pass-rate sample


def test_fourth_model_prefers_short_yardage():
    m, s = fit_fourth_model(_synthetic())
    assert m.summary()["cv_auc"] > 0.7
    assert s[s.distance <= 2]["xgo"].mean() > s[s.distance >= 8]["xgo"].mean()
