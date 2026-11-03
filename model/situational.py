"""Situation models fitted on all FBS plays of a season.

* Pass-rate model -> PROE (pass rate over expected): how much more often a team
  passes than an average FBS team would in the same down, distance, field position,
  score and clock situations.
* 4th-down decision model -> go rate over expected: how often a team goes for it
  compared with what a *typical FBS coach* does in the same spot. This measures
  aggressiveness relative to peers, not whether the decisions were optimal.

Both are plain logistic regressions so they stay explainable. Held-out (by game)
log loss and AUC are reported so the UI can show how much to trust them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _situation_features(df: pd.DataFrame, fourth: bool = False) -> pd.DataFrame:
    dist = df["distance"].clip(1, 30).astype(float)
    ytg = df["ytg"].clip(1, 99).astype(float)
    margin = df["margin"].clip(-28, 28).astype(float)
    t = (df["half_sec_left"].clip(0, 1800) / 1800).astype(float)
    late = (df["period"] >= 4).astype(float)
    X = pd.DataFrame({
        "log_dist": np.log(dist), "dist": dist, "ytg": ytg / 100, "ytg2": (ytg / 100) ** 2,
        "margin": margin / 28, "margin_x_time_left": margin / 28 * (1 - t), "time_left": t,
        "second_half": (df["period"] >= 3).astype(float), "late_trailing": late * (margin < 0),
        "two_min": (df["half_sec_left"] <= 120).astype(float), "home": df["is_home"].astype(float),
        "red_zone": (ytg <= 20).astype(float), "goal_to_go": (dist >= ytg).astype(float),
    }, index=df.index)
    if not fourth:
        X["down2"] = (df["down"] == 2).astype(float)
        X["down3"] = (df["down"] == 3).astype(float)
        X["down3_x_logdist"] = X["down3"] * X["log_dist"]
    else:
        X["fg_range"] = (ytg <= 38).astype(float)  # ~55-yard attempt or shorter
    return X


@dataclass
class SituationModel:
    name: str
    target: str
    fourth: bool
    pipe: object | None = None
    cv_log_loss: float = float("nan")
    cv_auc: float = float("nan")
    base_rate: float = float("nan")
    base_log_loss: float = float("nan")
    n_train: int = 0

    def fit(self, df: pd.DataFrame, groups: pd.Series, folds: int = 5) -> "SituationModel":
        X, y = _situation_features(df, self.fourth), df[self.target].astype(int).to_numpy()
        self.n_train = len(y)
        self.base_rate = float(y.mean())
        oof = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=folds).split(X, y, groups):
            m = self._new().fit(X.iloc[tr], y[tr])
            oof[te] = m.predict_proba(X.iloc[te])[:, 1]
        self.cv_log_loss = float(log_loss(y, oof))
        self.cv_auc = float(roc_auc_score(y, oof))
        self.base_log_loss = float(log_loss(y, np.full(len(y), self.base_rate)))
        self.pipe = self._new().fit(X, y)
        return self

    @staticmethod
    def _new():
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(_situation_features(df, self.fourth))[:, 1]

    def summary(self) -> dict:
        return {"model": self.name, "n_train": self.n_train, "base_rate": self.base_rate,
                "cv_log_loss": self.cv_log_loss, "baseline_log_loss": self.base_log_loss, "cv_auc": self.cv_auc,
                "validation": "5-fold cross-validation grouped by game (no game in both train and test)"}


def pass_rate_sample(plays: pd.DataFrame) -> pd.DataFrame:
    """Plays used for PROE: non-garbage 1st-3rd down scrimmage plays."""
    return plays[plays["is_scrimmage"] & plays["down"].between(1, 3) & ~plays["garbage"]
                 & plays["distance"].notna() & plays["ytg"].notna()].copy()


def fourth_down_sample(plays: pd.DataFrame) -> pd.DataFrame:
    return plays[(plays["fourth_decision"] != "") & ~plays["garbage"]
                 & plays["distance"].notna() & plays["ytg"].notna()].copy()


def fit_pass_model(plays: pd.DataFrame) -> tuple[SituationModel, pd.DataFrame]:
    s = pass_rate_sample(plays)
    s["pass"] = s["is_pass"].astype(int)
    m = SituationModel("pass_rate", "pass", fourth=False).fit(s, s["game_id"])
    s["xpass"] = m.predict(s)
    return m, s


def fit_fourth_model(plays: pd.DataFrame) -> tuple[SituationModel, pd.DataFrame]:
    s = fourth_down_sample(plays)
    s["go"] = (s["fourth_decision"] == "go").astype(int)
    m = SituationModel("fourth_down_go", "go", fourth=True).fit(s, s["game_id"])
    s["xgo"] = m.predict(s)
    return m, s


def over_expected(df: pd.DataFrame, actual: str, expected: str, by: list[str]) -> pd.DataFrame:
    """Actual rate - expected rate, with a 95% interval from the Bernoulli variance of the expectation."""
    g = df.groupby(by)
    out = pd.DataFrame({
        "n": g.size(),
        "actual_rate": g[actual].mean(),
        "expected_rate": g[expected].mean(),
        "var": g[expected].apply(lambda p: float((p * (1 - p)).sum())),
    })
    out["over_expected"] = out["actual_rate"] - out["expected_rate"]
    se = np.sqrt(out["var"]) / out["n"]
    out["ci95_low"] = out["over_expected"] - 1.96 * se
    out["ci95_high"] = out["over_expected"] + 1.96 * se
    return out.drop(columns="var").reset_index()
