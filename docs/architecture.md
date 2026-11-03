# Architecture

```
            ┌──────────────── GitHub Actions (daily in season / weekly / on push) ────────────────┐
            │                                                                                      │
 CFBD API ──┤  pipeline/  ─── cached responses (data/cache, gzip; restored between runs) ───┐      │
 Open-Meteo ┤    sources/*      validate (pydantic)  →  transforms/*  →  data/processed/*.parquet  │
 data/manual┤    manual.py      validate manual CSVs / Google Sheets (fails the build if bad)     │
 (or Sheets)│                    │                                                               │
            │  model/            ▼                                                               │
            │    features → backtest (walk-forward) → adjustments → projections → simulation      │
            │                    │                                                               │
            │  publish.py  →  public/data/*.json (+ meta: sources, fetch times, notes) + csv/*.csv  │
            │                    │                                                               │
            │  tests (pytest + vitest) → vite build → dist/ (static) → GitHub Pages               │
            └──────────────────────────────────────────────────────────────────────────────────────┘
                                 │
                 Browser: React app fetches public/data/*.json (never the APIs; no keys in the site)
```

## Principles

- **The browser never calls an API.** Keys stay in the pipeline (`.env` locally, a repository secret in CI).
  The workflow checks that the key doesn't appear anywhere in `dist/`.
- **Every number has provenance.** Each JSON file is `{meta, data}`. `meta.sources` lists the endpoint
  and fetch time of each input, and `meta.data_as_of` is the oldest input. The UI shows these in source
  notes and the ⓘ popovers.
- **No fabricated data.** Missing inputs stay null and render as "—" or an empty state. Manual data must
  cite a source. Model outputs carry intervals, sample sizes or fit diagnostics.
- **Cheap refreshes.** Responses for finished seasons and weeks are cached forever, and the current season
  refreshes after 20 h. Each run has a call budget (`CFBD_MAX_CALLS`) that stops a runaway job before it
  drains the 1,000-call monthly quota.
- **No lookahead.** Every model feature uses only games that kicked off earlier, and a test enforces this
  by scrambling future results.

## Pipeline steps (`python -m pipeline.run`)

1. Validate manual data (`pipeline/manual.py`). Stop with row/column messages if anything is wrong.
2. For 2019 → current season: games, closing lines, per-game advanced stats (EPA, success, explosiveness).
3. Context: venues → travel distance, rest days, box-score turnovers (last 3 seasons), weather (Open-Meteo).
4. Current season: team season stats, advanced season stats, weekly box scores, SP+/Elo/FPI, AP poll.
5. Play-by-play for every completed week → classified plays (local parquet only) → tendency tables and the
   pass-rate and 4th-down situation models.
6. Players: season stats, usage, Tennessee game logs, roster.
7. Publish validated manual data with model injury impact.

## Model steps (`python -m model.run`)

Walk-forward backtest (settings chosen per season from earlier seasons) → totals model + fitted
adjustments → live projections for Tennessee's games → 10,000-game and 10,000-season simulations →
republish Elo with the selected settings. See [model.md](model.md).

## Frontend (`src/`)

Vite + React 19 + TypeScript, Tailwind v4 (semantic color tokens with light and dark sets), Recharts
(lazy-loaded so text renders first), TanStack Table v8. Hash routing (`/#/matchup`) works on any static
host. Each page is its own code chunk. `src/lib/model.ts` mirrors the Python simulation so the Matchup
sliders recompute in the browser.

## Tests

- `pipeline/tests`, `model/tests` (pytest): cache and budget, schemas, transforms, play classifier,
  situation models, Elo/ridge recovery on synthetic data, no-lookahead, adjustments, simulation, manual
  validator, plus an offline end-to-end rebuild from the cache.
- `src/**/*.test.ts` (vitest): browser-side simulation and formatting.
- CI also runs `tsc`, the production build, the secret scan and a Lighthouse audit.
