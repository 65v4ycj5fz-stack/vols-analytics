import { useState } from "react";
import { C } from "../components/chartColors";
import { CalibrationChart, LineSeriesChart } from "../components/lazyCharts";
import { Card, ChartFrame, ErrorState, Legend, Loading, PageHeader, Pill, Select, SimpleTable, SourceNote } from "../components/ui";
import { useDataset } from "../lib/data";
import { pct, signed } from "../lib/format";

interface M { games: number; mae_vs_actual: number; rmse_vs_actual: number; mae_vs_market: number; straight_up_accuracy: number;
  brier: number; log_loss: number; ats_wins: number; ats_losses: number; ats_pushes: number; ats_win_pct: number | null;
  ats_edge3_wins: number; ats_edge3_losses: number; ats_edge3_win_pct: number | null }
interface Cal { bin_low: number; bin_high: number; n: number; mean_predicted: number; actual_rate: number; ci95_low: number; ci95_high: number }
interface AdjItem { key: string; label: string; unit: string; coef: number; se: number | null; ci95_low: number | null; ci95_high: number | null; significant: boolean; n: number; description: string }
interface Backtest {
  headline: string; beats_market: boolean; test_seasons: number[];
  overall: { model: M; elo_only: M; market: M };
  per_season: { season: number; train_seasons: string; model: M; elo_only: M; market: M }[];
  calibration: { model: Cal[]; elo_only: Cal[]; market: Cal[] };
  model_adjusted: { overall: M; per_season: (M & { season: number })[]; calibration: Cal[] };
  totals: { overall: { games: number; model_mae: number; adjusted_mae: number; market_mae: number } };
  adjustment_fits: { season: number; fitted_on: string; margin: AdjItem[]; total: AdjItem[] }[];
}
interface Params { home_field_points: number; home_field_points_se: number; points_per_100_elo: number; points_per_0_1_epa_edge: number;
  margin_model: { sigma: number; n_train: number }; elo_params: Record<string, number>; eff_params: Record<string, number | null> }

export default function ModelPage() {
  const bt = useDataset<Backtest>("backtest");
  const pr = useDataset<Params>("model_params");
  const adjDs = useDataset<{ injury_assumptions: { points_per_impact: number } }>("adjustments_model");
  const outDs = useDataset<{ n_sims: number }>("season_outlook");
  const [calKey, setCalKey] = useState<"model" | "elo_only" | "market" | "adjusted">("model");
  if (bt.status === "loading" || pr.status === "loading") return <Loading />;
  if (bt.status === "error") return <ErrorState error={bt.error} />;
  if (pr.status === "error") return <ErrorState error={pr.error} />;
  const b = bt.data, p = pr.data;
  const rows: [string, M][] = [["Model (baseline)", b.overall.model], ["Model + adjustments", b.model_adjusted.overall],
    ["Elo only", b.overall.elo_only], ["Closing spread (market)", b.overall.market]];
  const seasonData = b.per_season.map((s) => ({ season: String(s.season), model: s.model.mae_vs_actual,
    elo: s.elo_only.mae_vs_actual, market: s.market.mae_vs_actual }));
  const cal = calKey === "adjusted" ? b.model_adjusted.calibration : b.calibration[calKey];
  const live = b.adjustment_fits[b.adjustment_fits.length - 1];
  // Every sentence below is computed from the published results, so it stays true after each refresh.
  const marketBetter = b.per_season.filter((x) => x.market.mae_vs_actual < x.model.mae_vs_actual).length;
  const maes = seasonData.flatMap((x) => [x.model, x.elo, x.market]);
  const [lo, hi] = [Math.min(...maes), Math.max(...maes)];
  const calN = b.calibration.model.reduce((t, c) => t + c.n, 0);
  const homeGap = b.calibration.model.reduce((t, c) => t + c.n * (c.actual_rate - c.mean_predicted), 0) / calN;
  const ppi = adjDs.status === "ready" ? adjDs.data.injury_assumptions.points_per_impact : null;
  const nSims = outDs.status === "ready" ? outDs.data.n_sims.toLocaleString() : "10,000+";

  return (
    <>
      <PageHeader title="Model" subtitle="How projections are made, how well they've done out of sample, and where they fall short." />
      <div role="note" className={`rounded-xl border p-4 ${b.beats_market ? "border-good/40 bg-edge-good" : "border-serious/50 bg-edge-bad"}`}>
        <div className="flex items-center gap-2 font-semibold">
          <Pill tone={b.beats_market ? "good" : "bad"}>{b.beats_market ? "Beats the market" : "Does not beat the market"}</Pill>
          Honest bottom line
        </div>
        <p className="mt-1 text-sm">{b.headline}</p>
      </div>

      <Card className="mt-4" title="Out-of-sample results" subtitle={`Walk-forward backtest, FBS vs FBS games with a closing line, ${b.test_seasons[0]}–${b.test_seasons.at(-1)}`}>
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable table">
          <SimpleTable head={["Predictor", "Games", "Avg miss (pts)", "Brier", "Log loss", "Picked winner", "vs spread", "vs spread, 3+ pt disagreements"]}
            rows={rows.map(([name, m]) => [name, m.games.toLocaleString(), m.mae_vs_actual.toFixed(2), m.brier.toFixed(3), m.log_loss.toFixed(3),
              pct(m.straight_up_accuracy, 1),
              m.ats_win_pct == null ? "—" : `${m.ats_wins}-${m.ats_losses} (${pct(m.ats_win_pct, 1)})`,
              m.ats_edge3_win_pct == null ? "—" : `${m.ats_edge3_wins}-${m.ats_edge3_losses} (${pct(m.ats_edge3_win_pct, 1)})`])} />
        </div>
        <p className="mt-2 text-xs text-ink-3">Lower is better for average miss, Brier and log loss. "vs spread" counts which side of the closing line
          the model's margin fell on. It measures accuracy only; 50% is what a coin flip gets.
          Projected totals: model misses by {b.totals.overall.model_mae.toFixed(2)} pts on average vs {b.totals.overall.market_mae.toFixed(2)} for the closing total.</p>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Average miss by season" subtitle="Mean absolute error vs the actual final margin, points (lower is better)" meta={bt.meta}
          table={<SimpleTable head={["Season", "Model", "Elo only", "Market"]} rows={seasonData.map((s) => [s.season, s.model.toFixed(2), s.elo.toFixed(2), s.market.toFixed(2)])} />}>
          <Legend items={[{ label: "Model", color: C.cat[0] }, { label: "Elo only", color: C.cat[1] }, { label: "Closing spread", color: C.cat[2] }]} />
          <LineSeriesChart data={seasonData} x="season" xLabel="Test season" yLabel="Avg miss (pts)"
            series={[{ key: "model", color: C.cat[0], label: "Model" }, { key: "elo", color: C.cat[1], label: "Elo only" }, { key: "market", color: C.cat[2], label: "Closing spread" }]}
            tip={(s) => ({ title: s.season, rows: [["Model", s.model.toFixed(2)], ["Elo only", s.elo.toFixed(2)], ["Closing spread", s.market.toFixed(2)]] })} />
          <p className="text-xs text-ink-3">The y-axis is zoomed to the {lo.toFixed(1)}–{hi.toFixed(1)} pt range so the gaps are visible; the three predictors are closer than they look.</p>
        </ChartFrame>
        <ChartFrame title="Calibration" subtitle="When the predictor says X%, how often does the home team win? Dots on the dashed line = well calibrated; dot size = games."
          meta={bt.meta}
          table={<SimpleTable head={["Bin", "Games", "Predicted", "Actual", "95% CI"]} rows={cal.map((c) =>
            [`${pct(c.bin_low)}–${pct(c.bin_high)}`, c.n, pct(c.mean_predicted, 1), pct(c.actual_rate, 1), `${pct(c.ci95_low, 0)}–${pct(c.ci95_high, 0)}`])} />}>
          <div className="mb-1 w-56"><Select label="Predictor" value={calKey} onChange={setCalKey} options={[
            { value: "model", label: "Model (baseline)" }, { value: "adjusted", label: "Model + adjustments" },
            { value: "elo_only", label: "Elo only" }, { value: "market", label: "Closing spread" }]} /></div>
          <CalibrationChart data={cal} color={C.cat[0]}
            tip={(c) => ({ title: `Predicted ${pct(c.bin_low)}–${pct(c.bin_high)}`, rows: [["Games", c.n], ["Avg predicted", pct(c.mean_predicted, 1)],
              ["Actual", pct(c.actual_rate, 1)], ["95% CI", `${pct(c.ci95_low)}–${pct(c.ci95_high)}`]] })} />
        </ChartFrame>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="How a projection is built">
          <ol className="list-decimal space-y-1.5 pl-5 text-sm">
            <li><strong>Ratings before kickoff:</strong> our margin-aware Elo and an opponent-adjusted EPA/play rating, refit every week
              using only earlier games.</li>
            <li><strong>Margin:</strong> home field ({p.home_field_points.toFixed(1)} ± {p.home_field_points_se.toFixed(1)} pts, fitted) +
              {" "}{p.points_per_100_elo.toFixed(1)} pts per 100 Elo + {p.points_per_0_1_epa_edge.toFixed(1)} pts per 0.1 EPA/play edge.</li>
            <li><strong>Win probability:</strong> normal curve with SD {p.margin_model.sigma.toFixed(1)} pts (the model's historical miss), trained on {p.margin_model.n_train.toLocaleString()} games.</li>
            <li><strong>Score:</strong> a totals model (both offenses' EPA + pace) gives combined points; each team's score = (total ± margin) / 2.</li>
            <li><strong>Adjustments:</strong> rest, travel, turnover regression and recent form (fitted), weather on the total (fitted), injuries (manual).</li>
            <li><strong>Simulation:</strong> {nSims} games for score distributions; {nSims} seasons for win totals and the SEC race.</li>
          </ol>
          <p className="mt-2 text-xs text-ink-3">Full methodology: docs/model.md in the project repository.</p>
        </Card>
        <Card title="Adjustment effects" subtitle={`Live coefficients, fitted on out-of-sample residuals from ${live.fitted_on}`}>
          <SimpleTable head={["Adjustment", "Effect per unit", "95% CI", "Significant?"]}
            rows={[...live.margin, ...live.total].map((a) => [`${a.label} (${a.unit})`, `${signed(a.coef, 2)} pts`,
              a.ci95_low == null ? "—" : `${signed(a.ci95_low, 2)} to ${signed(a.ci95_high, 2)}`, a.significant ? "yes" : "no"])} />
          <p className="mt-2 text-xs text-ink-3">Weather and rest effects apply to totals and margins respectively. Non-significant effects stay in the
            model with their fitted (small) size, and you can switch any of them off on the Matchup page.</p>
        </Card>
      </div>

      <Card className="mt-4" title="Limitations">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>The closing spread had a smaller average miss than this model in {marketBetter} of {b.per_season.length} seasons tested.
            Treat projections as an explainable view of team strength, not an edge.</li>
          <li>Out of sample, home teams won {Math.abs(homeGap * 100).toFixed(1)} percentage points {homeGap >= 0 ? "more" : "less"} often than predicted:
            one home-field value is fitted on earlier seasons, so a trend in home-field advantage shows up with a lag.</li>
          <li>No roster, recruiting or transfer-portal information. Early-season ratings rely on last season.</li>
          <li>Injury effects are a stated assumption (impact × {ppi ?? "—"} pts × chance of missing × depth weight), not estimated from data.</li>
          <li>Score distributions assume normal errors; real football scores cluster on 3s and 7s.</li>
          <li>SEC tiebreakers are approximated with random tiebreaks; no playoff probability is shown because selection is by committee.</li>
          <li>Public play-by-play has no personnel, play-action or blitz data.</li>
        </ul>
        <SourceNote meta={bt.meta} />
      </Card>
    </>
  );
}
