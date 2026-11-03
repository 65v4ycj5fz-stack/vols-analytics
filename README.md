# Vols Analytics

An unofficial, shareable analytics site for Tennessee Volunteers football: season stats, play-by-play
tendencies, depth chart, injuries and model projections, with uncertainty shown everywhere. It runs as a
free static site on GitHub Pages and refreshes itself daily in season. Every table also downloads as
CSV for Google Sheets.

- **Data:** [CollegeFootballData.com](https://collegefootballdata.com) (free API key) and
  [Open-Meteo](https://open-meteo.com) weather (no key). Injuries, depth chart and scheme notes are
  entered by hand, each row with a source. Nothing is invented; missing data shows as an empty state.
- **Model:** opponent-adjusted ratings → margin → win probability → score → simulation, checked with a
  walk-forward backtest. The model does **not** beat the betting market, and the site says so. See
  [docs/model.md](docs/model.md).
- **No wagering features.** Closing spreads appear only to measure accuracy.

## Set up and run locally (5 steps)

You need Python 3.11+ (3.14 tested), Node 22+ and `make`.

1. `git clone <this repo> && cd vols-analytics`
2. `cp .env.example .env` and paste your free key from <https://collegefootballdata.com/key> after `CFBD_API_KEY=`
3. `make setup` (Python virtualenv + npm packages)
4. `make data` (fetches and caches data, then runs the model; the first run takes ~20 min, mostly the one-time weather history)
5. `make dev` and open <http://localhost:5173>

Other commands: `make test` (all tests), `make build` (static site in `dist/`), `make data-offline`
(rebuild from cache with no API calls), `make validate` (check the manual CSVs), `make docs`
(regenerate the data dictionary).

**API budget:** the free CFBD tier is 1,000 calls/month, shared by your computer and the GitHub workflow.
Responses are cached in `data/cache/`: finished weeks and seasons are never re-fetched, and current-season
data refreshes after 20 hours. A daily refresh uses about 15 calls, and a cold start about 110.

## Deploy to GitHub Pages (free, 4 steps)

1. Create a repository on GitHub and push this folder to its `main` branch.
2. **Settings → Secrets and variables → Actions → New repository secret:** name `CFBD_API_KEY`, value = your key.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. **Actions → Refresh data & deploy → Run workflow.** When it finishes, the site is at
   `https://<your-username>.github.io/<repo-name>/` (the link is also shown on the workflow run).

After that, [.github/workflows/refresh-deploy.yml](.github/workflows/refresh-deploy.yml) runs by itself:
daily August–January, Mondays the rest of the year, and on every push to `main` (for example after you
edit an injury). Each run checks the manual data, refreshes, runs the model and all tests, builds,
confirms the API key isn't in the output, saves a Lighthouse report, and deploys. If any check fails, the
live site keeps its last good version.

## Share with a friend

- Send the Pages link. It works on phones and laptops, in light or dark mode, with no login.
- Links go straight to pages, e.g. `…/#/matchup` or `…/#/schedule`, and each game's matchup page has its own link.
- **Unlisted mode:** add a repository *variable* (not secret) `SITE_UNLISTED` = `true` and re-run the
  workflow. Search engines are then asked not to index the site (`noindex` + `robots.txt`), so only people
  you send the link to will find it. This is **not** a password: anyone with the link can open it. GitHub Pages
  can't do real password protection. If you need that, host `dist/` behind something like Cloudflare Access
  or a paid Netlify/Vercel password feature.
- Friends who live in spreadsheets: the **Data** page has a "Copy Sheets formula" button for every table
  (see [docs/google-sheets.md](docs/google-sheets.md)).

## Updating injuries, the depth chart and scheme notes

Edit the CSVs in [`data/manual/`](data/manual/) on GitHub, or point the site at a Google Sheet. The guide for
non-programmers is [data/manual/README.md](data/manual/README.md). A bad entry stops the refresh with a
message naming the file, row and column. The live site never shows broken data.

## Project layout

| Path | What |
|---|---|
| `pipeline/` | API clients with caching, schemas, transforms, manual-data validator, publisher (`python -m pipeline.run`) |
| `model/` | Ratings, backtest, adjustments, projections, simulation (`python -m model.run`) |
| `data/manual/` | Hand-entered CSV templates + guide |
| `public/data/` | Generated JSON + `csv/` (not committed; built by `make data` / CI) |
| `src/` | React + TypeScript site |
| `docs/` | [model.md](docs/model.md), [architecture.md](docs/architecture.md), [data-dictionary.md](docs/data-dictionary.md), [google-sheets.md](docs/google-sheets.md) |

## Known limitations

**Model**
- The closing spread is more accurate than the model (smaller average miss in every season tested), and the
  model's picks went about 49% against the spread. Use projections to see *why* a game looks the way it does,
  not as an edge. The Model page recomputes these statements from the backtest on every refresh.
- Home-field advantage has drifted upward. One value is fitted on earlier seasons, so home teams have won
  slightly more often than predicted.
- There's no roster, recruiting or transfer-portal information. Early-season ratings lean on last season.
- Injury effects are an explicit assumption (impact × 0.6 pts × chance of missing × depth weight), not an
  estimate. They're also only as good as the manual entries.
- Score distributions use a normal approximation. Real scores cluster on 3s and 7s.
- The season simulation breaks SEC ties at random (real tiebreakers aren't modeled). No playoff probability
  is shown, because selection is by committee.
- Several fitted adjustments (rest, recent form, rain) aren't statistically significant. They stay small,
  are labeled, and can be switched off on the Matchup page.

**Data**
- Public play-by-play has no personnel groupings, play-action, blitz or snap-count data. Those pages show
  empty states or manual notes. "Shotgun", "no huddle" and "deep" come from play-text wording, which
  scorers record inconsistently.
- Turnover history is pulled for the last three seasons only (to save API calls). Game logs are Tennessee-only.
- CFBD's 2026 roster lists every player as the same class year, so class is left blank.
- Kickoffs marked TBD get no weather forecast, and forecasts only exist about two weeks out.
- Depth chart, injuries and scheme notes are empty until someone enters them.

**Site & operations**
- The free CFBD tier (1,000 calls/month) is shared by local runs and the workflow. A cold start costs ~110 calls.
- The first CI run takes ~20–25 minutes (one-time weather history). If GitHub's runner IP gets
  rate-limited by Open-Meteo, weather is skipped for that run and retried next time.
- "Unlisted" mode hides the site from search engines but isn't access control.
- Lighthouse scores come from CI. Locally, accessibility was checked with axe (WCAG 2.1 AA, 11 pages, light
  and dark themes) and load size was measured, but no Lighthouse score was produced, because Chrome isn't
  installed on the build machine.

## Credits & disclaimer

Unofficial fan project, not affiliated with or endorsed by the University of Tennessee, its athletics
department or the SEC. No official logos or trademarks are used. Data from CollegeFootballData.com (CFBD).
Weather data by Open-Meteo.com (CC BY 4.0).
