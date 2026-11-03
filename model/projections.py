"""Live projections: baseline + adjustments -> projected score, simulation, explanation."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from model.adjustments import (MARGIN_ADJ, POINTS_PER_IMPACT, TOTAL_ADJ, injury_points)
from model.explain import keys_to_game, model_factors, split_edges
from model.ratings import adjusted_efficiency
from model.simulate import season_outlook, simulate_game, summarize_game
from pipeline import config

MARGIN_INPUT_DETAIL = {
    "rest_diff": lambda v: f"{v:+.0f} days of rest vs opponent",
    "travel_diff": lambda v: f"opponent travels {v * 1000:+,.0f} km more" if v >= 0 else f"we travel {-v * 1000:,.0f} km more",
    "to_diff": lambda v: f"turnover margin edge {v:+.2f}/game so far",
    "form_edge": lambda v: f"recent-form rating edge {v:+.3f} EPA/play",
}


def _sign(row) -> float:
    return 1.0 if row["home_team"] == config.TEAM else -1.0


def margin_adjustments(row: pd.Series, fit: dict, sign: float) -> list[dict]:
    items = []
    for a in fit["margin"]:
        v = row.get(a["key"])
        v = 0.0 if v is None or pd.isna(v) else float(v)
        pts = sign * a["coef"] * v
        items.append({"key": a["key"], "label": a["label"], "unit": a["unit"], "input": sign * v,
                      "coef": a["coef"], "se": a["se"], "ci95_low": a["ci95_low"], "ci95_high": a["ci95_high"],
                      "significant": a["significant"], "points": pts, "source": "fitted",
                      "detail": MARGIN_INPUT_DETAIL[a["key"]](sign * v), "description": a["description"]})
    return items


def total_adjustments(row: pd.Series, fit: dict) -> list[dict]:
    items = []
    for a in fit["total"]:
        v = row.get(a["key"])
        v = 0.0 if v is None or pd.isna(v) else float(v)
        items.append({"key": a["key"], "label": a["label"], "unit": a["unit"], "input": v, "coef": a["coef"],
                      "se": a["se"], "significant": a["significant"], "points": a["coef"] * v, "source": "fitted",
                      "description": a["description"]})
    return items


def split_ratings(adv: pd.DataFrame, games: pd.DataFrame, plays_path) -> dict:
    """Season-to-date opponent-adjusted rush/pass EPA and run share (descriptive explanations)."""
    from model.features import team_game_rows
    cur = games[games["season"] == config.SEASON]
    tg = team_game_rows(cur, adv).merge(adv[["game_id", "team", "off_rush_epa", "off_pass_epa"]], on=["game_id", "team"])
    out = {}
    for kind in ("rush", "pass"):
        r, _ = adjusted_efficiency(tg, f"off_{kind}_epa")
        for t, o, d in zip(r["team"], r["adj_off"], r["adj_def"]):
            out[(t, kind)] = (float(o), float(d))
    try:
        p = pd.read_parquet(plays_path, columns=["offense", "is_scrimmage", "garbage", "is_rush"])
        p = p[p["is_scrimmage"] & ~p["garbage"]]
        for t, s in p.groupby("offense")["is_rush"].mean().items():
            out[(t, "rush_share")] = float(s)
    except FileNotFoundError:
        pass
    return out


def build(f: pd.DataFrame, margin_model, totals_model, fit: dict, rho: float, tau: float,
          injuries: pd.DataFrame, depth: pd.DataFrame, splits: dict, tendencies: dict,
          sched: pd.DataFrame) -> tuple[list[dict], dict]:
    team, season = config.TEAM, config.SEASON
    sig_m, sig_t = margin_model.sigma, totals_model.sigma
    cur = f[f["season"] == season].copy()
    cur["base_margin_home"] = margin_model.predict(cur)
    cur["base_total"] = totals_model.predict(cur)
    mcoef = {a["key"]: a["coef"] for a in fit["margin"]}
    tcoef = {a["key"]: a["coef"] for a in fit["total"]}
    cur["adj_margin_home"] = cur["base_margin_home"] + sum(cur[k].astype(float).fillna(0) * c for k, c in mcoef.items())
    cur["adj_total"] = cur["base_total"] + sum(cur[k].astype(float).fillna(0) * c for k, c in tcoef.items())
    inj_cache: dict[str, tuple[float, list]] = {}

    def inj(t):
        if t not in inj_cache:
            inj_cache[t] = injury_points(injuries, depth, t)
        return inj_cache[t]

    for side in ("home", "away"):
        cur[f"{side}_inj"] = [0.0 if c else inj(t)[0] for t, c in zip(cur[f"{side}_team"], cur["completed"])]
    cur["final_margin_home"] = cur["adj_margin_home"] - cur["home_inj"] + cur["away_inj"]

    mine = cur[(cur["home_team"] == team) | (cur["away_team"] == team)].sort_values("start_date")
    projections = []
    for _, r in mine.iterrows():
        s = _sign(r)
        opp = r["away_team"] if s > 0 else r["home_team"]
        site = "neutral" if r["neutral_site"] else ("home" if s > 0 else "away")
        madj = margin_adjustments(r, fit, s)
        team_inj, team_det = (0.0, []) if r["completed"] else inj(team)
        opp_inj, opp_det = (0.0, []) if r["completed"] else inj(opp)
        madj.append({"key": "injuries", "label": "Injuries (manual)", "unit": "points", "input": None,
                     "coef": POINTS_PER_IMPACT, "se": None, "significant": None, "points": opp_inj - team_inj,
                     "source": "manual assumption",
                     "detail": f"{team} -{team_inj:.1f}, {opp} -{opp_inj:.1f} expected pts from listed injuries"
                     if (team_det or opp_det) else "no injuries entered in data/manual/injuries.csv",
                     "description": f"Impact rating (0-5) x {POINTS_PER_IMPACT} pts x P(out by status) x depth-chart "
                                    "weight. An assumption, not fit from data; adjustable on the Matchup page.",
                     "players": {"team": team_det, "opponent": opp_det}})
        tadj = total_adjustments(r, fit)
        base_m = s * r["base_margin_home"]
        final_m = s * r["final_margin_home"]
        total = float(r["adj_total"])
        mkt_spread = -s * r["market_margin"] if pd.notna(r["market_margin"]) else None
        sim = summarize_game(simulate_game(final_m, total, sig_m, sig_t, rho), mkt_spread)
        row_t = {"site": site,
                 "team_elo": r["home_elo_pre"] if s > 0 else r["away_elo_pre"],
                 "opp_elo": r["away_elo_pre"] if s > 0 else r["home_elo_pre"],
                 "team_adj_off": r["home_adj_off"] if s > 0 else r["away_adj_off"],
                 "team_adj_def": r["home_adj_def"] if s > 0 else r["away_adj_def"],
                 "opp_adj_off": r["away_adj_off"] if s > 0 else r["home_adj_off"],
                 "opp_adj_def": r["away_adj_def"] if s > 0 else r["home_adj_def"]}
        factors = model_factors(row_t, margin_model.coef, team, opp, madj)
        edges = split_edges(team, opp, splits, margin_model.coef["epa_diff"])
        wx = None
        if pd.notna(r.get("temp_f")) and not r.get("dome"):
            wx = {"kind": r.get("weather_kind"), "temp_f": r["temp_f"], "wind_mph": r["wind_mph"],
                  "precip_mm": r["precip_mm"]}
        elif r.get("dome"):
            wx = {"kind": "indoor"}
        done = bool(r["completed"])
        projections.append({
            "game_id": int(r["game_id"]), "week": int(r["week"]), "start_date": r["start_date"],
            "opponent": opp, "site": site, "completed": done,
            "actual": {"team": float(r["home_pts"] if s > 0 else r["away_pts"]),
                       "opp": float(r["away_pts"] if s > 0 else r["home_pts"]),
                       "margin": float(s * r["margin"])} if done else None,
            "baseline": {"margin": base_m, "total": float(r["base_total"]),
                         "win_prob": float(margin_model.win_prob(base_m))},
            "adjustments": madj, "total_adjustments": tadj,
            "projection": {"margin": final_m, "total": total, "team_points": (total + final_m) / 2,
                           "opp_points": (total - final_m) / 2,
                           "win_prob": float(margin_model.win_prob(final_m)),
                           "margin_p10": final_m - 1.2816 * sig_m, "margin_p90": final_m + 1.2816 * sig_m},
            "simulation": sim if not done else {k: sim[k] for k in ("n_sims", "win_prob", "team_points", "opp_points", "margin")},
            "market": {"spread": mkt_spread, "total": None if pd.isna(r.get("total")) else float(r["total"])},
            "factors": factors, "split_edges": edges, "keys_to_game": keys_to_game(team, opp, edges, tendencies),
            "weather": wx,
            "inputs": {**row_t, "team_games_in_season": r["home_games_in_season"] if s > 0 else r["away_games_in_season"],
                       "opp_games_in_season": r["away_games_in_season"] if s > 0 else r["home_games_in_season"]},
        })

    # season outlook
    rem = mine[~mine["completed"]].assign(margin=lambda d: d["final_margin_home"])
    conf = cur[~cur["completed"] & cur["conference_game"] & (cur["home_conf"] == config.CONFERENCE)
               & (cur["away_conf"] == config.CONFERENCE)].assign(margin=lambda d: d["final_margin_home"], conf=True)
    rem = rem.assign(conf=rem["conference_game"] & (rem["home_conf"] == config.CONFERENCE)
                     & (rem["away_conf"] == config.CONFERENCE))
    done_conf = cur[cur["completed"] & cur["conference_game"] & (cur["home_conf"] == config.CONFERENCE)
                    & (cur["away_conf"] == config.CONFERENCE)]
    conf_teams = sorted(set(cur.loc[cur["home_conf"] == config.CONFERENCE, "home_team"])
                        | set(cur.loc[cur["away_conf"] == config.CONFERENCE, "away_team"]))
    st = pd.DataFrame({"team": conf_teams})
    st["wins"] = [int(((done_conf["home_team"] == t) & (done_conf["margin"] > 0)).sum()
                      + ((done_conf["away_team"] == t) & (done_conf["margin"] < 0)).sum()) for t in conf_teams]
    st["losses"] = [int(((done_conf["home_team"] == t) & (done_conf["margin"] < 0)).sum()
                        + ((done_conf["away_team"] == t) & (done_conf["margin"] > 0)).sum()) for t in conf_teams]
    played = sched[sched["result"] != ""]
    outlook = season_outlook(rem, int((played["result"] == "W").sum()), int((played["result"] == "L").sum()),
                             team, conf, st, sig_m, tau)
    outlook["notes"] = [
        "Remaining games use the adjusted projection (including any injuries entered).",
        f"Team strength uncertainty tau = {tau:.1f} pts, estimated from out-of-sample residuals.",
        "No College Football Playoff probability is shown: selection is by committee. "
        "Win totals and the SEC finish are the measurable context.",
    ]
    outlook["current_conference_standings"] = st.sort_values(["wins", "losses"], ascending=[False, True]).to_dict("records")
    return projections, outlook


def load_tendencies() -> dict:
    p = config.PUBLIC_DATA / "tendency_summary.json"
    if not p.exists():
        return {}
    rows = json.loads(p.read_text())["data"]
    return {r["team"]: {k: (np.nan if v is None else v) for k, v in r.items()} for r in rows}
