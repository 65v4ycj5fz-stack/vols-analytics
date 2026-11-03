import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { C } from "../components/chartColors";
import { LineSeriesChart } from "../components/lazyCharts";
import { DataTable } from "../components/DataTable";
import { Card, ChartFrame, ErrorState, Legend, Loading, PageHeader, Select, SimpleTable, SourceNote } from "../components/ui";
import { all, useDataset, type Meta, type MetricDef } from "../lib/data";
import { fmt, ordinal } from "../lib/format";

type Row = Record<string, unknown> & { team: string; conference: string };
const TEAM = "Tennessee";
const GROUPS = [["offense", "Offense"], ["defense", "Defense"], ["special", "Special teams & field position"], ["overall", "Overall"]] as const;
const TREND: { key: string; label: string; unit: string; opp?: string }[] = [
  { key: "points_for", label: "Points scored vs allowed", unit: "pts", opp: "points_against" },
  { key: "off_epa", label: "EPA/play: offense vs defense allowed", unit: "EPA/play", opp: "def_epa" },
  { key: "off_success", label: "Success rate: offense vs defense allowed", unit: "%", opp: "def_success" },
  { key: "off_ypp", label: "Yards per play: offense vs defense allowed", unit: "yds", opp: "def_ypp" },
  { key: "off_rush_epa", label: "Rush EPA/play: offense vs defense allowed", unit: "EPA/play", opp: "def_rush_epa" },
  { key: "off_pass_epa", label: "Pass EPA/play: offense vs defense allowed", unit: "EPA/play", opp: "def_pass_epa" },
];

export default function TeamStats() {
  const s = all<[Row[], Row[], MetricDef[], Row[]]>(useDataset<Row[]>("team_season_stats"), useDataset<Row[]>("tendency_summary"),
    useDataset<MetricDef[]>("metrics"), useDataset<Row[]>("team_game_stats"));
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [stats, tend, metrics, games] = s.values;
  return (
    <>
      <PageHeader title="Team Stats" subtitle="Season and per-game stats for Tennessee with national (FBS) and SEC ranks; 1 = best." />
      <div className="space-y-4">
        <Profile stats={stats.data} tend={tend.data} metrics={metrics.data} meta={stats.meta} />
        <Trends games={games.data} meta={games.meta} />
        <AllTeams stats={stats.data} tend={tend.data} metrics={metrics.data} meta={stats.meta} />
      </div>
    </>
  );
}

function Profile({ stats, tend, metrics, meta }: { stats: Row[]; tend: Row[]; metrics: MetricDef[]; meta: Meta }) {
  const row = { ...stats.find((r) => r.team === TEAM), ...tend.find((r) => r.team === TEAM) } as Row;
  const n = stats.length;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {GROUPS.map(([g, label]) => {
        const defs = metrics.filter((m) => m.group === g && row[m.key] !== undefined);
        return (
          <Card key={g} title={label} subtitle={`${defs.length} stats · ${n} FBS teams`}>
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-ink-2"><th scope="col" className="py-1 text-left">Stat</th>
                <th scope="col" className="py-1 text-right">Value</th><th scope="col" className="py-1 text-right">FBS</th>
                <th scope="col" className="py-1 text-right">SEC</th></tr></thead>
              <tbody>{defs.map((m) => {
                const r = row[`${m.key}_rank`] as number | null;
                const tone = m.neutral || r == null ? "" : r <= 25 ? "bg-edge-good" : r > n - 25 ? "bg-edge-bad" : "";
                return (
                  <tr key={m.key} className="border-t border-line">
                    <th scope="row" className="py-1 pr-2 text-left font-normal" title={m.definition}>{m.label}</th>
                    <td className="tabular py-1 text-right">{fmt(row[m.key], m.unit)}</td>
                    <td className={`tabular py-1 text-right ${tone}`}>{m.neutral ? <span className="text-ink-3">{ordinal(r)}*</span> : ordinal(r)}</td>
                    <td className="tabular py-1 text-right">{ordinal(row[`${m.key}_conf_rank`])}</td>
                  </tr>);
              })}</tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">Shaded: top 25 / bottom 25 nationally. * style stat (rank = most, not best). Hover a stat for its definition.</p>
          </Card>);
      })}
      <div className="lg:col-span-2"><SourceNote meta={meta} /></div>
    </div>
  );
}

function Trends({ games, meta }: { games: Row[]; meta: Meta }) {
  const [key, setKey] = useState(TREND[0].key);
  const t = TREND.find((x) => x.key === key)!;
  const mine = games.filter((g) => g.team === TEAM).sort((a, b) => (a.week as number) - (b.week as number));
  const fbsAvg = useMemo(() => {
    const v = games.map((g) => g[t.key]).filter((x): x is number => typeof x === "number");
    return v.reduce((a, b) => a + b, 0) / v.length;
  }, [games, t.key]);
  const data = mine.map((g) => ({ week: g.week as number, opponent: g.opponent as string, a: g[t.key] as number, b: g[t.opp!] as number }));
  const scale = t.unit === "%" ? 100 : 1;
  const shown = data.map((d) => ({ ...d, a: d.a * scale, b: d.b * scale }));
  return (
    <ChartFrame title={`Game by game: ${t.label}`} subtitle={`${TEAM} 2026, by week. Units: ${t.unit === "%" ? "percent" : t.unit}. Dashed line = FBS average per team-game.`}
      meta={meta}
      table={<SimpleTable head={["Week", "Opponent", "Offense", "Defense allowed"]}
        rows={data.map((d) => [d.week, d.opponent, fmt(d.a, t.unit), fmt(d.b, t.unit)])} />}>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <Legend items={[{ label: `${TEAM} offense`, color: C.team }, { label: "Allowed by defense", color: C.opp }]} />
        <div className="w-72"><Select label="Stat" value={key} onChange={setKey} options={TREND.map((x) => ({ value: x.key, label: x.label }))} /></div>
      </div>
      <LineSeriesChart data={shown} x="week" xLabel="Week" yLabel={t.unit === "%" ? "%" : t.unit}
        series={[{ key: "a", color: C.team, label: "Offense" }, { key: "b", color: C.opp, label: "Defense allowed" }]}
        refY={{ y: fbsAvg * scale, label: "FBS avg" }}
        tip={(d) => ({ title: `Week ${d.week} vs ${d.opponent}`, rows: [["Offense", fmt(d.a / scale, t.unit)], ["Defense allowed", fmt(d.b / scale, t.unit)]] })} />
    </ChartFrame>
  );
}

function AllTeams({ stats, tend, metrics, meta }: { stats: Row[]; tend: Row[]; metrics: MetricDef[]; meta: Meta }) {
  const [group, setGroup] = useState<string>("offense");
  const [conf, setConf] = useState("All");
  const rows = useMemo(() => stats.map((r) => ({ ...r, ...tend.find((t) => t.team === r.team) })) as Row[], [stats, tend]);
  const confs = ["All", ...[...new Set(stats.map((r) => r.conference).filter(Boolean))].sort()];
  const defs = metrics.filter((m) => m.group === group && rows[0]?.[m.key] !== undefined);
  const columns = useMemo<ColumnDef<Row, unknown>[]>(() => [
    { accessorKey: "team", header: "Team", meta: { align: "left" },
      cell: (c) => <span className={c.getValue() === TEAM ? "font-bold" : ""}>{c.getValue() as string}</span> },
    { accessorKey: "conference", header: "Conf", meta: { align: "left", hideSm: true } },
    ...defs.map<ColumnDef<Row, unknown>>((m) => ({
      id: m.key, header: m.label, accessorFn: (r) => (r[m.key] ?? undefined) as number | undefined, sortUndefined: "last",
      cell: (c) => <span title={`FBS rank ${ordinal(c.row.original[`${m.key}_rank`])}`}>{fmt(c.getValue(), m.unit)}</span>,
    })),
  ], [defs]);
  const data = conf === "All" ? rows : rows.filter((r) => r.conference === conf);
  return (
    <Card title="All FBS teams" subtitle="Sort any column; hover a value for its national rank.">
      <div className="mb-2 flex flex-wrap gap-3">
        <div className="w-48"><Select label="Stat group" value={group} onChange={setGroup} options={GROUPS.map(([v, l]) => ({ value: v, label: l }))} /></div>
        <div className="w-48"><Select label="Conference" value={conf} onChange={setConf} options={confs.map((c) => ({ value: c, label: c }))} /></div>
      </div>
      <DataTable data={data} columns={columns} filterPlaceholder="Filter teams…" caption="FBS team stats"
        initialSort={[{ id: defs[0]?.key ?? "team", desc: defs[0]?.higher_is_better ?? false }]}
        rowClassName={(r) => (r.team === TEAM ? "bg-surface-2" : "")} />
      <SourceNote meta={meta} extra="Values are season totals/averages to date; ranks are among FBS teams only." />
    </Card>
  );
}
