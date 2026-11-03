import { useEffect, useState } from "react";

/** Provenance block written by pipeline/publish.py on every dataset. */
export interface Meta {
  dataset: string;
  description: string;
  generated_at: string;
  season: number | null;
  data_as_of: string | null;
  sources: { source: string; endpoint: string; fetched_at: string | null; requests?: number }[];
  notes: string[];
  rows: number | null;
}
export interface Dataset<T> {
  meta: Meta;
  data: T;
}

type Row = Record<string, unknown>;
export type Num = number | null;

export interface ScheduleRow {
  game_id: number; season: number; week: number; season_type: string; start_date: string;
  opponent: string; opponent_conf: string | null; site: "home" | "away" | "neutral"; conference_game: boolean;
  venue: string | null; completed: boolean; points_for: Num; points_against: Num; spread: Num; total: Num;
  margin: Num; result: "W" | "L" | "T" | ""; ats: string;
}

export interface SiteMeta {
  team: string; conference: string; season: number; last_refreshed: string;
  record: { wins: number; losses: number; ties: number };
  conference_record: { wins: number; losses: number; ties: number };
}

export interface MetricDef {
  key: string; label: string; unit: string; higher_is_better: boolean; group: string;
  definition: string; neutral: boolean;
}

export interface Adjustment {
  key: string; label: string; unit: string; input: number | null; coef: number; se: number | null;
  ci95_low?: number | null; ci95_high?: number | null; significant: boolean | null; points: number;
  source: string; detail?: string; description: string;
  players?: { team: InjuryDetail[]; opponent: InjuryDetail[] };
}
export interface InjuryDetail {
  player: string; position: string; status: string; impact_rating: number; prob_out: number;
  depth_weight: number; points: number;
}
export interface Dist { mean: number; p10: number; p25: number; median: number; p75: number; p90: number }
export interface Simulation {
  n_sims: number; seed?: number; win_prob: number; team_points: Dist; opp_points: Dist; margin: Dist;
  margin_hist?: { value: number; share: number }[];
  team_points_hist?: { value: number; share: number }[];
  opp_points_hist?: { value: number; share: number }[];
  most_likely_scores?: { team: number; opp: number; share: number }[];
  p_one_score_game?: number; cover_prob_vs_market?: number;
}
export interface Factor { key: string; points: number; text: string }
export interface GameProjection {
  game_id: number; week: number; start_date: string; opponent: string; site: string; completed: boolean;
  actual: { team: number; opp: number; margin: number } | null;
  baseline: { margin: number; total: number; win_prob: number };
  adjustments: Adjustment[]; total_adjustments: Adjustment[];
  projection: { margin: number; total: number; team_points: number; opp_points: number; win_prob: number;
                margin_p10: number; margin_p90: number };
  simulation: Simulation;
  market: { spread: Num; total: Num };
  factors: Factor[];
  split_edges: { key: string; edge_epa: number; points_approx: number; text: string }[];
  keys_to_game: string[];
  weather: { kind: string; temp_f?: number; wind_mph?: number; precip_mm?: number } | null;
  inputs: Record<string, number | string>;
}
export interface Projections {
  games: GameProjection[];
  model: { sigma_margin: number; sigma_total: number; rho: number; n_sims: number;
           margin_coef: Record<string, number>; totals_coef: Record<string, number>; points_per_impact: number };
}

const cache = new Map<string, Promise<Dataset<unknown>>>();

export function dataUrl(name: string, ext: "json" | "csv" = "json"): string {
  const base = import.meta.env.BASE_URL;
  return ext === "json" ? `${base}data/${name}.json` : `${base}data/csv/${name}.csv`;
}

export function loadDataset<T>(name: string): Promise<Dataset<T>> {
  if (!cache.has(name)) {
    const p = fetch(dataUrl(name)).then(async (r) => {
      if (!r.ok) throw new Error(`${name}.json: HTTP ${r.status}`);
      return (await r.json()) as Dataset<unknown>;
    });
    p.catch(() => cache.delete(name)); // allow a retry after a failure
    cache.set(name, p);
  }
  return cache.get(name)! as Promise<Dataset<T>>;
}

export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; meta: Meta; data: T };

export function useDataset<T = Row[]>(name: string): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    loadDataset<T>(name).then(
      (d) => alive && setState({ status: "ready", meta: d.meta, data: d.data }),
      (e: Error) => alive && setState({ status: "error", error: e.message }),
    );
    return () => { alive = false; };
  }, [name]);
  return state;
}

/** Combine several datasets: ready only when all are ready. */
export function all<T extends unknown[]>(...states: { [K in keyof T]: LoadState<T[K]> }):
  { status: "loading" } | { status: "error"; error: string } | { status: "ready"; values: { [K in keyof T]: { meta: Meta; data: T[K] } } } {
  const err = states.find((s) => s.status === "error") as { error: string } | undefined;
  if (err) return { status: "error", error: err.error };
  if (states.some((s) => s.status === "loading")) return { status: "loading" };
  return { status: "ready", values: states.map((s) => ({ meta: (s as { meta: Meta }).meta, data: (s as { data: unknown }).data })) as never };
}

export const DATASETS: { name: string; label: string; json?: boolean; csv?: boolean }[] = [
  { name: "schedule", label: "Schedule & results" },
  { name: "results_history", label: "Results history (2019+)" },
  { name: "team_season_stats", label: "Team season stats (all FBS)" },
  { name: "team_game_stats", label: "Team per-game stats (all FBS)" },
  { name: "team_profiles", label: "Tennessee + opponents: stats & tendencies with ranks" },
  { name: "ratings", label: "Ratings (ours + SP+, Elo, FPI)" },
  { name: "rating_trend", label: "Rating trend" },
  { name: "tendency_summary", label: "Tendency summary (all FBS)" },
  { name: "tendency_splits", label: "Tendency splits" },
  { name: "situational_splits", label: "Situational splits" },
  { name: "fourth_downs", label: "4th-down decisions" },
  { name: "proe_by_game", label: "Pass rate over expected by game" },
  { name: "player_season_stats", label: "Player season stats" },
  { name: "player_usage", label: "Player usage" },
  { name: "player_game_logs", label: "Player game logs" },
  { name: "roster", label: "Roster" },
  { name: "depth_chart", label: "Depth chart (manual)" },
  { name: "depth_chart_estimated", label: "Depth chart (estimated from box scores)" },
  { name: "absence_alerts", label: "Absence alerts (box-score based)" },
  { name: "injuries", label: "Injuries (manual)" },
  { name: "schemes", label: "Scheme notes (manual)" },
  { name: "opponent_scouting", label: "Opponent scouting (manual)" },
  { name: "predictions", label: "Baseline predictions" },
  { name: "projections_table", label: "Projections" },
  { name: "season_win_distribution", label: "Season win distribution", json: false },
  { name: "backtest_games", label: "Backtest (every game)" },
];
