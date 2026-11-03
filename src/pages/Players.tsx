import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Card, ErrorState, Loading, PageHeader, Select, SourceNote } from "../components/ui";
import { all, useDataset } from "../lib/data";
import { fmt } from "../lib/format";

export type PRow = Record<string, unknown> & { player_id: string; player: string; position: string; team: string };

export const CATEGORIES: Record<string, { label: string; cols: [string, string, string?][]; sort: string }> = {
  passing: { label: "Passing", sort: "passing_yds", cols: [["passing_completions", "Cmp"], ["passing_att", "Att"],
    ["passing_pct", "Cmp%", "%"], ["passing_yds", "Yds"], ["passing_ypa", "Y/A"], ["passing_td", "TD"], ["passing_int", "INT"]] },
  rushing: { label: "Rushing", sort: "rushing_yds", cols: [["rushing_car", "Car"], ["rushing_yds", "Yds"], ["rushing_ypc", "Y/C"],
    ["rushing_td", "TD"], ["rushing_long", "Long"], ["usage_rush", "Rush usage", "%"]] },
  receiving: { label: "Receiving", sort: "receiving_yds", cols: [["receiving_rec", "Rec"], ["receiving_yds", "Yds"],
    ["receiving_ypr", "Y/R"], ["receiving_td", "TD"], ["receiving_long", "Long"], ["usage_pass", "Pass usage", "%"]] },
  defense: { label: "Defense", sort: "defensive_tot", cols: [["defensive_tot", "Tkl"], ["defensive_solo", "Solo"],
    ["defensive_tfl", "TFL"], ["defensive_sacks", "Sacks"], ["defensive_qb_hur", "QB hur"], ["defensive_pd", "PBU"],
    ["interceptions_int", "INT"]] },
  kicking: { label: "Kicking & punting", sort: "kicking_pts", cols: [["kicking_fgm", "FGM"], ["kicking_fga", "FGA"],
    ["kicking_long", "Long"], ["kicking_xpm", "XPM"], ["kicking_pts", "Pts"], ["punting_no", "Punts"], ["punting_ypp", "Y/P"]] },
};

export default function Players() {
  const s = all<[PRow[], PRow[]]>(useDataset<PRow[]>("player_season_stats"), useDataset<PRow[]>("player_usage"));
  const [team, setTeam] = useState("Tennessee");
  const [cat, setCat] = useState("passing");
  const rows = useMemo(() => {
    if (s.status !== "ready") return [];
    const [stats, usage] = s.values;
    const u = new Map(usage.data.map((r) => [r.player_id, r]));
    return stats.data.map((r) => ({ ...u.get(r.player_id), ...r }));
  }, [s]);
  const c = CATEGORIES[cat];
  const columns = useMemo<ColumnDef<PRow, unknown>[]>(() => [
    { accessorKey: "player", header: "Player", meta: { align: "left" },
      cell: (x) => x.row.original.team === "Tennessee"
        ? <Link to={`/players/${x.row.original.player_id}`}>{x.getValue() as string}</Link> : (x.getValue() as string) },
    { accessorKey: "position", header: "Pos", meta: { align: "left" } },
    ...(team === "All" ? [{ accessorKey: "team", header: "Team", meta: { align: "left", hideSm: true } } as ColumnDef<PRow, unknown>] : []),
    ...c.cols.map<ColumnDef<PRow, unknown>>(([k, label, unit]) => ({
      id: k, header: label, accessorFn: (r) => (r[k] ?? undefined) as number | undefined, sortUndefined: "last",
      cell: (x) => (unit === "%" ? fmt(x.getValue(), "%") : fmt(x.getValue(), "", Number.isInteger(x.getValue()) ? 0 : 1)),
    })),
  ], [c, team]);
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const teams = ["Tennessee", ...[...new Set(rows.map((r) => r.team))].filter((t) => t !== "Tennessee").sort(), "All"];
  const lead = c.cols[0][0];
  const data = rows.filter((r) => (team === "All" || r.team === team) && r[lead] != null);
  return (
    <>
      <PageHeader title="Players" subtitle="Season stats for Tennessee and every 2026 opponent. Tennessee players link to game logs." />
      <Card>
        <div className="mb-3 flex flex-wrap gap-3">
          <div className="w-56"><Select label="Team" value={team} onChange={setTeam} options={teams.map((t) => ({ value: t, label: t === "All" ? "All teams" : t }))} /></div>
          <div className="w-48"><Select label="Category" value={cat} onChange={setCat} options={Object.entries(CATEGORIES).map(([v, x]) => ({ value: v, label: x.label }))} /></div>
        </div>
        <DataTable key={cat + team} data={data} columns={columns} filterPlaceholder="Filter by name or position…"
          initialSort={[{ id: c.sort, desc: true }]} caption={`${c.label} stats`} />
        <SourceNote meta={s.values[0].meta} extra="Usage = share of the team's plays involving the player (CFBD). Snap counts are not publicly available." />
      </Card>
    </>
  );
}
