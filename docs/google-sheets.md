# Mirror the data in Google Sheets

Every table on the site is published as a CSV next to the site:

```
https://<your-username>.github.io/<repo-name>/data/csv/<dataset>.csv
```

Google Sheets can pull these live with `IMPORTDATA`. The site's **Data** page has a "Copy Sheets formula"
button that fills in the right URL for you.

## Steps

1. Create a new Google Sheet.
2. Make one tab per dataset you want (e.g. `schedule`, `team_season_stats`, `projections_table`).
3. In cell **A1** of each tab, paste the formula for that dataset, for example:
   ```
   =IMPORTDATA("https://<your-username>.github.io/<repo-name>/data/csv/schedule.csv")
   ```
4. Sheets re-fetches roughly every hour, so the tab follows the site's daily refresh. Build charts or
   pivot tables on other tabs that reference these.

## Useful datasets

| Dataset | Contents |
|---|---|
| `schedule` | Tennessee schedule, results, closing spread, result vs spread |
| `projections_table` | Projected score, margin, 80% range, win probability per game |
| `season_win_distribution` | Probability of each regular-season win total |
| `team_season_stats` | Every FBS team's season stats with national and conference ranks |
| `team_game_stats` | Every FBS team's per-game stats |
| `ratings` | Our Elo and adjusted EPA, plus SP+, CFBD Elo and FPI |
| `tendency_summary` | Run/pass and situational tendencies for every FBS team, with ranks |
| `tendency_splits` | Tennessee and opponents by down & distance, field zone, score, quarter |
| `fourth_downs` | Every 4th-down decision with the typical-coach go probability |
| `player_season_stats`, `player_game_logs`, `player_usage`, `roster` | Player data |
| `injuries`, `depth_chart`, `schemes`, `opponent_scouting` | The manual datasets as published |
| `backtest_games` | Every backtested game: model, Elo and market predictions vs results |

Column meanings: [data-dictionary.md](data-dictionary.md).

Notes:
- `IMPORTDATA` allows a limited number of calls per sheet; if a tab shows `#N/A`, wait and reload.
- Percentages are stored as fractions (0.452 = 45.2%). Format the column as percent in Sheets.
- To *edit* injuries or the depth chart in Sheets (the other direction), see `data/manual/README.md`.
