"""Predicted margin and win probability.

margin_home = b_home * site_home + b_elo * elo_diff + b_epa * epa_diff + e,  e ~ Normal(0, sigma)

Home-field advantage is ``b_home`` (points), fitted from data. Win probability is
the normal CDF of predicted margin / sigma, with sigma fitted from training residuals.
No intercept: on a neutral field two equal teams should be a coin flip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

FULL = ("site_home", "elo_diff", "epa_diff")
ELO_ONLY = ("site_home", "elo_diff")


@dataclass
class MarginModel:
    features: tuple[str, ...] = FULL
    coef: dict[str, float] = field(default_factory=dict)
    stderr: dict[str, float] = field(default_factory=dict)
    sigma: float = float("nan")
    n_train: int = 0

    def fit(self, df: pd.DataFrame) -> "MarginModel":
        d = df.dropna(subset=list(self.features) + ["margin"])
        res = sm.OLS(d["margin"].to_numpy(dtype=float), d[list(self.features)].to_numpy(dtype=float)).fit()
        self.coef = dict(zip(self.features, map(float, res.params)))
        self.stderr = dict(zip(self.features, map(float, res.bse)))
        self.sigma = float(np.sqrt(np.mean(res.resid ** 2)))
        self.n_train = len(d)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return sum(df[k].to_numpy(dtype=float) * v for k, v in self.coef.items())

    def win_prob(self, margin: np.ndarray | float) -> np.ndarray:
        return norm.cdf(np.asarray(margin, dtype=float) / self.sigma)

    def interval(self, margin: np.ndarray | float, level: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
        z = norm.ppf(0.5 + level / 2)
        m = np.asarray(margin, dtype=float)
        return m - z * self.sigma, m + z * self.sigma

    def contributions(self, row: pd.Series) -> dict[str, float]:
        """Points each feature adds to the home margin (for plain-English explanations)."""
        return {k: float(row[k]) * v for k, v in self.coef.items()}

    def to_dict(self) -> dict:
        return {"features": list(self.features), "coef": self.coef, "stderr": self.stderr,
                "sigma": self.sigma, "n_train": self.n_train}


def market_sigma(df: pd.DataFrame) -> float:
    """Spread of actual margins around the closing line (used for a market win probability)."""
    d = df.dropna(subset=["market_margin", "margin"])
    return float(np.sqrt(np.mean((d["margin"] - d["market_margin"]) ** 2)))


TOTAL_FEATURES = ("epa_sum", "pace_c")
PACE_CENTER = 134.0  # typical total plays per FBS game; centers the pace term


@dataclass
class TotalModel:
    """total_points = c0 + c_epa * epa_sum + c_pace * (pace - 134) + e,  e ~ Normal(0, sigma).

    ``epa_sum`` is both offenses' expected EPA/play vs those defenses; ``pace`` the two teams'
    average total plays per game so far. Team points = (total +/- margin) / 2, so the projected
    score is always consistent with the margin model.
    """
    coef: dict[str, float] = field(default_factory=dict)
    stderr: dict[str, float] = field(default_factory=dict)
    sigma: float = float("nan")
    n_train: int = 0

    @staticmethod
    def _x(df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"const": 1.0, "epa_sum": df["epa_sum"].astype(float),
                             "pace_c": df["pace"].astype(float) - PACE_CENTER}, index=df.index)

    def fit(self, df: pd.DataFrame) -> "TotalModel":
        d = df.dropna(subset=["epa_sum", "pace", "home_pts", "away_pts"])
        y = d["home_pts"].astype(float) + d["away_pts"].astype(float)
        res = sm.OLS(y.to_numpy(), self._x(d).to_numpy()).fit()
        names = ["const", *TOTAL_FEATURES]
        self.coef = dict(zip(names, map(float, res.params)))
        self.stderr = dict(zip(names, map(float, res.bse)))
        self.sigma = float(np.sqrt(np.mean(res.resid ** 2)))
        self.n_train = len(d)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self._x(df)
        return sum(x[k].to_numpy() * v for k, v in self.coef.items())

    def to_dict(self) -> dict:
        return {"coef": self.coef, "stderr": self.stderr, "sigma": self.sigma, "n_train": self.n_train,
                "pace_center": PACE_CENTER}
