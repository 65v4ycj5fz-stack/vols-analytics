import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { C } from "../components/chartColors";
import { ColumnChart } from "../components/lazyCharts";
import { Card, ChartFrame, Empty, ErrorState, Legend, Loading, PageHeader, Pill, Select, SimpleTable, StatTile } from "../components/ui";
import { all, useDataset, type GameProjection, type MetricDef, type Projections } from "../lib/data";
import { dateLabel, fmt, isNum, ordinal, pct, signed, siteWord, spreadLabel } from "../lib/format";
import { normCdf, simulateGame } from "../lib/model";

type Row = Record<string, unknown> & { team: string };
const TEAM = "Tennessee";
const COMPARE = ["points_pg", "points_allowed_pg", "off_epa", "def_epa", "off_success", "def_success", "off_rush_epa",
  "def_rush_epa", "off_pass_epa", "def_pass_epa", "off_explosiveness", "def_havoc", "third_down_pct",
  "third_down_pct_allowed", "off_pts_per_opp", "def_pts_per_opp", "turnover_margin", "plays_pg", "early_down_pass_rate",
  "proe", "def_sack_rate", "sack_rate_allowed", "rz_td_rate", "def_rz_td_rate", "go_rate"];

export default function Matchup() {
  const { gameId } = useParams();
  const nav = useNavigate();
  const s = all<[Projections, Row[], MetricDef[]]>(useDataset<Projections>("projections"),
    useDataset<Row[]>("team_profiles"), useDataset<MetricDef[]>("metrics"));
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [proj, profiles, metrics] = s.values;
  const games = proj.data.games;
  const g = games.find((x) => String(x.game_id) === gameId) ?? games.find((x) => !x.completed) ?? games[games.length - 1];
  return (
    <>
      <PageHeader title={`${TEAM} ${siteWord(g.site)} ${g.opponent}`}
        subtitle={`Week ${g.week} · ${dateLabel(g.start_date, true)}${g.completed ? " · final" : ""}`}>
        <div className="w-64">
          <Select label="Choose a game" value={String(g.game_id)} onChange={(v) => nav(`/matchup/${v}`)}
            options={games.map((x) => ({ value: String(x.game_id), label: `Wk ${x.week}: ${siteWord(x.site)} ${x.opponent}${x.completed ? ` (${x.actual?.team}-${x.actual?.opp})` : ""}` }))} />
        </div>
      </PageHeader>
      <MatchupBody key={g.game_id} g={g} model={proj.data.model} profiles={profiles.data} metrics={metrics.data} />
    </>
  );
}

function MatchupBody({ g, model, profiles, metrics }:
  { g: GameProjection; model: Projections["model"]; profiles: Row[]; metrics: MetricDef[] }) {
  const factor = (k: string) => g.factors.find((f) => f.key === k)?.points ?? 0;
  const fitted = g.adjustments.filter((a) => a.source === "fitted");
  const inj = g.adjustments.find((a) => a.key === "injuries");
  const injTeam0 = (inj?.players?.team ?? []).reduce((t, p) => t + p.points, 0);
  const injOpp0 = (inj?.players?.opponent ?? []).reduce((t, p) => t + p.points, 0);
  const siteSign = g.site === "home" ? 1 : g.site === "away" ? -1 : 0;
  const hfa0 = model.margin_coef.site_home;

  const [hfa, setHfa] = useState(hfa0);
  const [formMult, setFormMult] = useState(1);
  const [on, setOn] = useState<Record<string, boolean>>(() => Object.fromEntries(fitted.map((a) => [a.key, true])));
  const [injTeam, setInjTeam] = useState(injTeam0);
  const [injOpp, setInjOpp] = useState(injOpp0);
  const changed = hfa !== hfa0 || formMult !== 1 || injTeam !== injTeam0 || injOpp !== injOpp0 || Object.values(on).some((v) => !v);

  const margin = factor("elo") + factor("offense_matchup") + factor("defense_matchup") + siteSign * hfa
    + fitted.reduce((t, a) => t + (on[a.key] ? a.points * (a.key === "form_edge" ? formMult : 1) : 0), 0)
    - injTeam + injOpp;
  const total = g.projection.total;
  const sim = useMemo(() => simulateGame(margin, total, model.sigma_margin, model.sigma_total, model.rho, model.n_sims),
    [margin, total, model]);
  const wp = normCdf(margin / model.sigma_margin);
  // 3-point bins (1-3, 4-6, ... and -1 to -3, ...): single-point bars alternate odd/even because of rounding
  const hist = useMemo(() => {
    const bins = new Map<number, number>();
    for (const h of sim.marginHist) {
      const b = h.value > 0 ? Math.ceil(h.value / 3) : -Math.ceil(-h.value / 3);
      if (Math.abs(b) <= 15) bins.set(b, (bins.get(b) ?? 0) + h.share);
    }
    return [...bins.entries()].sort((a, b) => a[0] - b[0]).map(([b, share]) => ({
      value: b * 3 - Math.sign(b), share,
      label: b > 0 ? `+${b * 3 - 2} to +${b * 3}` : `${b * 3 + 2} to ${b * 3}` }));
  }, [sim]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatTile accent label={changed ? "Your projection" : "Projected score"}
          value={`${Math.round((total + margin) / 2)}-${Math.round((total - margin) / 2)}`} sub={`${TEAM} ${signed(margin)}`} />
        <StatTile accent label="Win probability" value={pct(wp)} sub={`${sim.n.toLocaleString()} sims: ${pct(sim.winProb)}`} />
        <StatTile label="80% margin range" value={`${signed(margin - 1.2816 * model.sigma_margin, 0)} to ${signed(margin + 1.2816 * model.sigma_margin, 0)}`}
          sub={`error SD ${model.sigma_margin.toFixed(1)} pts`} />
        <StatTile label="One-score game" value={pct(sim.oneScore)} sub="final margin ≤ 8" />
        <StatTile label={g.completed ? "Final" : "Closing spread"}
          value={g.completed && g.actual ? `${g.actual.team}-${g.actual.opp}` : spreadLabel(g.market.spread)}
          sub={g.completed ? `closing spread ${spreadLabel(g.market.spread)}` : "comparison only"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <ChartFrame title="Simulated final margin" subtitle={`${TEAM} points minus ${g.opponent} points, in 3-point bins; share of ${sim.n.toLocaleString()} simulated games`}
            table={<SimpleTable head={["Margin (pts)", "Share"]} rows={hist.map((h) => [h.label, pct(h.share, 1)])} />}
            note="Normal approximation around the projection; real scores cluster on 3s and 7s, so single scores are less certain than the overall shape.">
            <Legend items={[{ label: `${TEAM} wins`, color: C.team }, { label: `${g.opponent} wins`, color: C.opp }]} />
            <ColumnChart data={hist} x="value" y="share" xLabel={`Margin (pts, ${TEAM} perspective)`} yLabel="Share of sims"
              colorFor={(h) => (h.value > 0 ? C.team : C.opp)} yFormat={(v) => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`}
              tip={(h) => ({ title: `${TEAM} by ${h.label} pts`, rows: [["Share of simulations", pct(h.share, 1)]] })} />
          </ChartFrame>
        </div>
        <Card className="lg:col-span-2" title="Adjust the model" subtitle="Changes recompute the projection and rerun the simulation in your browser."
          actions={changed ? <button type="button" className="rounded-md border border-line px-2 py-1 text-xs" onClick={() => {
            setHfa(hfa0); setFormMult(1); setInjTeam(injTeam0); setInjOpp(injOpp0); setOn(Object.fromEntries(fitted.map((a) => [a.key, true])));
          }}>Reset</button> : undefined}>
          <Slider label="Home-field advantage" value={hfa} min={0} max={6} step={0.1} onChange={setHfa}
            display={`${hfa.toFixed(1)} pts${siteSign === 0 ? " (neutral site: no effect)" : ""}`} hint={`fitted: ${hfa0.toFixed(1)} pts`} />
          <Slider label="Recent-form weighting" value={formMult} min={0} max={2} step={0.1} onChange={setFormMult}
            display={`${formMult.toFixed(1)}× fitted`} hint="0 = every game counts equally; 1 = fitted weight" />
          <Slider label={`${TEAM} injuries`} value={injTeam} min={0} max={10} step={0.5} onChange={setInjTeam}
            display={`−${injTeam.toFixed(1)} pts`} hint={`from injuries.csv: ${injTeam0.toFixed(1)}`} />
          <Slider label={`${g.opponent} injuries`} value={injOpp} min={0} max={10} step={0.5} onChange={setInjOpp}
            display={`−${injOpp.toFixed(1)} pts`} hint={`from injuries.csv: ${injOpp0.toFixed(1)}`} />
          <fieldset className="mt-3">
            <legend className="text-xs font-medium text-ink-2">Fitted adjustments</legend>
            {fitted.map((a) => (
              <label key={a.key} className="mt-1 flex items-center justify-between gap-2 text-sm">
                <span><input type="checkbox" checked={on[a.key]} onChange={(e) => setOn({ ...on, [a.key]: e.target.checked })} className="mr-2 accent-[var(--brand)]" />
                  {a.label}</span>
                <span className="tabular text-ink-2">{signed(a.points * (a.key === "form_edge" ? formMult : 1))}
                  {a.significant ? "" : <span title="Not statistically significant (95%)"> ⁿˢ</span>}</span>
              </label>
            ))}
            <p className="mt-1 text-xs text-ink-3">ⁿˢ = coefficient not significant at 95%; kept but shown so you can switch it off.</p>
          </fieldset>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Why the model says this" subtitle="Model factors add up to the projected margin (before your slider changes).">
          <ul className="space-y-1.5 text-sm">
            {g.factors.map((f) => (
              <li key={f.key} className="flex gap-2"><span className="tabular w-16 shrink-0 font-semibold">
                <span aria-hidden>{f.points >= 0 ? "▲" : "▼"}</span> {signed(f.points)}</span><span>{f.text}</span></li>
            ))}
            <li className="flex gap-2 border-t border-line pt-1.5 font-semibold"><span className="tabular w-16">{signed(g.projection.margin)}</span>
              <span>Projected margin</span></li>
          </ul>
          <h3 className="mt-4 text-sm font-semibold">Run/pass breakdown (descriptive)</h3>
          <ul className="mt-1 space-y-1 text-sm text-ink-2">{g.split_edges.map((e) => <li key={e.key}>{e.text}</li>)}</ul>
        </Card>
        <Card title="Keys to the game" subtitle="Generated from the largest opponent-adjusted edges and tendency stats">
          {g.keys_to_game.length ? <ol className="list-decimal space-y-1.5 pl-5 text-sm">{g.keys_to_game.map((k) => <li key={k}>{k}</li>)}</ol>
            : <Empty title="No standout edges" />}
          <h3 className="mt-4 text-sm font-semibold">Conditions</h3>
          <p className="text-sm text-ink-2">{weatherText(g)}</p>
          {g.total_adjustments.some((a) => a.points !== 0) && (
            <p className="mt-1 text-xs text-ink-3">Weather adjusts the projected total by {signed(g.total_adjustments.reduce((t, a) => t + a.points, 0))} pts.</p>
          )}
        </Card>
      </div>

      <SideBySide opp={g.opponent} profiles={profiles} metrics={metrics} />
    </div>
  );
}

function weatherText(g: GameProjection): string {
  const w = g.weather;
  if (!w) return "No weather data (forecasts appear about two weeks before kickoff).";
  if (w.kind === "indoor") return "Indoor stadium.";
  return `${w.kind === "forecast" ? "Forecast" : "Observed"}: ${Math.round(w.temp_f ?? 0)}°F, wind ${Math.round(w.wind_mph ?? 0)} mph, `
    + `precipitation ${(w.precip_mm ?? 0).toFixed(1)} mm/h (Open-Meteo).`;
}

function Slider({ label, value, min, max, step, onChange, display, hint }:
  { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; display: string; hint: string }) {
  return (
    <label className="mt-2 block text-sm">
      <span className="flex justify-between"><span className="font-medium">{label}</span><span className="tabular text-ink-2">{display}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-[var(--brand)]" aria-valuetext={display} />
      <span className="text-xs text-ink-3">{hint}</span>
    </label>
  );
}

function SideBySide({ opp, profiles, metrics }: { opp: string; profiles: Row[]; metrics: MetricDef[] }) {
  const a = profiles.find((r) => r.team === TEAM) ?? ({} as Row), b = profiles.find((r) => r.team === opp) ?? ({} as Row);
  if (!b.team) return <Card title="Season stats"><Empty title={`${opp} is not an FBS team`}>Season stat comparisons cover FBS teams only.</Empty></Card>;
  const defs = COMPARE.map((k) => metrics.find((m) => m.key === k)).filter(Boolean) as MetricDef[];
  return (
    <Card title="Season stats, side by side" subtitle="National rank in parentheses. Highlighted cell = better rank; pace/style stats aren't highlighted.">
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable table">
        <table className="w-full text-sm">
          <thead><tr className="text-xs text-ink-2">
            <th scope="col" className="px-2 py-1 text-left">Stat</th>
            <th scope="col" className="px-2 py-1 text-right">{TEAM}</th>
            <th scope="col" className="px-2 py-1 text-right">{opp}</th>
          </tr></thead>
          <tbody>
            {defs.map((m) => {
              const ra = a[`${m.key}_rank`], rb = b[`${m.key}_rank`];
              const better = !m.neutral && isNum(ra) && isNum(rb) && ra !== rb ? (ra < rb ? "a" : "b") : null;
              const cell = (v: unknown, r: unknown, me: boolean) => (
                <td className={`tabular px-2 py-1 text-right ${me ? "bg-edge-good font-semibold" : ""}`}>
                  {me && <span aria-label="edge">▲ </span>}{fmt(v, m.unit)} <span className="text-xs text-ink-3">({ordinal(r)})</span>
                </td>);
              return (
                <tr key={m.key} className="border-t border-line">
                  <th scope="row" className="px-2 py-1 text-left font-normal" title={m.definition}>{m.label}
                    {m.neutral && <Pill>style</Pill>}</th>
                  {cell(a[m.key], ra, better === "a")}{cell(b[m.key], rb, better === "b")}
                </tr>);
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
