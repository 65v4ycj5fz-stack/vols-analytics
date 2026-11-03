import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { DataTable } from "../components/DataTable";
import { Card, Empty, ErrorState, Loading, PageHeader, Select, SourceNote, StatTile, StatusBadge } from "../components/ui";
import { all, useDataset, type Projections } from "../lib/data";
import { ago, dateLabel, pct, siteWord } from "../lib/format";

export interface InjuryRow {
  team: string; player: string; position: string; status: string; injury_area: string | null; date_reported: string;
  expected_return: string | null; source_url: string | null; impact_rating: number; last_updated: string; source: string;
  prob_out?: number | null; depth_weight?: number | null; model_points?: number | null;
}
const ORDER = ["out", "doubtful", "questionable", "probable", "available"];
interface Assumptions { injury_assumptions: { points_per_impact: number; status_prob_out: Record<string, number>; depth_weight: Record<string, number> } }

export default function Injuries() {
  const s = all<[InjuryRow[], Projections, Assumptions]>(useDataset<InjuryRow[]>("injuries"), useDataset<Projections>("projections"),
    useDataset<Assumptions>("adjustments_model"));
  const [team, setTeam] = useState("All");
  const columns = useMemo<ColumnDef<InjuryRow, unknown>[]>(() => [
    { accessorKey: "player", header: "Player", meta: { align: "left" } },
    { accessorKey: "team", header: "Team", meta: { align: "left", hideSm: true } },
    { accessorKey: "position", header: "Pos", meta: { align: "left" } },
    { accessorKey: "status", header: "Status", meta: { align: "left" }, sortingFn: (a, b) =>
        ORDER.indexOf(a.original.status) - ORDER.indexOf(b.original.status),
      cell: (c) => <StatusBadge status={c.getValue() as string} /> },
    { accessorKey: "injury_area", header: "Injury", meta: { align: "left", hideSm: true }, cell: (c) => (c.getValue() as string) ?? "—" },
    { accessorKey: "expected_return", header: "Expected return", meta: { align: "left", hideSm: true }, cell: (c) => (c.getValue() as string) ?? "—" },
    { accessorKey: "impact_rating", header: "Impact (0-5)" },
    { accessorKey: "model_points", header: "Model impact", cell: (c) => {
        const v = c.getValue() as number | null;
        return v == null ? "—" : <span title={`P(out) ${pct(c.row.original.prob_out)} × depth weight ${c.row.original.depth_weight}`}>−{v.toFixed(1)} pts</span>;
      } },
    { accessorKey: "last_updated", header: "Updated", cell: (c) => <span title={c.getValue() as string}>{ago(c.getValue() as string)}</span> },
    { accessorKey: "source", header: "Source", meta: { align: "left" }, enableSorting: false, cell: (c) => c.row.original.source_url
        ? <a href={c.row.original.source_url} rel="noopener noreferrer" target="_blank">{c.getValue() as string}</a> : (c.getValue() as string) },
  ], []);
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [inj, proj, adm] = s.values;
  const a = adm.data.injury_assumptions;
  const statusText = Object.entries(a.status_prob_out).filter(([, v]) => v > 0).map(([k, v]) => `${k} ${pct(v)}`).join(", ");
  const depthText = Object.entries(a.depth_weight).map(([k, v]) => `${k === "unlisted" ? "not on the depth chart" : k === "1" ? "starter" : `string ${k}`} ${v}`).join(", ");
  const rows = inj.data;
  const teams = ["All", ...new Set(rows.map((r) => r.team))];
  const shown = team === "All" ? rows : rows.filter((r) => r.team === team);
  const next = proj.data.games.find((g) => !g.completed);
  const nextAdj = next?.adjustments.find((a) => a.key === "injuries");
  const sum = (t: string) => rows.filter((r) => r.team === t).reduce((x, r) => x + (r.model_points ?? 0), 0);

  return (
    <>
      <PageHeader title="Injuries" subtitle="Manually entered injury reports with sources, and how much the model adjusts for them." />
      {rows.length === 0 ? (
        <Card>
          <Empty title="No injuries entered">
            Injury reports aren't available from the stats API, so they're entered by hand in <code>data/manual/injuries.csv</code> or
            a linked Google Sheet. Until rows are added, the model's injury adjustment is 0 and nothing is shown here.
            Step-by-step instructions are in <code>data/manual/README.md</code> in the project repository.
          </Empty>
        </Card>
      ) : (
        <>
          {next && (
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatTile label="Tennessee listed" value={rows.filter((r) => r.team === "Tennessee" && r.status !== "available").length} />
              <StatTile label="Tennessee model impact" value={`−${sum("Tennessee").toFixed(1)} pts`} />
              <StatTile label={`${next.opponent} model impact`} value={`−${sum(next.opponent).toFixed(1)} pts`} />
              <StatTile accent label={`Net for ${siteWord(next.site)} ${next.opponent}`} value={`${(nextAdj?.points ?? 0) >= 0 ? "+" : ""}${(nextAdj?.points ?? 0).toFixed(1)} pts`}
                sub={`Week ${next.week}, ${dateLabel(next.start_date)}`} />
            </div>
          )}
          <Card>
            <div className="mb-3 w-56"><Select label="Team" value={team} onChange={setTeam} options={teams.map((t) => ({ value: t, label: t === "All" ? "All teams" : t }))} /></div>
            <DataTable data={shown} columns={columns} caption="Injury report" filterPlaceholder="Filter by player or position…"
              initialSort={[{ id: "status", desc: false }]} />
            <SourceNote meta={inj.meta} />
          </Card>
        </>
      )}
      <Card className="mt-4" title="How injuries move the projection">
        <p className="text-sm text-ink-2">Expected points lost = impact rating × {a.points_per_impact} pts × chance of missing the game
          ({statusText}) × depth-chart weight ({depthText}). A 5/5 starter who is out ≈ {(5 * a.points_per_impact).toFixed(1)} points. This rule is an <strong>assumption</strong>, not fit from
          data, because public injury histories aren't available. Adjust it per game with the injury sliders on the Matchup page.</p>
      </Card>
    </>
  );
}
