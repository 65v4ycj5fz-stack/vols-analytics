# Model methodology

Everything here is reproducible with `make data` (or `make data-offline`) and is
tested in `model/tests/`. Live numbers come from `public/data/backtest.json` and
`public/data/model_params.json`; the snapshot below is dated so it is never
mistaken for the current state.

## 1. Ratings (pregame, no lookahead)

| Rating | How | Code |
|---|---|---|
| **Elo** (ours) | Margin-aware Elo over every game involving an FBS team since 2019. Rating moves by `K × ln(|margin|+1) × 2.2/(0.001·Δelo_winner + 2.2) × (result − expected)`. FBS teams start at 1500, others at 1200; each offseason ratings regress toward the mean. The rating stored for a game is the one *before* kickoff. | `model/ratings.py` |
| **Opponent-adjusted EPA/play** (ours) | Ridge regression of each team-game's offensive EPA/play on offense, defense and home indicators, weighted by plays. Before every week we refit using only that season's earlier games, then blend with last season's final rating: `(n·current + g·prior_keep·last_season) / (n + g)`, where `n` = games played. Week 1 uses the prior alone. | `model/features.py` |

Published ratings (SP+, CFBD Elo, FPI) are shown on the site for context but are
**not** model inputs: their historical values are end-of-season numbers, so using
them would leak future information into the backtest.

## 2. Predicted margin and home-field advantage

```
home_margin = b_home · site_home + b_elo · (home_elo − away_elo) + b_epa · epa_edge + error
epa_edge    = (home_adj_off + away_adj_def) − (away_adj_off + home_adj_def)      # EPA/play
error       ~ Normal(0, σ)
```

* `site_home` is 1 for a true home game, 0 at a neutral site. **Home-field advantage
  is `b_home`, fitted from data**, not assumed.
* No intercept: two equal teams on a neutral field are a coin flip.
* Fitted with ordinary least squares on FBS-vs-FBS games from earlier seasons.

## 3. Win probability

`P(win) = Φ(predicted margin / σ)`, where σ is the standard deviation of training
residuals. Calibration is measured out of sample (section 5) in ten probability bins,
each with a 95% interval, alongside the Brier score and log loss.

## 4. Walk-forward backtest (no leakage)

For each test season S from 2021 through the current season:

1. **Settings** are chosen from a grid using only seasons before S. The grid is
   27 Elo settings (K, Elo home bonus, offseason regression) × 12 efficiency settings
   (ridge penalty, prior weight, share of last season kept). Selection minimizes
   in-sample margin error on the training seasons.
2. **Coefficients and σ** are fitted on seasons 2020 through S−1. 2019 is warm-up only.
3. **Every game in S** is predicted from features that only use games played before it.
   `test_features_have_no_lookahead` checks this: it scrambles the results of future
   games and asserts that earlier features don't change.

Comparisons:

* **Elo-only baseline**: the same setup with only `site_home` and `elo_diff`.
* **Market**: the closing spread (median across the sportsbooks CFBD lists). Its win
  probability is `Φ(−spread / σ_market)`.

Metrics: MAE and RMSE vs the actual margin, MAE vs the closing spread, straight-up
accuracy, Brier score, log loss, calibration, and record against the spread (all games
and games where |model − market| ≥ 3). The spread comparison exists only to measure
accuracy. The site has no wagering features.

## 5. Results snapshot (generated 2026-11-02; 4,444 games, 2021–2026 wk 9)

| | Margin MAE | Brier | Log loss | Straight-up | Calibration error* |
|---|---|---|---|---|---|
| **Model** | **12.98** | 0.190 | 0.558 | 70.0% | 0.025 |
| Elo only | 13.22 | 0.193 | 0.568 | 69.9% | 0.027 |
| Closing spread | 12.03 | 0.177 | 0.524 | 73.0% | 0.015 |

\*Expected calibration error: the games-weighted average gap between predicted and actual win rate across the ten bins.

**Honest read:** the model beats the Elo-only baseline on margin error in all six seasons (and on Brier score in five of six), but it
**does not beat the market**. Closing spreads are about 1 point per game more accurate,
and the model's picks went 49.1% against the spread (47% when it disagreed with the
market by 3+ points). Treat the model as an explainable view of team strength, not an
edge. The site says this on the Model page.

Live-model parameters (trained on 2020–2025): home field = **+2.8 pts (SE 0.26)**;
100 Elo points ≈ **2.2 pts**; an EPA/play edge of 0.1 ≈ **3.2 pts**; σ ≈ 16.5 pts.

## 6. Known limitations

* **Home field is drifting upward.** The average FBS home margin went from 3.3
  (2021) to 5.1 (2025) and 6.7 (2026 so far), but the model fits one home-field value
  on all past seasons. The result is that home teams in the 25–50% bins win somewhat
  more often than predicted.
* The grid search chose almost no offseason Elo regression and no Elo home bonus,
  leaving home field to the regression term. These are the best values within the
  searched grid, not a claim about football.
* No roster, recruiting, transfer-portal or injury information yet. Early-season
  predictions rely on last season's ratings. Phase 4 adds the adjustments layer.
* FCS opponents are rated only from their games against FBS teams in the data.
* The margin error is assumed normal with one σ for every matchup. Blowout and
  close-game tails are not modeled separately (Phase 4 simulation revisits this).

## 7. Situation models (tendencies, Phase 2)

Two descriptive logistic regressions fitted on all FBS plays of the current season.
Validation is 5-fold, grouped by game, and fit quality is reported in `tendency_models.json`:

* **Pass rate**: 1st–3rd down, non-garbage plays. Features: down, distance, field
  position, score margin × time, half/two-minute flags, home. PROE = actual − expected,
  with a 95% interval.
* **4th-down go**: what a *typical FBS coach* does in the same spot. "Go rate over
  expected" measures aggressiveness relative to peers, **not** whether a decision was
  optimal.

## 8. Score projection (Phase 4)

```
total = c0 + c_epa · epa_sum + c_pace · (pace − 134) + error_total
team points = (total ± margin) / 2
```

`epa_sum` is both offenses' expected EPA/play against the opposing defense. `pace` is
the two teams' average total plays per game so far (shrunk toward the league mean for
the first few games). Because team points come from the margin and total, the
projected score always matches the margin model. The totals model is fitted on the
same earlier-season training window as the margin model.

## 9. Adjustments layer

Each adjustment is listed separately on every projection with its input, coefficient,
standard error and points, so you can see and switch off each one.

| Adjustment | Applies to | How it's set |
|---|---|---|
| Rest advantage (days, ±7 cap) | margin | fitted |
| Travel (extra km traveled by the visitor) | margin | fitted |
| Turnover regression (season-to-date turnover margin, shrunk) | margin | fitted |
| Recent form (rating with a 3-week half-life minus the flat rating) | margin | fitted |
| Wind over 10 mph, precipitation, cold (< 40°F) | total | fitted |
| Injuries | margin | **manual assumption** |

**Fitted adjustments** are regressions on the walk-forward model's *out-of-sample*
residuals. For season S they are fitted only on seasons before S. They include an
intercept so their slopes aren't biased by overall drift, and that intercept is never
applied. An input with no variation, or fewer than 50 usable games, gets no adjustment.

**Injuries** can't be fitted from public data, so the rule is a stated assumption:
`impact (0–5, manual) × 0.6 pts × P(out | status) × depth weight`, where
P(out) is out 1.0 / doubtful 0.75 / questionable 0.5 / probable 0.1 / available 0, and the
depth weight is starter 1.0 / 2nd string 0.5 / 3rd 0.25 / not on the chart 0.5. A 5/5
starter ruled out is about 3 points. All of these values are adjustable in the UI.

Turnover data (box scores) is pulled for the last three seasons only, to save API calls.
The turnover adjustment is therefore fitted on 2024–2025 residuals.

## 10. Simulation

* **Game:** 10,000 draws of (margin, total) from a bivariate normal using the model's
  error SDs and their historical residual correlation. Scores are rounded and floored
  at 0. Ties go to a simplified overtime (winner drawn from the win probability, +7).
  Outputs: win probability, score and margin distributions, the most common simulated
  scores, one-score-game probability, and the probability of beating the closing spread
  (shown only for model evaluation).
* **Season:** 10,000 simulated seasons covering the team's remaining games and every
  remaining SEC game. Each team gets one strength shock per simulated season (SD τ,
  estimated from how team-season average residuals vary beyond game-level noise), so a
  team that is better than its rating stays better all season. Per-game noise is reduced
  so each single game still has the full model error. Outputs: win-total distribution,
  P(≥N wins), SEC record distribution and P(top-2 SEC finish).
  **Approximation:** SEC ties are broken at random. No playoff probability is shown,
  because selection is by committee.
* **Explanations:** model factors (home field, Elo, offense matchup, defense matchup, and
  each adjustment) add up exactly to the projected margin. Rush/pass "split edges" break
  the EPA factors down further for description only and are not added again. "Keys to
  the game" are generated from the largest split edges and tendency stats.

### Phase 4 snapshot (generated 2026-11-02, live coefficients fitted on 2021–2025 residuals)

| Adjustment | Effect | SE | Significant |
|---|---|---|---|
| Travel | +0.80 pts per 1,000 km extra for the visitor | 0.28 | yes |
| Turnover regression | −1.10 pts per +1 turnover margin/game | 0.66 | no |
| Rest | +0.05 pts per day | 0.10 | no |
| Recent form | −6.4 pts per EPA/play of form edge | 6.2 | no |
| Wind (total) | −0.56 pts per mph above 10 | 0.18 | yes |
| Cold < 40°F (total) | −2.4 pts | 1.1 | yes |
| Precipitation (total) | −0.83 pts per mm/h | 0.72 | no |

Out of sample, the adjustments trim margin error from 12.98 to 12.96 pts and total error
from 12.99 to 12.96 pts. The closing total is still better at 12.52. Season-level
rating uncertainty is τ ≈ 1.9 pts. Margin and total errors correlate at about ρ ≈ 0.05.
