# Updating injuries, the depth chart and scheme notes (no coding needed)

The site gets stats automatically, but four things are typed in by people:

| File | What it holds | Shows up on |
|---|---|---|
| `injuries.csv` | Who's hurt, their status, and how much it matters | Injuries page, Dashboard alerts, Matchup projections |
| `depth_chart.csv` | Starters and backups at each position | Depth Chart page; also weights injuries (a starter matters more than a backup) |
| `schemes.csv` | Tennessee's offensive/defensive/special-teams schemes | Schemes & Tendencies page |
| `opponent_scouting.csv` | The same scheme notes for opponents | Schemes & Tendencies page |

**Every row needs a `source`** (a link or "team release", "beat writer X", "own film notes", ...)
and a `last_updated` date. The site shows both next to the data. Never enter something you can't source.

You can edit the files on GitHub (Option A) or in a Google Sheet (Option B). Either way, the
next refresh checks your entries. If something is wrong, the refresh stops and tells you
the file, row number and column to fix. Nothing broken ever reaches the site.

---

## Option A: edit on GitHub (simplest)

1. Open the repository on github.com, go to `data/manual/`, and click the file (for example `injuries.csv`).
2. Click the ✏️ pencil icon ("Edit this file").
3. Add one line per row, with commas between columns, in the same order as the first (header) line.
   Leave a column empty by typing nothing between two commas. If a value contains a comma, put it in
   double quotes: `"Spread, RPO-heavy"`.
4. Click **Commit changes…**, write a short note (e.g. "Week 10 injuries"), and commit.
5. The site rebuilds automatically within a few minutes. You can also start it by hand: **Actions** tab →
   **Refresh data & deploy** → **Run workflow**.
6. If the refresh fails, open it in the **Actions** tab. The red step lists exactly what to fix, like:
   ```
   injuries.csv: 1 problem(s) found
     row 4, column 'status': 'maybe' is not allowed. Use one of: 'out', 'doubtful', 'questionable', 'probable' or 'available'
   ```
   "Row 4" means the 4th line of the file, counting the header as line 1, the same numbering a spreadsheet uses.

## Option B: keep the data in a Google Sheet

1. Create a Google Sheet with four tabs: `injuries`, `depth_chart`, `schemes`, `opponent_scouting`.
2. In each tab, paste the header line from the matching file in this folder into row 1 (one column per cell).
   Use **Data → Split text to columns** if it lands in one cell.
3. **File → Share → Publish to web.** Pick the tab, choose **Comma-separated values (.csv)**, click **Publish**, and copy the link.
   Repeat for each tab. Each tab gets its own link.
4. In the GitHub repository: **Settings → Secrets and variables → Actions → Variables → New repository variable**:

   | Variable name | Value |
   |---|---|
   | `SHEET_INJURIES_URL` | the injuries tab's CSV link |
   | `SHEET_DEPTH_CHART_URL` | the depth_chart tab's CSV link |
   | `SHEET_SCHEMES_URL` | the schemes tab's CSV link |
   | `SHEET_OPPONENT_SCOUTING_URL` | the opponent_scouting tab's CSV link |

5. Done. Every refresh downloads the sheet and validates it exactly like a file. When a sheet link is set, it
   is used instead of the file in the repo. If Google is unreachable, the refresh falls back to the
   repo file and notes it.

Anyone with the published link can read the sheet, so don't put anything private in it.
(To use sheets on your own computer, put the same `SHEET_…_URL=` lines in your `.env` file.)

---

## Column reference

Dates are always `YYYY-MM-DD` (e.g. `2026-11-02`). Team names must match CFBD spelling exactly,
e.g. `Tennessee`, `Texas A&M`, `LSU`, `Vanderbilt`, `Kentucky`. Capitalization of values like
`OUT` / `out` doesn't matter.

### injuries.csv

| Column | Required | Allowed values |
|---|---|---|
| team | yes | CFBD team name |
| player | yes | Full name, spelled like the depth chart/roster |
| position | yes | e.g. QB, RB, WR, TE, OL, DL, LB, CB, S, K, P |
| status | yes | `out`, `doubtful`, `questionable`, `probable`, `available` |
| injury_area | no | e.g. ankle, knee, undisclosed |
| date_reported | yes | date |
| expected_return | no | free text, e.g. "Week 12" or "season" |
| source_url | no | a link starting with `https://` |
| impact_rating | yes | 0–5, your judgment: 0 = no impact, 1 = depth player, 3 = solid starter, 5 = star/QB |
| last_updated | yes | date |
| source | yes | where this came from |

**How the model uses it:** expected points lost = impact × 0.6 × chance of missing the game
(out 100%, doubtful 75%, questionable 50%, probable 10%, available 0%) × depth weight
(starter 1.0, 2nd string 0.5, 3rd 0.25, not on the depth chart 0.5). A 5/5 starter who is out ≈ 3 points.
This rule is an assumption, not something learned from data. You can override it with the injury
sliders on the Matchup page. When a player is healthy again, set `available` or delete the row.

Example (an illustration, not a real report):
```
team,player,position,status,injury_area,date_reported,expected_return,source_url,impact_rating,last_updated,source
Tennessee,Jane Example,WR,questionable,ankle,2026-11-03,,https://example.com/report,2,2026-11-04,example
```

### depth_chart.csv

| Column | Required | Allowed values |
|---|---|---|
| team | yes | CFBD team name (usually `Tennessee`) |
| position_group | yes | `offense`, `defense`, `special teams` |
| position | yes | Offense: QB, RB, WR (or X / Z / SLOT), TE, LT, LG, C, RG, RT. Defense: DE, DT, NT, EDGE, LB (or WILL / MIKE / SAM), CB, NB/STAR, S (or FS / SS). Special teams: K, P, LS, KR, PR, H |
| string | yes | 1 = starter, 2 = backup, 3, 4 |
| player | yes | Full name |
| jersey | no | number |
| class | no | FR, SO, JR, SR, GR, or RS-FR … RS-SR |
| height | no | like `6-2` |
| weight | no | pounds, number |
| snap_pct | no | 0–100 if you know it (public play-by-play has no snap counts) |
| notes | no | anything |
| last_updated / source | yes | as above |

List two starters (string 1) at WR, CB, S, DE, DT or LB if the team plays two at once. The validator only
warns about duplicate starters at other positions.

**Shortcut:** run `python -m pipeline.manual seed-depth` (or ask whoever runs the project) to create
`depth_chart_seed.csv` from the official CFBD roster, with names, positions, jerseys and sizes filled in.
Fill in `position_group` and `string`, delete players who aren't on the depth chart, and copy the rows into
`depth_chart.csv`.

### schemes.csv and opponent_scouting.csv (same columns)

| Column | Required | Notes |
|---|---|---|
| team | yes | CFBD team name |
| unit | yes | `offense`, `defense`, `special teams` |
| base_scheme | yes | e.g. "Spread / vertical RPO", "4-2-5 quarters", "3-3-5" |
| tempo | no | e.g. "fast, no-huddle" |
| personnel_groupings | no | e.g. "11 (70%), 12 (20%)" (from film or a cited source) |
| coverage_shells | no | e.g. "Cover 3, quarters" |
| front | no | e.g. "4-down even, mint" |
| blitz_style | no | e.g. "simulated pressures, sim fire zones" |
| key_concepts | no | e.g. "mesh, vertical choice, inside zone" |
| notes | no | anything |
| last_updated / source | yes | as above |

The site's own numbers (run/pass rates, tempo, shotgun rate, 4th-down aggressiveness) come from
play-by-play automatically. These files are for the things play-by-play can't show.

## Checking your files before committing (optional, for whoever runs the code)

```bash
make validate
```
