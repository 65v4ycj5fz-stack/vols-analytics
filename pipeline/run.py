"""Pipeline entry point: ``python -m pipeline.run`` (or ``make data``).

Fetches (or reuses cached) CFBD data, builds tables, and writes public/data/*.json
and public/data/csv/*.csv. Use ``--offline`` to rebuild purely from cache.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from model.ratings import adjusted_efficiency, elo_history, run_elo
from pipeline import config, manual
from pipeline.cfbd import CFBDClient, CFBDError
from pipeline.publish import write_dataset
from model.situational import fit_fourth_model, fit_pass_model
from pipeline.schemas import VenueRaw
from pipeline.sources import cfbd_games, cfbd_players, cfbd_plays, cfbd_ratings, cfbd_stats, openmeteo
from pipeline.sources.base import fetch
from pipeline.transforms.context import game_context, venues_frame
from pipeline.transforms import players as player_tx
from pipeline.transforms import tendencies as tend
from pipeline.transforms.plays import EXPLOSIVE_PASS_YDS, EXPLOSIVE_RUSH_YDS, plays_frame
from pipeline.transforms.games import fbs_games, games_frame, record, team_schedule
from pipeline.transforms.team_stats import (METRICS, NEUTRAL_RANK, add_ranks, adv_game_frame, box_frame,
                                            game_table, season_table)
from pipeline.transforms.team_stats import Metric


def log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def build(client: CFBDClient) -> dict[str, int]:
    team, season = config.TEAM, config.SEASON
    t0 = time.time()
    manual_data = manual.load_all()  # fail fast, before any API calls, if a manual file is malformed

    # ---- multi-season history (games, lines, per-game advanced stats) ----
    hist_games, hist_adv, game_sources = [], [], []
    for yr in config.ALL_SEASONS:
        g = cfbd_games.games(client, yr)
        ln = cfbd_games.lines(client, yr)
        adv = cfbd_stats.game_advanced(client, yr)
        hist_games.append(games_frame(g.rows, ln.rows))
        hist_adv.append(adv_game_frame(adv.rows))
        game_sources += g.sources + ln.sources + adv.sources
        if yr == season:
            cur_game_rows, cur_game_sources = g.rows, g.sources + ln.sources
            cur_adv_sources = adv.sources
        log(f"season {yr}: {len(g.rows)} games, {len(adv.rows)} team-game advanced rows")
    all_games = pd.concat(hist_games, ignore_index=True)
    all_adv = pd.concat(hist_adv, ignore_index=True)
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    all_games.to_parquet(config.PROCESSED / "games.parquet", index=False)
    all_adv.to_parquet(config.PROCESSED / "adv_games.parquet", index=False)
    build_context(client, all_games)

    # ---- current season detail ----
    teams = cfbd_stats.fbs_teams(client, season)
    stats = cfbd_stats.season_stats(client, season)
    adv_season = cfbd_stats.season_advanced(client, season)
    box = cfbd_stats.box_scores(client, season, cur_game_rows)
    sp, elo_cfbd, fpi = (cfbd_ratings.sp_plus(client, season), cfbd_ratings.elo(client, season),
                         cfbd_ratings.fpi(client, season))
    fbs_names = {t.school for t in teams.rows}
    team_conf = {t.school: t.conference for t in teams.rows}
    cur_games = all_games[all_games["season"] == season]

    # schedule + results
    sched = team_schedule(cur_games, team)
    sched_hist = team_schedule(all_games, team)
    write_dataset("schedule", sched, season=season, sources=cur_game_sources,
                  description=f"{team} {season} schedule, results, consensus closing spread and result vs spread.",
                  notes=["spread: negative = Tennessee favored; median across sportsbooks listed by CFBD.",
                         "Spreads are shown for model backtesting context only."])
    write_dataset("results_history", sched_hist[sched_hist["completed"]], sources=game_sources,
                  description=f"{team} results {config.ALL_SEASONS[0]}-{season}.")

    # team season stats (all FBS) with ranks
    season_tbl = season_table(stats.rows, adv_season.rows, fbs_games(cur_games), teams.rows)
    write_dataset("team_season_stats", season_tbl, season=season,
                  sources=stats.sources + adv_season.sources + teams.sources + cur_game_sources,
                  description="Season team stats for every FBS team with national and conference ranks (1 = best).",
                  notes=["EPA = CFBD predicted points added (PPA).",
                         "Red-zone and situational splits come from play-by-play (Phase 2)."])

    # per-game team stats (all teams, current season)
    games_tbl = game_table(fbs_games(cur_games), all_adv[all_adv["season"] == season], box_frame(box.rows))
    games_tbl = games_tbl[games_tbl["team"].isin(fbs_names)]
    write_dataset("team_game_stats", games_tbl, season=season,
                  sources=box.sources + cur_game_sources + cur_adv_sources,
                  description="Per-game stats for every FBS team: points, EPA/success/explosiveness, box score.")

    # ratings
    elo_games, elo_final = run_elo(fbs_games(all_games))
    adj_rows = game_table(fbs_games(cur_games), all_adv[all_adv["season"] == season], pd.DataFrame())
    adj_epa, hfa_epa = adjusted_efficiency(adj_rows, "off_epa")
    adj_sr, _ = adjusted_efficiency(adj_rows, "off_success")
    ratings = pd.DataFrame({"team": sorted(fbs_names)})
    ratings["conference"] = ratings["team"].map(team_conf)
    ratings["elo"] = ratings["team"].map(elo_final)
    ratings = ratings.merge(adj_epa.rename(columns={"adj_off": "adj_off_epa", "adj_def": "adj_def_epa", "games": "games"}),
                            on="team", how="left")
    ratings = ratings.merge(adj_sr[["team", "adj_off", "adj_def"]].rename(columns={
        "adj_off": "adj_off_success", "adj_def": "adj_def_success"}), on="team", how="left")
    ratings["adj_net_epa"] = ratings["adj_off_epa"] - ratings["adj_def_epa"]
    ratings = ratings.merge(pd.DataFrame([{
        "team": r.team, "sp_rating": r.rating, "sp_off": r.offense.rating if r.offense else None,
        "sp_def": r.defense.rating if r.defense else None,
        "sp_st": r.specialTeams.rating if r.specialTeams else None} for r in sp.rows]), on="team", how="left")
    ratings = ratings.merge(pd.DataFrame([{"team": r.team, "cfbd_elo": r.elo} for r in elo_cfbd.rows]), on="team", how="left")
    ratings = ratings.merge(pd.DataFrame([{"team": r.team, "fpi": r.fpi} for r in fpi.rows]), on="team", how="left")
    rating_metrics = [
        Metric("elo", "Elo (ours)", "Elo", True, "overall", "Self-computed margin-aware Elo, 2019 onward."),
        Metric("adj_net_epa", "Adj. net EPA/play", "pts/play", True, "overall", "Opponent-adjusted offensive minus defensive EPA/play (ours)."),
        Metric("adj_off_epa", "Adj. offensive EPA/play", "pts/play", True, "offense", "Opponent- and home-adjusted (ours)."),
        Metric("adj_def_epa", "Adj. defensive EPA/play allowed", "pts/play", False, "defense", "Opponent- and home-adjusted (ours)."),
        Metric("sp_rating", "SP+", "pts", True, "overall", "Bill Connelly's SP+ as published via CFBD."),
        Metric("sp_off", "SP+ offense", "pts", True, "offense", "SP+ offensive rating."),
        Metric("sp_def", "SP+ defense", "pts", False, "defense", "SP+ defensive rating (points allowed; lower is better)."),
        Metric("cfbd_elo", "CFBD Elo", "Elo", True, "overall", "CFBD's published Elo."),
        Metric("fpi", "FPI", "pts", True, "overall", "ESPN FPI as relayed by CFBD."),
    ]
    ratings = add_ranks(ratings, rating_metrics)
    write_dataset("ratings", ratings, season=season,
                  sources=sp.sources + elo_cfbd.sources + fpi.sources + game_sources,
                  description="Published (SP+, CFBD Elo, FPI) and self-computed (Elo, opponent-adjusted EPA) ratings, FBS.",
                  notes=[f"Fitted home-field edge in EPA/play this season: {hfa_epa:+.3f}.",
                         "Elo and adjustment parameters are documented defaults until the Phase 3 fit."])

    # rating trend for the team: Elo after each game + adjusted net EPA using games through that date
    trend = elo_history(elo_games[elo_games["season"] == season], team)
    net = []
    for dt in trend["start_date"]:
        sub = adj_rows[adj_rows["start_date"] <= dt]
        a, _ = adjusted_efficiency(sub, "off_epa")
        r = a[a["team"] == team]
        net.append(float(r["adj_off"].iloc[0] - r["adj_def"].iloc[0]) if len(r) else np.nan)
    trend["adj_net_epa"] = net
    write_dataset("rating_trend", trend, season=season, sources=game_sources,
                  description=f"{team} rating after each {season} game: our Elo and opponent-adjusted net EPA/play.")

    build_plays_and_players(client, cur_game_rows, cur_games, fbs_names, sched)
    publish_manual(manual_data, set(all_games["home_team"]) | set(all_games["away_team"]))

    write_dataset("metrics", [
        {**m.__dict__, "neutral": m.key in NEUTRAL_RANK | tend.NEUTRAL_TENDENCIES}
        for m in METRICS + rating_metrics + tend.TENDENCY_METRICS
    ], sources=[], description="Metric labels, units, definitions and rank direction used by the site.", csv=False)

    rec, conf_rec = record(sched), record(sched, conference_only=True)
    write_dataset("meta", {
        "team": team, "conference": config.CONFERENCE, "season": season,
        "seasons_loaded": config.ALL_SEASONS,
        "last_refreshed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "record": rec, "conference_record": conf_rec,
        "cfbd_calls_this_run": client.calls_made,
    }, sources=cur_game_sources, season=season, description="Site-wide metadata and refresh time.", csv=False)

    log(f"done in {time.time() - t0:.1f}s; CFBD calls this run: {client.calls_made}")
    return {"calls": client.calls_made}


def build_context(client: CFBDClient, all_games: pd.DataFrame) -> None:
    """Phase 4 inputs: venues/travel/rest, box-score turnovers (recent seasons) and game weather."""
    season = config.SEASON
    venues = fetch(client, "/venues", {}, VenueRaw, season, ttl_hours=24 * 30)
    ctx = game_context(all_games, venues_frame(venues.rows))
    ctx.to_parquet(config.PROCESSED / "game_context.parquet", index=False)

    boxes = []
    for yr in range(max(config.ALL_SEASONS[0], season - 2), season + 1):
        yr_games = cfbd_games.games(client, yr).rows
        boxes.append(box_frame(cfbd_stats.box_scores(client, yr, yr_games).rows).assign(season=yr))
    pd.concat(boxes, ignore_index=True).to_parquet(config.PROCESSED / "box_games.parquet", index=False)

    fbs2 = all_games[(all_games["home_class"] == "fbs") & (all_games["away_class"] == "fbs")]
    g = fbs2.merge(ctx[["game_id", "dome", "lat", "lon"]], on="game_id")
    g = g[~g["dome"] & (g["season"] >= 2021)]
    now = pd.Timestamp.now(tz="UTC")
    past = g[g["completed"] & (g["start_date"] < now - pd.Timedelta(days=6))]
    # TBD kickoffs are stored as midnight placeholders, so a forecast would be for the wrong hour
    upcoming = g[~g["completed"] & ~g["start_time_tbd"] & (g["start_date"] > now) & (g["start_date"] < now + pd.Timedelta(days=15))]
    offline = client.offline
    empty = pd.DataFrame(columns=["game_id", "temp_f", "wind_mph", "precip_mm"])
    # weather is optional: each part fails independently and the site shows "no weather data"
    try:
        wx_hist = openmeteo.game_weather(past, "archive", openmeteo.client("archive", offline=offline))
    except CFBDError as exc:
        log(f"historical weather unavailable: {str(exc)[:120]}")
        wx_hist = empty
    try:
        wx_next = openmeteo.game_weather(upcoming, "forecast", openmeteo.client("forecast", offline=offline),
                                         ttl_hours=6)
    except CFBDError as exc:
        log(f"forecast weather unavailable: {str(exc)[:120]}")
        wx_next = empty
    wx = pd.concat([wx_hist.assign(kind="observed"), wx_next.assign(kind="forecast")], ignore_index=True)
    wx.to_parquet(config.PROCESSED / "weather.parquet", index=False)
    log(f"context: {len(ctx):,} games, weather for {len(wx_hist):,} past + {len(wx_next):,} upcoming outdoor games")


def publish_manual(loaded: dict[str, manual.Loaded], known_teams: set[str]) -> None:
    """Publish validated manual datasets (with model injury impact) and keep copies for the model."""
    from model.adjustments import injury_points

    out_dir = config.PROCESSED / "manual"
    out_dir.mkdir(parents=True, exist_ok=True)
    status = []
    for name, l in loaded.items():
        df = pd.DataFrame(l.rows, columns=l.spec.columns)
        warnings = list(l.warnings) + [f"{name}: team '{t}' doesn't match a CFBD team name"
                                       for t in sorted(set(df["team"]) - known_teams)]
        df.to_csv(out_dir / f"{name}.csv", index=False)
        if name == "injuries" and len(df):
            depth = pd.DataFrame(loaded["depth_chart"].rows)
            per = {}
            for t in df["team"].unique():
                _, detail = injury_points(df, depth if len(depth) else None, t)
                per.update({(t, d["player"]): d for d in detail})
            df["prob_out"] = [per.get((t, p), {}).get("prob_out") for t, p in zip(df["team"], df["player"])]
            df["depth_weight"] = [per.get((t, p), {}).get("depth_weight") for t, p in zip(df["team"], df["player"])]
            df["model_points"] = [per.get((t, p), {}).get("points") for t, p in zip(df["team"], df["player"])]
        src = [{"source": f"manual entry ({l.origin})", "endpoint": f"data/manual/{name}.csv",
                "fetched_at": max(df["last_updated"].astype(str)) if len(df) else None}]
        notes = ["Entered by hand; every row lists its source and last-updated date."] + warnings
        if name == "injuries":
            notes.append("model_points = impact x 0.6 pts x P(out by status) x depth weight (an assumption; see Model page).")
        write_dataset(name, df, sources=src, description=l.spec.description, notes=notes)
        status.append({"dataset": name, "origin": l.origin, "rows": len(df), "warnings": warnings,
                       "last_updated": max(df["last_updated"].astype(str)) if len(df) else None})
        for w in warnings:
            log(f"manual warning: {w}")
    write_dataset("manual_status", status, sources=[], csv=False,
                  description="Which manual datasets are filled in, where they came from, and any warnings.")


def build_plays_and_players(client: CFBDClient, cur_game_rows, cur_games: pd.DataFrame,
                            fbs_names: set[str], sched: pd.DataFrame) -> None:
    """Phase 2: play-by-play aggregation, tendency tables and player stats."""
    team, season = config.TEAM, config.SEASON
    focus = [team] + [o for o in sched["opponent"].tolist() if o != team]  # Tennessee + every opponent

    raw = cfbd_plays.plays(client, season, cur_game_rows)
    week_of = dict(zip(cur_games["game_id"], cur_games["week"]))
    plays = plays_frame(raw.rows, season, week_of)
    plays = plays[plays["game_id"].isin(set(cur_games["game_id"]))]
    plays.to_parquet(config.PROCESSED / f"plays_{season}.parquet", index=False)  # local only, never published
    log(f"plays {season}: {len(plays):,} rows, {int(plays['is_scrimmage'].sum()):,} scrimmage")
    fbs_plays = plays[plays["offense"].isin(fbs_names) | plays["defense"].isin(fbs_names)]

    pass_model, pass_s = fit_pass_model(fbs_plays)
    fourth_model, fourth_s = fit_fourth_model(fbs_plays)
    models = [pass_model.summary(), fourth_model.summary()]
    log(f"pass model AUC {pass_model.cv_auc:.3f}; 4th-down model AUC {fourth_model.cv_auc:.3f}")
    defs = [f"Explosive = run of {EXPLOSIVE_RUSH_YDS}+ yds or pass of {EXPLOSIVE_PASS_YDS}+ yds.",
            "Garbage time (CFBD definition) excluded: margin > 38 in Q2, > 28 in Q3, > 22 in Q4.",
            "Success = 50% of yards-to-go on 1st down, 70% on 2nd, 100% on 3rd/4th.",
            "Formation, tempo and pass depth are parsed from the official play-by-play text; personnel "
            "groupings, play-action and blitz/pressure are not in public play-by-play."]
    src = raw.sources

    summary = tend.team_summary(fbs_plays, pass_s, fourth_s, fbs_names)
    summary = summary.merge(cur_games[["home_team", "home_conf"]].drop_duplicates("home_team")
                            .rename(columns={"home_team": "team", "home_conf": "conference"}), on="team", how="left")
    summary = add_ranks(summary, tend.TENDENCY_METRICS)
    write_dataset("tendency_summary", summary, season=season, sources=src,
                  description="Play-by-play tendency metrics for every FBS team with national/conference ranks.",
                  notes=defs + [f"Model fit quality: {m['model']} held-out AUC {m['cv_auc']:.3f}, "
                                f"log loss {m['cv_log_loss']:.3f} vs {m['baseline_log_loss']:.3f} for a constant rate."
                                for m in models])
    write_dataset("tendency_splits", tend.split_table(fbs_plays, focus, fbs_names), season=season, sources=src,
                  description=f"Run/pass rate and efficiency by down, distance, field zone, score, quarter, "
                              f"formation and tempo for {team} and each opponent (offense and defense).",
                  notes=defs + [f"Rows with fewer than {tend.SMALL_SAMPLE} plays are flagged small_sample."])
    rk = cfbd_plays.rankings(client, season)
    ranked = {w.week: {r.school for p in w.polls if p.poll == "AP Top 25" for r in p.ranks}
              for w in rk.rows if w.seasonType == "regular"}
    write_dataset("situational_splits", tend.situational_splits(fbs_plays, cur_games, focus, ranked),
                  season=season, sources=src + rk.sources,
                  description="Leading/trailing, home/away, vs AP Top 25 and conference splits (play-level efficiency).",
                  notes=defs + ["'vs AP Top 25' uses the AP poll released before that week's games."])
    write_dataset("fourth_downs", tend.fourth_down_log(fourth_s, focus, cur_games), season=season, sources=src,
                  description="Every non-garbage 4th-down decision with the probability a typical FBS coach goes for it.",
                  notes=["xgo is a descriptive peer model, not a recommendation; see tendency_models.json for fit quality."])
    write_dataset("proe_by_game", tend.proe_by_game(pass_s, focus, cur_games), season=season, sources=src,
                  description="Pass rate over expected per game with 95% intervals.")
    write_dataset("tendency_models", models, season=season, sources=src, csv=False,
                  description="Fit diagnostics for the pass-rate and 4th-down situation models.")

    # players
    ps = cfbd_players.season_stats(client, season)
    us = cfbd_players.usage(client, season)
    ro = cfbd_players.roster(client, season, team)
    gl = cfbd_players.game_logs(client, season, team, cur_game_rows)
    focus_set = set(focus)
    write_dataset("player_season_stats", player_tx.season_stats(ps.rows, focus_set), season=season, drop_nulls=True,
                  sources=ps.sources, description=f"Season player stats for {team} and its opponents.")
    write_dataset("player_usage", player_tx.usage(us.rows, focus_set), season=season, sources=us.sources,
                  description="CFBD usage rate: share of the team's plays involving the player (by down/type).",
                  notes=["Snap counts are not available from CFBD; usage covers ball-carriers and targets only."])
    write_dataset("player_game_logs", player_tx.game_logs(gl.rows, team, cur_games), season=season, drop_nulls=True,
                  sources=gl.sources, description=f"{team} per-game player box scores.")
    roster = player_tx.roster(ro.rows)
    roster_notes = []
    if len(roster) >= 20 and roster["class_year"].nunique(dropna=True) <= 1:
        roster["class_year"] = None  # a single value for every player is a source-data problem, not a class
        roster_notes.append("CFBD reported the same class year for every player this season, so class is left blank.")
    write_dataset("roster", roster, season=season, sources=ro.sources, notes=roster_notes,
                  description=f"{team} roster from CFBD (class_year 1 = freshman).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="use cached responses only; no API calls")
    ap.add_argument("--max-calls", type=int, default=None, help="per-run CFBD call budget")
    args = ap.parse_args(argv)
    overrides = {}
    if args.offline:
        overrides["offline"] = True
    if args.max_calls is not None:
        overrides["max_calls"] = args.max_calls
    client = CFBDClient.from_env(**overrides)
    try:
        build(client)
    except CFBDError as exc:
        log(f"ERROR: {exc}")
        return 1
    except manual.ManualDataError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
