import { Fragment } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, Empty, ErrorState, Loading, PageHeader, SimpleTable, SourceNote, StatTile } from "../components/ui";
import { all, useDataset } from "../lib/data";
import { fmt, pct } from "../lib/format";
import { CATEGORIES, type PRow } from "./Players";

const LOG_COLS: [string, string][] = [["passing_comp", "Cmp"], ["passing_att", "Att"], ["passing_yds", "Pass yds"], ["passing_td", "Pass TD"],
  ["passing_int", "INT"], ["rushing_car", "Car"], ["rushing_yds", "Rush yds"], ["rushing_td", "Rush TD"], ["receiving_rec", "Rec"],
  ["receiving_yds", "Rec yds"], ["receiving_td", "Rec TD"], ["defensive_tot", "Tkl"], ["defensive_tfl", "TFL"],
  ["defensive_sacks", "Sacks"], ["defensive_pd", "PBU"], ["interceptions_int", "Def INT"], ["kicking_fg_made", "FGM"], ["kicking_fg_att", "FGA"]];

export default function PlayerDetail() {
  const { playerId } = useParams();
  const s = all<[PRow[], PRow[], PRow[], PRow[]]>(useDataset<PRow[]>("player_season_stats"), useDataset<PRow[]>("player_game_logs"),
    useDataset<PRow[]>("player_usage"), useDataset<PRow[]>("roster"));
  if (s.status === "loading") return <Loading />;
  if (s.status === "error") return <ErrorState error={s.error} />;
  const [stats, logs, usage, roster] = s.values;
  const season = stats.data.find((r) => r.player_id === playerId);
  const bio = roster.data.find((r) => r.player_id === playerId);
  const u = usage.data.find((r) => r.player_id === playerId);
  const games = logs.data.filter((r) => r.player_id === playerId).sort((a, b) => (a.week as number) - (b.week as number));
  const name = season?.player ?? bio?.player ?? (games[0]?.player as string | undefined);
  if (!name) return <Empty title="Player not found"><Link to="/players">Back to players</Link></Empty>;
  const cols = LOG_COLS.filter(([k]) => games.some((g) => g[k] != null));
  const h = bio?.height_in as number | undefined;
  return (
    <>
      <PageHeader title={name} subtitle={[bio?.position ?? season?.position, bio?.jersey != null ? `#${bio.jersey}` : null,
        bio?.class_year ? `Year ${bio.class_year}` : null, h ? `${Math.floor(h / 12)}'${h % 12}"` : null,
        bio?.weight_lb ? `${bio.weight_lb} lb` : null, bio?.hometown || null].filter(Boolean).join(" · ")}>
        <Link to="/players">← All players</Link>
      </PageHeader>
      {u && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Usage (all plays)" value={pct(u.usage_overall as number, 1)} />
          <StatTile label="Pass usage" value={pct(u.usage_pass as number, 1)} />
          <StatTile label="Rush usage" value={pct(u.usage_rush as number, 1)} />
          <StatTile label="3rd-down usage" value={pct(u.usage_third_down as number, 1)} />
        </div>
      )}
      <div className="grid gap-4">
        {season && (
          <Card title="Season totals">
            <div className="flex flex-wrap gap-6">
              {Object.values(CATEGORIES).map((c) => {
                const present = c.cols.filter(([k]) => season[k] != null && !k.startsWith("usage"));
                if (!present.length) return null;
                return (
                  <div key={c.label}>
                    <div className="text-xs font-semibold uppercase text-ink-3">{c.label}</div>
                    <dl className="mt-1 grid grid-cols-[auto_auto] gap-x-3 text-sm">
                      {present.map(([k, l]) => <Fragment key={k}><dt className="text-ink-2">{l}</dt><dd className="tabular text-right">{k.endsWith("pct") ? fmt(season[k], "%") : fmt(season[k], "", k.endsWith("ypa") || k.endsWith("ypc") || k.endsWith("ypr") ? 1 : 0)}</dd></Fragment>)}
                    </dl>
                  </div>);
              })}
            </div>
            <SourceNote meta={stats.meta} />
          </Card>
        )}
        <Card title="Game log">
          {games.length ? (
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Scrollable table">
              <SimpleTable head={["Wk", "Opponent", ...cols.map(([, l]) => l)]}
                rows={games.map((g) => [g.week as number, g.opponent as string, ...cols.map(([k]) => fmt(g[k], "", 0))])} />
            </div>
          ) : <Empty title="No game log">Game logs are available for Tennessee players only.</Empty>}
          <SourceNote meta={logs.meta} />
        </Card>
      </div>
    </>
  );
}
