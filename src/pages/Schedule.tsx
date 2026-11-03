import { Link } from "react-router-dom";
import { C } from "../components/chartColors";
import { ColumnChart } from "../components/lazyCharts";
import { Card, ChartFrame, ErrorState, Loading, PageHeader, Pill, SimpleTable, SourceNote, StatTile } from "../components/ui";
import { all, useDataset, type Projections, type ScheduleRow } from "../lib/data";
import { dateLabel, pct, signed, siteWord, spreadLabel } from "../lib/format";

interface Outlook {
  n_sims: number; tau: number; expected_wins: number; games_remaining: number;
  current_record: { wins: number; losses: number };
  win_distribution: { wins: number; prob: number }[]; p_at_least: Record<string, number>;
  conference?: { expected_conf_wins: number; p_top2_finish: number; p_first_place: number; tiebreak_note: string;
    conf_win_distribution: { wins: number; prob: number }[];
    standings_projection: { team: string; expected_conf_wins: number; p_top2: number }[] };
  current_conference_standings: { team: string; wins: number; losses: number }[];
  notes: string[];
}

export default function Schedule() {
  const s = all<[ScheduleRow[], Projections, Outlook]>(useDataset<ScheduleRow[]>("schedule"),
    useDataset<Projections>("projections"), useDataset<Outlook>("season_outlook"));
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [sched, proj, out] = s.values;
  const o = out.data;
  const byId = new Map(proj.data.games.map((g) => [g.game_id, g]));
  const expectedFromGames = sched.data.reduce((t, g) => t + (g.completed ? (g.result === "W" ? 1 : 0) : (byId.get(g.game_id)?.projection.win_prob ?? 0)), 0);

  return (
    <>
      <PageHeader title="Schedule & Projections"
        subtitle="Results so far, the model's pregame view of every game, and the simulated win total." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile accent label="Expected wins" value={o.expected_wins.toFixed(2)} sub={`sum of game win probabilities: ${expectedFromGames.toFixed(2)}`} />
        <StatTile label="Record" value={`${o.current_record.wins}-${o.current_record.losses}`} sub={`${o.games_remaining} games left`} />
        <StatTile label="P(10+ wins)" value={pct(o.p_at_least["10"], 1)} />
        <StatTile label="P(top-2 SEC)" value={pct(o.conference?.p_top2_finish, 1)} sub="SEC title-game spot, approx." />
      </div>

      <Card className="mt-4" title="Games" subtitle="Completed games show the model's pregame projection next to the result.">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable table">
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-ink-2">
              {["Wk", "Date", "Opponent", "Result", "Projection", "Win prob", "Spread", "vs spread"].map((h, i) =>
                <th key={h} scope="col" className={`px-2 py-2 ${i < 3 ? "text-left" : "text-right"} ${i === 1 || i === 7 ? "hidden sm:table-cell" : ""}`}>{h}</th>)}
            </tr></thead>
            <tbody>
              {sched.data.map((g) => {
                const p = byId.get(g.game_id);
                const wp = p?.projection.win_prob;
                return (
                  <tr key={g.game_id} className="border-t border-line">
                    <td className="tabular px-2 py-2">{g.week}</td>
                    <td className="hidden px-2 py-2 sm:table-cell">{dateLabel(g.start_date)}</td>
                    <td className="px-2 py-2"><span className="text-ink-3">{siteWord(g.site)}</span>{" "}
                      <Link to={`/matchup/${g.game_id}`}>{g.opponent}</Link>{g.conference_game && <span className="ml-1 text-xs text-ink-3">SEC</span>}</td>
                    <td className="tabular px-2 py-2 text-right">{g.completed ? <><Pill tone={g.result === "W" ? "good" : "bad"}>{g.result}</Pill> {g.points_for}-{g.points_against}</> : "—"}</td>
                    <td className="tabular px-2 py-2 text-right">{p ? `${Math.round(p.projection.team_points)}-${Math.round(p.projection.opp_points)} (${signed(p.projection.margin)})` : "—"}</td>
                    <td className="px-2 py-2 text-right">{wp != null ? <WinBar p={wp} /> : "—"}</td>
                    <td className="tabular px-2 py-2 text-right">{spreadLabel(g.spread)}</td>
                    <td className="hidden px-2 py-2 text-right sm:table-cell">{g.ats || "—"}</td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>
        <SourceNote meta={sched.meta} extra="Spread: negative = Tennessee favored (median closing line across books listed by CFBD), shown to compare against the model only." />
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Regular-season win total" subtitle={`Share of ${o.n_sims.toLocaleString()} simulated seasons ending with each win total`}
          meta={out.meta} note={o.notes.join(" ")}
          table={<SimpleTable head={["Wins", "Probability", "At least"]} rows={o.win_distribution.map((w) =>
            [w.wins, pct(w.prob, 1), pct(o.p_at_least[String(w.wins)] ?? 1, 1)])} />}>
          <ColumnChart data={o.win_distribution} x="wins" y="prob" xLabel="Regular-season wins" yLabel="Probability"
            colorFor={() => C.team} yFormat={(v) => `${Math.round(v * 100)}%`}
            tip={(w) => ({ title: `${w.wins} wins`, rows: [["Probability", pct(w.prob, 1)], ["At least this many", pct(o.p_at_least[String(w.wins)] ?? 1, 1)]] })} />
        </ChartFrame>
        {o.conference && (
          <Card title="SEC outlook" subtitle="Conference-only results; ties broken at random (approximation)">
            <div className="grid grid-cols-3 gap-3">
              <StatTile label="Exp. SEC wins" value={o.conference.expected_conf_wins.toFixed(1)} />
              <StatTile label="P(1st)" value={pct(o.conference.p_first_place, 1)} />
              <StatTile label="P(top 2)" value={pct(o.conference.p_top2_finish, 1)} />
            </div>
            <div className="mt-3 max-h-72 overflow-auto" tabIndex={0} role="region" aria-label="Projected SEC standings">
              <SimpleTable head={["Team", "Now", "Exp. SEC wins", "P(top 2)"]}
                rows={[...o.conference.standings_projection].sort((a, b) => b.p_top2 - a.p_top2).map((r) => {
                  const cur = o.current_conference_standings.find((c) => c.team === r.team);
                  return [r.team === "Tennessee" ? "▶ Tennessee" : r.team, cur ? `${cur.wins}-${cur.losses}` : "—",
                    r.expected_conf_wins.toFixed(1), pct(r.p_top2, 1)];
                })} />
            </div>
            <p className="mt-2 text-xs text-ink-3">{o.conference.tiebreak_note} No playoff probability is shown: selection is by committee.</p>
          </Card>
        )}
      </div>
    </>
  );
}

function WinBar({ p }: { p: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="relative inline-block h-2 w-16 overflow-hidden rounded-full bg-surface-2">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${p * 100}%`, background: C.team }} />
      </span>
      <span className="tabular w-10">{pct(p)}</span>
    </span>
  );
}
