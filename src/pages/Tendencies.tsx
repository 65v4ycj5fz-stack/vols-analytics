import { Fragment, useState } from "react";
import { C } from "../components/chartColors";
import { GroupScatter, HBarChart, LineSeriesChart } from "../components/lazyCharts";
import { Card, ChartFrame, Empty, ErrorState, Legend, Loading, PageHeader, Select, SimpleTable } from "../components/ui";
import { all, useDataset, type Meta } from "../lib/data";
import { ordinal, pct, signed } from "../lib/format";

interface Split { team: string; side: string; split: string; split_value: string; plays: number; pass_rate: number;
  success_rate: number; epa_per_play: number | null; explosive_rate: number; sack_rate: number | null; small_sample: boolean;
  down: number | null; dist_bucket: string | null; games?: number }
interface Fourth { team: string; week: number; defense: string; period: number; clock: string; distance: number; ytg: number;
  margin: number; fourth_decision: "go" | "punt" | "fg"; xgo: number; converted: number | null; text: string }
interface Proe { team: string; opponent: string; week: number; n: number; actual_rate: number; expected_rate: number;
  over_expected: number; ci95_low: number; ci95_high: number }
interface Scheme { team: string; unit: string; base_scheme: string; tempo: string | null; personnel_groupings: string | null;
  coverage_shells: string | null; front: string | null; blitz_style: string | null; key_concepts: string | null; notes: string | null;
  last_updated: string; source: string }
type Summ = Record<string, number | string | null> & { team: string };

const DISTS = ["1-3", "4-6", "7-10", "11+"];
const DOWN_NAME = ["", "1st", "2nd", "3rd", "4th"];

export default function Tendencies() {
  const s = all<[Split[], Split[], Fourth[], Proe[], Summ[], Scheme[], Scheme[]]>(
    useDataset<Split[]>("tendency_splits"), useDataset<Split[]>("situational_splits"), useDataset<Fourth[]>("fourth_downs"),
    useDataset<Proe[]>("proe_by_game"), useDataset<Summ[]>("tendency_summary"), useDataset<Scheme[]>("schemes"),
    useDataset<Scheme[]>("opponent_scouting"));
  const [team, setTeam] = useState("Tennessee");
  const [side, setSide] = useState<"offense" | "defense">("offense");
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [splits, sit, fourth, proe, summ, schemes, scouting] = s.values;
  const teams = [...new Set(splits.data.map((r) => r.team))].filter((t) => t !== "FBS average");
  const sm = summ.data.find((r) => r.team === team);
  const notes = [...schemes.data, ...scouting.data].filter((r) => r.team === team);
  const sideWord = side === "offense" ? "offense" : "defense (what opponents did)";

  return (
    <>
      <PageHeader title="Schemes & Tendencies" subtitle="What each team does in each situation, from play-by-play (garbage time excluded), plus manual scheme notes.">
        <div className="flex gap-3">
          <div className="w-48"><Select label="Team" value={team} onChange={setTeam} options={teams.map((t) => ({ value: t, label: t }))} /></div>
          <div className="w-36"><Select label="Side" value={side} onChange={setSide} options={[{ value: "offense", label: "Offense" }, { value: "defense", label: "Defense" }]} /></div>
        </div>
      </PageHeader>

      {sm && <SummaryTiles s={sm} n={summ.data.length} />}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Heatmap rows={splits.data} team={team} side={side} meta={splits.meta} sideWord={sideWord} />
        <SchemeNotes notes={notes} team={team} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Situational rows={sit.data.filter((r) => r.team === team && r.side === side)} meta={sit.meta} team={team} sideWord={sideWord} />
        <FieldZone rows={splits.data.filter((r) => r.team === team && r.side === side && r.split === "field_zone")} meta={splits.meta} sideWord={sideWord} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <FourthDowns rows={fourth.data.filter((r) => r.team === team)} meta={fourth.meta} s={sm} team={team} />
        <ProeChart rows={proe.data.filter((r) => r.team === team)} meta={proe.meta} team={team} />
      </div>
    </>
  );
}

function SummaryTiles({ s, n }: { s: Summ; n: number }) {
  const t = (k: string, label: string) => ({ k, label });
  const items = [t("early_down_pass_rate", "Early-down pass rate"), t("proe", "Pass rate over expected"),
    t("shotgun_rate", "Shotgun rate"), t("no_huddle_rate", "No-huddle rate"), t("deep_pass_rate", "Deep-pass rate"),
    t("explosive_rate", "Explosive play rate"), t("def_sack_rate", "Defensive sack rate"), t("go_over_expected", "4th-down go rate vs expected")];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {items.map(({ k, label }) => {
        const v = s[k] as number | null;
        const isDiff = k === "proe" || k === "go_over_expected";
        const ci = isDiff ? s[k === "proe" ? "proe_ci_low" : "go_oe_ci_low"] as number : null;
        const ci2 = isDiff ? s[k === "proe" ? "proe_ci_high" : "go_oe_ci_high"] as number : null;
        return <div key={k} className="rounded-lg border border-line bg-surface p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
          <div className="tabular mt-1 text-xl font-bold">{isDiff ? `${signed((v ?? NaN) * 100)} pts` : pct(v, 1)}</div>
          <div className="text-xs text-ink-2">{ordinal(s[`${k}_rank`])} of {n} (most){isDiff && ci != null ? ` · 95% CI ${signed(ci * 100, 0)} to ${signed((ci2 ?? 0) * 100, 0)}` : ""}</div>
        </div>;
      })}
    </div>
  );
}

function cellColor(v: number, diverging: boolean): { bg: string; fg: string } {
  if (diverging) {
    const steps = ["--div-neg-3", "--div-neg-2", "--div-neg-1", "--div-mid", "--div-pos-1", "--div-pos-2", "--div-pos-3"];
    const i = Math.max(0, Math.min(6, Math.round(v / 0.08) + 3));
    return { bg: `var(${steps[i]})`, fg: i === 3 || i === 2 || i === 4 ? "var(--ink)" : "#fff" };
  }
  const i = Math.max(1, Math.min(7, Math.round(v * 7) || 1));
  return { bg: `var(--seq-${i}00)`, fg: i >= 4 ? "#fff" : "#141413" };
}

function Heatmap({ rows, team, side, meta, sideWord }: { rows: Split[]; team: string; side: string; meta: Meta; sideWord: string }) {
  const [mode, setMode] = useState<"rate" | "diff">("rate");
  const cell = (t: string, sd: string, d: number, b: string) =>
    rows.find((r) => r.team === t && r.side === sd && r.split === "down_distance" && r.down === d && r.dist_bucket === b);
  const data = [1, 2, 3, 4].map((d) => ({ d, cells: DISTS.map((b) => ({ b, me: cell(team, side, d, b), fbs: cell("FBS average", "offense", d, b) })) }));
  return (
    <ChartFrame title={`Pass rate by down & distance: ${team} ${sideWord}`}
      subtitle={mode === "rate" ? "Share of snaps that were passes (sacks count as passes). Number below = plays." : "Pass rate minus the FBS average in the same down & distance (percentage points)."}
      meta={meta}
      table={<SimpleTable head={["Down", ...DISTS.map((b) => `${b} to go`)]} rows={data.map((r) => [DOWN_NAME[r.d],
        ...r.cells.map((c) => c.me ? `${pct(c.me.pass_rate)} (${c.me.plays})` : "—")])} />}
      note="Hatched cells have fewer than 20 plays. Treat them as anecdotes.">
      <div className="mb-2 flex gap-2" role="group" aria-label="Color mode">
        {(["rate", "diff"] as const).map((m) => (
          <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
            className={`rounded-md border px-2 py-1 text-xs ${mode === m ? "border-brand bg-surface-2 font-semibold" : "border-line"}`}>
            {m === "rate" ? "Pass rate" : "vs FBS average"}</button>))}
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable table">
        <table className="w-full border-separate border-spacing-0.5 text-center text-sm">
          <thead><tr><th scope="col" className="w-16 text-xs text-ink-3"><span className="sr-only">Down</span></th>
            {DISTS.map((b) => <th key={b} scope="col" className="text-xs font-medium text-ink-2">{b} to go</th>)}</tr></thead>
          <tbody>{data.map((r) => (
            <tr key={r.d}><th scope="row" className="text-xs font-medium text-ink-2">{DOWN_NAME[r.d]}</th>
              {r.cells.map(({ b, me, fbs }) => {
                if (!me) return <td key={b} className="rounded-md bg-surface-2 py-3 text-xs text-ink-3">—</td>;
                const v = mode === "rate" ? me.pass_rate : me.pass_rate - (fbs?.pass_rate ?? me.pass_rate);
                const c = cellColor(v, mode === "diff");
                return (
                  <td key={b} className="rounded-md py-2" title={`${DOWN_NAME[r.d]} & ${b}: ${pct(me.pass_rate)} pass on ${me.plays} plays (FBS ${pct(fbs?.pass_rate)}); success ${pct(me.success_rate)}`}
                    style={{ background: c.bg, color: c.fg, backgroundImage: me.small_sample ? "repeating-linear-gradient(45deg, transparent 0 5px, rgba(127,127,127,.35) 5px 7px)" : undefined }}>
                    <div className="tabular font-semibold">{mode === "rate" ? pct(v) : `${signed(v * 100, 0)}`}</div>
                    <div className="tabular text-[10px] opacity-90">{me.plays} plays</div>
                  </td>);
              })}</tr>))}</tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-ink-3" aria-hidden>
        {mode === "rate" ? <>0% <span className="h-2 w-32 rounded" style={{ background: "linear-gradient(90deg, var(--seq-100), var(--seq-400), var(--seq-700))" }} /> 100% pass</>
          : <>runs more <span className="h-2 w-32 rounded" style={{ background: "linear-gradient(90deg, var(--div-neg-3), var(--div-mid), var(--div-pos-3))" }} /> passes more</>}
      </div>
    </ChartFrame>
  );
}

function SchemeNotes({ notes, team }: { notes: Scheme[]; team: string }) {
  const fields: [keyof Scheme, string][] = [["tempo", "Tempo"], ["personnel_groupings", "Personnel"], ["front", "Front"],
    ["coverage_shells", "Coverage"], ["blitz_style", "Pressure"], ["key_concepts", "Key concepts"], ["notes", "Notes"]];
  return (
    <Card title={`${team} scheme notes`} subtitle="Manual entries. Personnel, play-action and blitz rates aren't in public play-by-play, so this is where film notes go.">
      {notes.length === 0 ? (
        <Empty title="No scheme notes entered">
          Add rows to <code>data/manual/{team === "Tennessee" ? "schemes" : "opponent_scouting"}.csv</code> (or the linked Google Sheet), with a source.
          The numbers on this page come from play-by-play and don't need manual entry.
        </Empty>
      ) : (
        <div className="space-y-3">{notes.map((n) => (
          <div key={n.unit} className="rounded-lg border border-line p-3">
            <div className="text-xs font-semibold uppercase text-ink-3">{n.unit}</div>
            <div className="font-semibold">{n.base_scheme}</div>
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              {fields.filter(([k]) => n[k]).map(([k, l]) => <Fragment key={k}><dt className="text-ink-3">{l}</dt><dd>{n[k]}</dd></Fragment>)}
            </dl>
            <div className="mt-1 text-xs text-ink-3">Source: {n.source} · updated {n.last_updated}</div>
          </div>))}</div>
      )}
    </Card>
  );
}

function Situational({ rows, meta, team, sideWord }: { rows: Split[]; meta: Meta; team: string; sideWord: string }) {
  const data = rows.map((r) => ({ ...r, label: r.split_value, epa: r.epa_per_play ?? 0 }));
  if (!data.length) return <Card title="Situational splits"><Empty title="No play-by-play for this team" /></Card>;
  return (
    <ChartFrame title={`Situational splits: ${team} ${sideWord}`} subtitle="EPA per play (points added per snap; for a defense, lower is better)" meta={meta}
      table={<SimpleTable head={["Split", "Value", "Games", "Plays", "EPA/play", "Success", "Pass rate"]}
        rows={rows.map((r) => [r.split, r.split_value, r.games ?? "—", r.plays, signed(r.epa_per_play, 3), pct(r.success_rate), pct(r.pass_rate)])} />}
      note="Ranked = AP Top 25 entering that week. Splits with few games are noisy; check the plays column in the table view.">
      <HBarChart data={data} y="label" x="epa" xLabel="EPA per play" xFormat={(v) => v.toFixed(2)}
        colorFor={() => C.team}
        tip={(d) => ({ title: `${d.split}: ${d.split_value}`, rows: [["EPA/play", signed(d.epa_per_play, 3)], ["Success rate", pct(d.success_rate)],
          ["Pass rate", pct(d.pass_rate)], ["Plays", d.plays], ["Games", d.games ?? "—"]] })} />
    </ChartFrame>
  );
}

function FieldZone({ rows, meta, sideWord }: { rows: Split[]; meta: Meta; sideWord: string }) {
  const order = ["Backed up (own 1-20)", "Own 21-50", "Opp 21-49", "Red zone (opp 1-20)"];
  const data = order.map((z) => rows.find((r) => r.split_value === z)).filter(Boolean).map((r) => ({ ...r!, rate: r!.pass_rate * 100 }));
  if (!data.length) return <Card title="Field position"><Empty title="No data" /></Card>;
  return (
    <ChartFrame title={`Pass rate by field position: ${sideWord}`} subtitle="Percent of snaps that were passes, own goal line → opponent goal line" meta={meta}
      table={<SimpleTable head={["Zone", "Plays", "Pass rate", "Success", "EPA/play"]} rows={data.map((r) => [r.split_value, r.plays, pct(r.pass_rate), pct(r.success_rate), signed(r.epa_per_play, 3)])} />}>
      <HBarChart data={data} y="split_value" x="rate" xLabel="Pass rate (%)" colorFor={() => C.team} xFormat={(v) => `${v}%`}
        tip={(d) => ({ title: d.split_value, rows: [["Pass rate", pct(d.pass_rate)], ["Plays", d.plays], ["Success", pct(d.success_rate)]] })} />
    </ChartFrame>
  );
}

function FourthDowns({ rows, meta, s, team }: { rows: Fourth[]; meta: Meta; s?: Summ; team: string }) {
  if (!rows.length) return <Card title="4th-down decisions"><Empty title="No 4th downs recorded" /></Card>;
  const groups = [{ label: "Went for it", key: "go", color: C.cat[2] }, { label: "Punted", key: "punt", color: C.cat[0] }, { label: "Field goal", key: "fg", color: C.cat[1] }]
    .map((g) => ({ ...g, data: rows.filter((r) => r.fourth_decision === g.key) }));
  const notable = rows.filter((r) => (r.fourth_decision !== "go" && r.xgo >= 0.5) || (r.fourth_decision === "go" && r.xgo < 0.25));
  return (
    <ChartFrame title={`4th-down decisions: ${team}`} subtitle="Each dot is a non-garbage-time 4th down: yards needed (across) vs yards to the end zone (higher = closer to scoring)"
      meta={meta}
      table={<SimpleTable head={["Wk", "Opp", "Q", "Clock", "Down & dist", "Yds to goal", "Score", "Decision", "Typical go %", "Converted"]}
        rows={rows.map((r) => [r.week, r.defense, r.period, r.clock, `4th & ${r.distance}`, r.ytg, signed(r.margin, 0), r.fourth_decision, pct(r.xgo), r.converted == null ? "—" : r.converted ? "yes" : "no"])} />}
      note={s ? `Went for it on ${pct(s.go_rate as number)} vs ${pct(s.go_rate_expected as number)} for a typical FBS coach in the same spots (${signed((s.go_over_expected as number) * 100)} pts; 95% CI ${signed((s.go_oe_ci_low as number) * 100, 0)} to ${signed((s.go_oe_ci_high as number) * 100, 0)}). "Typical" describes peers, not the optimal call.` : undefined}>
      <Legend items={groups.map((g) => ({ label: `${g.label} (${g.data.length})`, color: g.color }))} />
      <GroupScatter groups={groups} x="distance" y="ytg" xLabel="Yards to go for a first down" yLabel="Yards to the end zone"
        yDomain={[0, 100]}
        tip={(r) => ({ title: `Wk ${r.week} vs ${r.defense}: 4th & ${r.distance} at the ${r.ytg <= 50 ? "opp " + r.ytg : "own " + (100 - r.ytg)}`,
          rows: [["Decision", r.fourth_decision], ["Typical coach goes", pct(r.xgo)], ["Score margin", signed(r.margin, 0)], ["Q / clock", `Q${r.period} ${r.clock}`],
            ...(r.converted != null ? [["Converted", r.converted ? "yes" : "no"] as [string, string]] : [])] })} />
      {notable.length > 0 && (
        <div className="mt-2 text-xs text-ink-2"><span className="font-semibold">Against the grain ({notable.length}):</span>{" "}
          {notable.slice(0, 4).map((r) => `wk ${r.week} 4th & ${r.distance} (${r.fourth_decision}, typical go ${pct(r.xgo)})`).join("; ")}</div>
      )}
    </ChartFrame>
  );
}

function ProeChart({ rows, meta, team }: { rows: Proe[]; meta: Meta; team: string }) {
  const data = [...rows].sort((a, b) => a.week - b.week).map((r) => ({ ...r, oe: r.over_expected * 100, lo: r.ci95_low * 100, hi: r.ci95_high * 100 }));
  if (!data.length) return <Card title="Pass rate over expected"><Empty title="No data" /></Card>;
  return (
    <ChartFrame title={`Pass rate over expected by game: ${team}`} subtitle="Percentage points above (+) or below (−) what an average FBS team calls in the same situations"
      meta={meta}
      table={<SimpleTable head={["Wk", "Opponent", "Plays", "Actual", "Expected", "Over expected", "95% CI"]}
        rows={data.map((r) => [r.week, r.opponent, r.n, pct(r.actual_rate), pct(r.expected_rate), signed(r.oe), `${signed(r.lo, 0)} to ${signed(r.hi, 0)}`])} />}
      note="1st–3rd down, garbage time excluded. Single games carry wide intervals (shown in the tooltip and table).">
      <LineSeriesChart data={data} x="week" xLabel="Week" yLabel="Pts over expected" series={[{ key: "oe", color: C.team, label: "PROE" }]}
        refY={{ y: 0, label: "average" }}
        tip={(r) => ({ title: `Week ${r.week} vs ${r.opponent}`, rows: [["Over expected", `${signed(r.oe)} pts`], ["95% CI", `${signed(r.lo, 0)} to ${signed(r.hi, 0)}`],
          ["Actual / expected", `${pct(r.actual_rate)} / ${pct(r.expected_rate)}`], ["Plays", r.n]] })} />
    </ChartFrame>
  );
}

