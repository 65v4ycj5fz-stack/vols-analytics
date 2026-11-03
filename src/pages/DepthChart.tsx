import { useState } from "react";
import { Card, Empty, ErrorState, Loading, PageHeader, Select, SourceNote, StatusBadge } from "../components/ui";
import { all, useDataset } from "../lib/data";
import type { InjuryRow } from "./Injuries";

interface DepthRow {
  team: string; position_group: string; position: string; string: number; player: string; jersey: number | null;
  class: string | null; height: string | null; weight: number | null; snap_pct: number | null; notes: string | null;
  last_updated: string; source: string;
}
interface RosterRow { player_id: string; player: string; jersey: number | null; position: string | null; class_year: number | null }

/** Formation slots: grid position (row, col on a 11-column field) and which depth-chart positions fill it. */
interface Slot { id: string; label: string; match: string[]; row: number; col: number }
const FORMATIONS: Record<string, { title: string; rows: number; slots: Slot[] }> = {
  offense: { title: "Offense", rows: 4, slots: [
    { id: "x", label: "WR", match: ["X", "WR"], row: 1, col: 1 },
    { id: "lt", label: "LT", match: ["LT", "OT", "OL"], row: 1, col: 3 },
    { id: "lg", label: "LG", match: ["LG", "OG", "OL"], row: 1, col: 4 },
    { id: "c", label: "C", match: ["C", "OL"], row: 1, col: 5 },
    { id: "rg", label: "RG", match: ["RG", "OG", "OL"], row: 1, col: 6 },
    { id: "rt", label: "RT", match: ["RT", "OT", "OL"], row: 1, col: 7 },
    { id: "te", label: "TE", match: ["TE", "Y"], row: 1, col: 8 },
    { id: "z", label: "WR", match: ["Z", "WR"], row: 1, col: 11 },
    { id: "slot", label: "SLOT", match: ["SLOT", "H", "WR"], row: 2, col: 10 },
    { id: "qb", label: "QB", match: ["QB"], row: 3, col: 5 },
    { id: "rb", label: "RB", match: ["RB", "HB", "TB"], row: 4, col: 5 },
  ] },
  defense: { title: "Defense", rows: 4, slots: [
    { id: "cb1", label: "CB", match: ["CB"], row: 1, col: 1 },
    { id: "s1", label: "S", match: ["FS", "S"], row: 1, col: 4 },
    { id: "s2", label: "S", match: ["SS", "S"], row: 1, col: 8 },
    { id: "cb2", label: "CB", match: ["CB"], row: 1, col: 11 },
    { id: "nb", label: "NB", match: ["NB", "STAR", "NICKEL"], row: 2, col: 10 },
    { id: "lb1", label: "LB", match: ["WILL", "LB", "OLB", "ILB"], row: 3, col: 4 },
    { id: "lb2", label: "LB", match: ["MIKE", "LB", "ILB"], row: 3, col: 6 },
    { id: "lb3", label: "LB", match: ["SAM", "LB", "OLB"], row: 3, col: 8 },
    { id: "de1", label: "DE", match: ["DE", "EDGE"], row: 4, col: 3 },
    { id: "dt1", label: "DT", match: ["DT", "NT", "DL"], row: 4, col: 5 },
    { id: "dt2", label: "DT", match: ["DT", "DL"], row: 4, col: 6 },
    { id: "de2", label: "DE", match: ["DE", "EDGE"], row: 4, col: 8 },
  ] },
  "special teams": { title: "Special teams", rows: 2, slots: [
    { id: "k", label: "K", match: ["K", "PK"], row: 1, col: 2 },
    { id: "p", label: "P", match: ["P"], row: 1, col: 4 },
    { id: "ls", label: "LS", match: ["LS"], row: 1, col: 6 },
    { id: "h", label: "H", match: ["H"], row: 1, col: 8 },
    { id: "kr", label: "KR", match: ["KR"], row: 2, col: 4 },
    { id: "pr", label: "PR", match: ["PR"], row: 2, col: 8 },
  ] },
};

/** Assign players to slots: exact position names first, then generic ones (e.g. "WR") in order. */
function assign(rows: DepthRow[], slots: Slot[]): { bySlot: Map<string, DepthRow[]>; unplaced: DepthRow[] } {
  const bySlot = new Map<string, DepthRow[]>();
  const used = new Set<DepthRow>();
  const starters = rows.filter((r) => r.string === 1);
  for (const s of slots) {
    const exact = starters.find((r) => !used.has(r) && r.position === s.match[0] && s.match[0] !== s.match[s.match.length - 1]);
    const generic = starters.filter((r) => !used.has(r) && s.match.includes(r.position));
    const pick = exact ?? generic[0];
    if (pick) {
      used.add(pick);
      const backups = rows.filter((r) => r.string > 1 && !used.has(r) && r.position === pick.position)
        .sort((a, b) => a.string - b.string).slice(0, 2);
      backups.forEach((b) => used.add(b));
      bySlot.set(s.id, [pick, ...backups]);
    }
  }
  return { bySlot, unplaced: rows.filter((r) => !used.has(r)) };
}

export default function DepthChart() {
  const s = all<[DepthRow[], InjuryRow[], RosterRow[]]>(useDataset<DepthRow[]>("depth_chart"), useDataset<InjuryRow[]>("injuries"),
    useDataset<RosterRow[]>("roster"));
  const [team, setTeam] = useState("Tennessee");
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [depth, inj, roster] = s.values;
  const teams = [...new Set(["Tennessee", ...depth.data.map((r) => r.team)])];
  const rows = depth.data.filter((r) => r.team === team);
  const injury = (name: string) => inj.data.find((i) => i.team === team && i.player.toLowerCase() === name.toLowerCase() && i.status !== "available");

  return (
    <>
      <PageHeader title="Depth Chart" subtitle="Starters and backups by position (manual entry), with injury status and snap share where known.">
        {teams.length > 1 && <div className="w-48"><Select label="Team" value={team} onChange={setTeam} options={teams.map((t) => ({ value: t, label: t }))} /></div>}
      </PageHeader>
      {rows.length === 0 ? (
        <>
          <Card><Empty title={`No depth chart entered for ${team}`}>
            Depth order isn't published by the stats API, so it's entered by hand in <code>data/manual/depth_chart.csv</code> (or a linked
            Google Sheet). See <code>data/manual/README.md</code>; <code>python -m pipeline.manual seed-depth</code> pre-fills names from
            the roster. Below is the official CFBD roster grouped by position. It does <strong>not</strong> show depth order.
          </Empty></Card>
          {team === "Tennessee" && <RosterByPosition roster={roster.data} />}
        </>
      ) : (
        <div className="space-y-4">
          {Object.entries(FORMATIONS).map(([group, f]) => {
            const g = rows.filter((r) => r.position_group === group);
            if (!g.length) return <Card key={group} title={f.title}><Empty title={`No ${group} entries`} /></Card>;
            const { bySlot, unplaced } = assign(g, f.slots);
            return (
              <Card key={group} title={f.title} subtitle={`Updated ${g.map((r) => r.last_updated).sort().at(-1)} · source: ${[...new Set(g.map((r) => r.source))].join("; ")}`}>
                <div className="checker hidden rounded-lg border border-line bg-surface-2 p-3 lg:grid"
                  style={{ gridTemplateColumns: "repeat(11, minmax(0, 1fr))", gridTemplateRows: `repeat(${f.rows}, auto)`, gap: "0.5rem" }}>
                  {f.slots.map((slot) => (
                    <div key={slot.id} style={{ gridRow: slot.row, gridColumn: slot.col }} className="min-w-0">
                      <SlotCard label={slot.label} players={bySlot.get(slot.id) ?? []} injury={injury} />
                    </div>
                  ))}
                </div>
                <div className="grid gap-2 sm:grid-cols-2 lg:hidden">
                  {f.slots.filter((x) => bySlot.has(x.id)).map((slot) => (
                    <SlotCard key={slot.id} label={slot.label} players={bySlot.get(slot.id)!} injury={injury} />
                  ))}
                </div>
                {unplaced.length > 0 && (
                  <div className="mt-3 text-sm">
                    <div className="text-xs font-semibold uppercase text-ink-3">Other {group} entries</div>
                    <ul className="mt-1 flex flex-wrap gap-2">{unplaced.map((r) => (
                      <li key={r.player + r.position} className="rounded-md border border-line px-2 py-1">
                        {r.position}{r.string > 1 ? ` (${r.string})` : ""}: {r.player}
                        {injury(r.player) && <> <StatusBadge status={injury(r.player)!.status} /></>}
                      </li>))}</ul>
                  </div>
                )}
              </Card>
            );
          })}
          <SourceNote meta={depth.meta} />
        </div>
      )}
    </>
  );
}

function SlotCard({ label, players, injury }: { label: string; players: DepthRow[]; injury: (n: string) => InjuryRow | undefined }) {
  if (!players.length) {
    return <div className="rounded-md border border-dashed border-line bg-surface px-2 py-1.5 text-center text-xs text-ink-3">{label}<br />—</div>;
  }
  const [starter, ...backups] = players;
  const inj = injury(starter.player);
  return (
    <div className="rounded-md border border-line bg-surface px-2 py-1.5 text-xs shadow-sm">
      <div className="font-bold text-brand-ink">{starter.position}</div>
      <div className="text-sm font-semibold leading-tight [overflow-wrap:anywhere]">
        {starter.jersey != null && <span className="text-ink-3">#{starter.jersey} </span>}{starter.player}
      </div>
      {starter.snap_pct != null && <div className="text-ink-3">{starter.snap_pct.toFixed(0)}% of snaps</div>}
      {inj && <div className="mt-0.5"><StatusBadge status={inj.status} /></div>}
      {backups.map((b) => {
        const bi = injury(b.player);
        return <div key={b.player} className="text-ink-2 [overflow-wrap:anywhere]">{b.string}. {b.player}{bi && ` (${bi.status})`}</div>;
      })}
    </div>
  );
}

function RosterByPosition({ roster }: { roster: RosterRow[] }) {
  const groups = new Map<string, RosterRow[]>();
  for (const r of roster) groups.set(r.position ?? "?", [...(groups.get(r.position ?? "?") ?? []), r]);
  const years = ["", "FR", "SO", "JR", "SR", "GR"];
  return (
    <Card className="mt-4" title="Roster by position (CFBD)" subtitle={`${roster.length} players · not a depth chart`}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[...groups.entries()].sort().map(([pos, list]) => (
          <div key={pos}>
            <div className="text-xs font-semibold uppercase text-ink-3">{pos} ({list.length})</div>
            <ul className="mt-1 text-sm">{list.sort((a, b) => (a.jersey ?? 99) - (b.jersey ?? 99)).map((r) => (
              <li key={r.player_id}><span className="tabular text-ink-3">#{r.jersey ?? "—"}</span> {r.player}
                {r.class_year ? <span className="text-xs text-ink-3"> {years[r.class_year] ?? ""}</span> : null}</li>))}</ul>
          </div>
        ))}
      </div>
    </Card>
  );
}
