"""Adjustments layer: explicit, separately reported corrections on top of the baseline.

Data-fitted (on out-of-sample residuals from earlier seasons only):
  margin: rest advantage, travel, turnover regression, recent form
  total:  wind, precipitation, cold
Manual (assumption, user-adjustable):
  injuries from data/manual/injuries.csv x depth chart role
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class Adj:
    key: str
    label: str
    unit: str
    description: str


MARGIN_ADJ = [
    Adj("rest_diff", "Rest advantage", "days (home - away)",
        "Difference in days since each team's previous game (bye weeks show up here), capped at +/-7."),
    Adj("travel_diff", "Travel", "1,000 km (away - home)",
        "Extra distance the visiting team travels from its home stadium, beyond the home team's."),
    Adj("to_diff", "Turnover regression", "turnover margin/game (home - away)",
        "Season-to-date turnover margin, shrunk toward 0. A negative coefficient means turnover "
        "luck tends not to persist, so ratings built on it are trimmed."),
    Adj("form_edge", "Recent form", "EPA/play (recent - season)",
        "How much better each team rates when recent games count more (3-week half-life) than "
        "when every game counts equally."),
]
TOTAL_ADJ = [
    Adj("wind_over_10", "Wind", "mph above 10", "Average wind over the first three game hours, above 10 mph."),
    Adj("precip_mm", "Precipitation", "mm/hour", "Average precipitation over the first three game hours."),
    Adj("cold", "Cold", "1 if under 40F", "Kickoff-window temperature below 40F."),
]


@dataclass
class ResidualFit:
    keys: list[str]
    intercept: bool = True  # fitted so slopes aren't biased by any overall drift; never applied
    const: float = 0.0
    coef: dict[str, float] = field(default_factory=dict)
    stderr: dict[str, float] = field(default_factory=dict)
    n: int = 0

    def fit(self, df: pd.DataFrame, resid: str) -> "ResidualFit":
        d = df.dropna(subset=[resid]).copy()
        X = d[self.keys].astype(float).fillna(0.0)  # missing input = no information = no adjustment
        live = [k for k in self.keys if X[k].std() > 0]  # inputs with no variation can't be fitted
        if len(live) < len(self.keys):
            fitted = ResidualFit(live, self.intercept).fit(df, resid) if live else None
            self.coef = {k: (fitted.coef[k] if fitted and k in live else 0.0) for k in self.keys}
            self.stderr = {k: (fitted.stderr[k] if fitted and k in live else float("nan")) for k in self.keys}
            self.const, self.n = (fitted.const, fitted.n) if fitted else (0.0, 0)
            return self
        keep = X.abs().sum(axis=1) > 0 if not self.intercept else pd.Series(True, index=X.index)
        X, y = X[keep], d.loc[keep, resid].astype(float)
        if self.intercept:
            X = sm.add_constant(X, has_constant="add")
        if len(y) < 50:
            self.coef = {k: 0.0 for k in self.keys}
            self.stderr = {k: float("nan") for k in self.keys}
            self.n = int(len(y))
            return self
        res = sm.OLS(y.to_numpy(), X.to_numpy()).fit()
        names = (["const"] if self.intercept else []) + self.keys
        self.coef = {k: float(v) for k, v in zip(names, res.params) if k != "const"}
        self.const = float(res.params[0]) if self.intercept else 0.0
        self.stderr = {k: float(v) for k, v in zip(names, res.bse) if k != "const"}
        self.n = int(len(y))
        return self

    def contributions(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({k: df[k].astype(float).fillna(0.0) * self.coef.get(k, 0.0) for k in self.keys},
                            index=df.index)

    def to_dict(self, specs: list[Adj]) -> list[dict]:
        out = []
        for s in specs:
            c, se = self.coef.get(s.key, 0.0), self.stderr.get(s.key, float("nan"))
            out.append({**s.__dict__, "coef": c, "se": se, "n": self.n,
                        "ci95_low": c - 1.96 * se if se == se else None,
                        "ci95_high": c + 1.96 * se if se == se else None,
                        "significant": bool(se == se and abs(c) > 1.96 * se)})
        return out


# ---- injuries (manual) ------------------------------------------------------

STATUS_PROB_OUT = {"out": 1.0, "doubtful": 0.75, "questionable": 0.5, "probable": 0.1, "available": 0.0}
DEPTH_WEIGHT = {1: 1.0, 2: 0.5, 3: 0.25}
DEPTH_WEIGHT_UNLISTED = 0.5
POINTS_PER_IMPACT = 0.6  # ASSUMPTION: a 5/5 impact starter fully out ~ 3 points. Not fit from data.


def injury_points(injuries: pd.DataFrame, depth: pd.DataFrame | None, team: str,
                  points_per_impact: float = POINTS_PER_IMPACT) -> tuple[float, list[dict]]:
    """Expected points lost by ``team`` from its listed injuries (positive = team is weaker)."""
    if injuries is None or injuries.empty:
        return 0.0, []
    inj = injuries[injuries["team"].fillna("").str.casefold() == team.casefold()]
    strings = {}
    if depth is not None and not depth.empty:
        d = depth[depth["team"].fillna("").str.casefold() == team.casefold()] if "team" in depth else depth
        strings = {str(p).casefold(): int(s) for p, s in zip(d["player"], d["string"]) if pd.notna(s)}
    total, detail = 0.0, []
    for r in inj.itertuples(index=False):
        p_out = STATUS_PROB_OUT.get(str(r.status).strip().lower(), 0.0)
        depth_w = DEPTH_WEIGHT.get(strings.get(str(r.player).casefold()), DEPTH_WEIGHT_UNLISTED)
        pts = float(r.impact_rating) * points_per_impact * p_out * depth_w
        total += pts
        detail.append({"player": r.player, "position": r.position, "status": r.status,
                       "impact_rating": r.impact_rating, "prob_out": p_out, "depth_weight": depth_w, "points": pts})
    return total, detail


def load_manual(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() and path.stat().st_size > 0 else pd.DataFrame()
