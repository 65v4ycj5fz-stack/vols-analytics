import { Link } from "react-router-dom";
import { C } from "../components/chartColors";
import { LineSeriesChart } from "../components/lazyCharts";
import { Card, ChartFrame, Empty, ErrorState, Loading, PageHeader, Pill, SimpleTable, SourceNote, StatTile } from "../components/ui";
import { all, useDataset, type GameProjection, type Projections, type ScheduleRow, type SiteMeta } from "../lib/data";
import { dateLabel, pct, signed, siteWord, spreadLabel } from "../lib/format";

interface TrendRow { game_id: number; week: number; opponent: string; elo: number; adj_net_epa: number }
interface Outlook { expected_wins: number; p_at_least: Record<string, number>; n_sims: number;
  conference?: { p_top2_finish: number; expected_conf_wins: number } }

export default function Dashboard() {
  const alertsDs = useDataset<{ player: string; position: string | null; games_with_stats: number; team_games: number }[]>("absence_alerts");
  const s = all<[SiteMeta, Projections, ScheduleRow[], TrendRow[], Outlook]>(
    useDataset<SiteMeta>("meta"), useDataset<Projections>("projections"), useDataset<ScheduleRow[]>("schedule"),
    useDataset<TrendRow[]>("rating_trend"), useDataset<Outlook>("season_outlook"));
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [meta, proj, sched, trend, outlook] = s.values;
  const alerts = alertsDs.status === "ready" ? alertsDs.data : [];
  const m = meta.data;
  const next = proj.data.games.find((g) => !g.completed);
  const last5 = sched.data.filter((g) => g.completed).slice(-5).reverse();
  const injuries = next?.adjustments.find((a) => a.key === "injuries");
  const injuredPlayers = [...(injuries?.players?.team ?? []), ...(injuries?.players?.opponent ?? [])];

  return (
    <>
      <PageHeader title={`${m.team} ${m.season}`}
        subtitle={<>Season analytics and model projections. Record {m.record.wins}-{m.record.losses}
          {" "}({m.conference_record.wins}-{m.conference_record.losses} {m.conference}).</>} />

      <div className="grid gap-4 lg:grid-cols-3">
        {next ? <NextGame g={next} sigma={proj.data.model.sigma_margin} /> :
          <Card title="Next game" className="lg:col-span-2"><Empty title="No upcoming games">The season is complete.</Empty></Card>}

        <Card title="Season outlook" subtitle={`${outlook.data.n_sims.toLocaleString()} simulated seasons`}>
          <div className="grid grid-cols-2 gap-3">
            <StatTile label="Record" value={`${m.record.wins}-${m.record.losses}`} sub={`${m.conference_record.wins}-${m.conference_record.losses} ${m.conference}`} />
            <StatTile label="Projected wins" value={outlook.data.expected_wins.toFixed(1)} sub="regular season, mean" />
            <StatTile label="P(9+ wins)" value={pct(outlook.data.p_at_least["9"])} />
            <StatTile label={`P(top-2 ${m.conference})`} value={pct(outlook.data.conference?.p_top2_finish)} sub="title-game spot (approx.)" />
          </div>
          <Link to="/schedule" className="mt-3 inline-block text-sm">Full schedule & win distribution →</Link>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ChartFrame title="Rating trend" subtitle="Our Elo rating after each game (higher = stronger)" meta={trend.meta}
            table={<SimpleTable rows={trend.data.map((t) => [`Wk ${t.week} ${t.opponent}`, t.elo.toFixed(0), signed(t.adj_net_epa, 3)])}
              head={["Game", "Elo", "Adj. net EPA/play"]} />}>
            <LineSeriesChart data={trend.data} x="week" xLabel="Week" yLabel="Elo"
              series={[{ key: "elo", color: C.team, label: "Elo" }]}
              tip={(r) => ({ title: `Week ${r.week} · ${r.opponent}`, rows: [["Elo after game", r.elo.toFixed(0)],
                ["Adj. net EPA/play", signed(r.adj_net_epa, 3)]] })} />
          </ChartFrame>
        </div>
        <Card title="Last 5 results">
          <ul className="divide-y divide-line">
            {last5.map((g) => (
              <li key={g.game_id} className="flex items-center justify-between py-2 text-sm">
                <span><Pill tone={g.result === "W" ? "good" : "bad"}>{g.result}</Pill>{" "}
                  <span className="text-ink-3">{siteWord(g.site)}</span> {g.opponent}</span>
                <span className="tabular font-medium">{g.points_for}-{g.points_against}</span>
              </li>
            ))}
          </ul>
          <SourceNote meta={sched.meta} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Injury alerts" subtitle={next ? `Listed for the ${next.opponent} game` : undefined}>
          {injuredPlayers.length ? (
            <ul className="text-sm">{injuredPlayers.map((p) => (
              <li key={p.player} className="flex justify-between py-1"><span>{p.player} ({p.position})</span>
                <span>{p.status} · −{p.points.toFixed(1)} pts</span></li>))}</ul>
          ) : (
            <Empty title="No injuries entered">
              Injuries are entered manually (see the <Link to="/injuries">Injuries</Link> page). The model's injury
              adjustment is 0 until rows are added.
            </Empty>
          )}
          {alerts.length > 0 && (
            <div className="mt-3 text-sm">
              <div className="text-xs font-semibold uppercase text-ink-3">Missing from the latest box score (not an injury report)</div>
              <ul className="mt-1">{alerts.map((a) => <li key={a.player}>{a.player} {a.position && <span className="text-ink-3">{a.position}</span>}
                <span className="text-xs text-ink-3"> · stats in {a.games_with_stats} of {a.team_games} earlier games</span></li>)}</ul>
            </div>
          )}
        </Card>
        <Card title="Matchup edges" subtitle={next ? `vs ${next.opponent}: season-to-date, opponent-adjusted` : undefined}>
          {next?.split_edges.length ? (
            <ul className="space-y-1.5 text-sm">{next.split_edges.map((e) => (
              <li key={e.key} className={`rounded-md px-2 py-1 ${e.edge_epa > 0 ? "bg-edge-good" : "bg-edge-bad"}`}>
                <span aria-hidden>{e.edge_epa > 0 ? "▲ " : "▼ "}</span>{e.text.replace(" (descriptive; part of the EPA factors)", "")}
              </li>))}</ul>
          ) : <Empty title="No matchup data" />}
          {next && <Link to={`/matchup/${next.game_id}`} className="mt-2 inline-block text-sm">Open matchup →</Link>}
        </Card>
      </div>
    </>
  );
}

function NextGame({ g, sigma }: { g: GameProjection; sigma: number }) {
  const p = g.projection;
  const top = g.factors.slice(0, 3);
  return (
    <Card className="lg:col-span-2" title={<>Next game: <span className="text-ink-2">{siteWord(g.site)}</span> {g.opponent}</>}
      subtitle={`Week ${g.week} · ${dateLabel(g.start_date, true)}`}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile accent label="Projected score" value={`${Math.round(p.team_points)}-${Math.round(p.opp_points)}`}
          sub={`Tennessee ${signed(p.margin)}`} />
        <StatTile accent label="Win probability" value={pct(p.win_prob)} sub={`10k sims: ${pct(g.simulation.win_prob)}`} />
        <StatTile label="80% margin range" value={`${signed(p.margin_p10, 0)} to ${signed(p.margin_p90, 0)}`}
          sub={`error SD ${sigma.toFixed(1)} pts`} />
        <StatTile label="Closing spread" value={spreadLabel(g.market.spread)} sub="for comparison only" />
      </div>
      <h3 className="mt-4 text-sm font-semibold">What drives the projection</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {top.map((f) => <li key={f.key} className="flex gap-2"><span className="tabular w-16 shrink-0 font-semibold">
          <span aria-hidden>{f.points >= 0 ? "▲ " : "▼ "}</span>{signed(f.points)}</span><span>{f.text.split(":")[0]}</span></li>)}
      </ul>
      <Link to={`/matchup/${g.game_id}`} className="mt-3 inline-block text-sm font-medium">Full matchup, factors & sliders →</Link>
    </Card>
  );
}
