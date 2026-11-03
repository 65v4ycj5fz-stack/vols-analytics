"""Plain-English factor breakdowns for a single projection (team perspective).

The model factors (home field, Elo, offense/defense EPA matchups, adjustments) add up
exactly to the projected margin. The rush/pass split is descriptive. It breaks the EPA
matchup down further, and those points are already inside the EPA factors, so they are
not added again.
"""

from __future__ import annotations

import numpy as np


def _pts(x: float) -> str:
    return f"{x:+.1f} pts"


def model_factors(row: dict, coef: dict, team: str, opp: str, adj: list[dict]) -> list[dict]:
    """``row`` is team-perspective: site, team_elo, opp_elo, team/opp adj_off/adj_def; ``adj`` = adjustment items."""
    b_epa = coef["epa_diff"]
    site_pts = coef["site_home"] * (1 if row["site"] == "home" else -1 if row["site"] == "away" else 0)
    off_edge = row["team_adj_off"] + row["opp_adj_def"]          # EPA/play our offense should gain
    def_edge = -(row["opp_adj_off"] + row["team_adj_def"])       # EPA/play our defense should save
    elo_pts = coef["elo_diff"] * (row["team_elo"] - row["opp_elo"])
    items = [
        {"key": "home_field", "points": site_pts, "text":
            ("Home field" if row["site"] == "home" else "Road game" if row["site"] == "away" else "Neutral site")
            + f": {_pts(site_pts)} (fitted home-field edge {coef['site_home']:.1f} pts)"},
        {"key": "elo", "points": elo_pts, "text":
            f"Results-based rating (Elo {row['team_elo']:.0f} vs {row['opp_elo']:.0f}): {_pts(elo_pts)}"},
        {"key": "offense_matchup", "points": b_epa * off_edge, "text":
            f"{team} offense vs {opp} defense: {off_edge:+.3f} EPA/play vs an average matchup, "
            f"worth about {_pts(b_epa * off_edge)}"},
        {"key": "defense_matchup", "points": b_epa * def_edge, "text":
            f"{team} defense vs {opp} offense: {def_edge:+.3f} EPA/play saved vs average, "
            f"worth about {_pts(b_epa * def_edge)}"},
    ]
    for a in adj:
        if a["points"] != 0:
            items.append({"key": a["key"], "points": a["points"], "text": f"{a['label']}: {_pts(a['points'])} ({a['detail']})"})
    return sorted(items, key=lambda x: -abs(x["points"]))


def split_edges(team: str, opp: str, ratings: dict, b_epa: float) -> list[dict]:
    """Descriptive rush/pass matchup edges from season-to-date opponent-adjusted split ratings.

    ``ratings[(team, kind)]`` -> (adj_off, adj_def) for kind in {"rush", "pass"};
    ``ratings[(team, "rush_share")]`` -> share of the team's plays that are runs.
    """
    out = []
    for kind in ("rush", "pass"):
        t, o = ratings.get((team, kind)), ratings.get((opp, kind))
        if t is None or o is None:
            continue
        share_t = ratings.get((team, "rush_share"), 0.5)
        share_o = ratings.get((opp, "rush_share"), 0.5)
        if kind == "pass":
            share_t, share_o = 1 - share_t, 1 - share_o
        off_edge = t[0] + o[1]
        def_edge = -(o[0] + t[1])
        for side, edge, share in (("offense", off_edge, share_t), ("defense", def_edge, share_o)):
            pts = b_epa * edge * share
            who = f"{team} {kind} {side}" + (f" vs {opp} {kind} defense" if side == "offense" else f" vs {opp} {kind} offense")
            out.append({"key": f"{kind}_{side}", "edge_epa": float(edge), "points_approx": float(pts),
                        "text": f"{who}: {edge:+.3f} EPA/{'rush' if kind == 'rush' else 'dropback'}, "
                                f"about {_pts(pts)} at {share:.0%} of snaps (descriptive; part of the EPA factors)"})
    return sorted(out, key=lambda x: -abs(x["points_approx"]))


def keys_to_game(team: str, opp: str, edges: list[dict], tendencies: dict) -> list[str]:
    """Short auto-generated 'keys to the game' from the biggest edges and tendencies."""
    unit = {"rush": "EPA/rush", "pass": "EPA/dropback"}
    templates = {
        ("rush", "offense", True): "Run the ball: {team}'s rush offense has a {e:+.2f} {u} edge vs {opp}'s rush defense.",
        ("rush", "offense", False): "Tough sledding on the ground: {opp}'s rush defense has a {e:.2f} {u} edge over {team}'s run game.",
        ("pass", "offense", True): "Attack through the air: {team}'s pass offense has a {e:+.2f} {u} edge vs {opp}'s pass defense.",
        ("pass", "offense", False): "Passing will be hard: {opp}'s pass defense has a {e:.2f} {u} edge over {team}'s passing game.",
        ("rush", "defense", True): "Make {opp} one-dimensional: {team}'s run defense has a {e:+.2f} {u} edge vs {opp}'s ground game.",
        ("rush", "defense", False): "Stop the run: {opp}'s rush offense has a {e:.2f} {u} edge vs {team}'s run defense.",
        ("pass", "defense", True): "Make {opp} throw: {team}'s pass defense has a {e:+.2f} {u} edge vs {opp}'s passing game.",
        ("pass", "defense", False): "Contain the passing game: {opp}'s pass offense has a {e:.2f} {u} edge vs {team}'s secondary.",
    }
    keys = []
    for e in edges[:4]:
        kind, side = e["key"].split("_")
        if abs(e["edge_epa"]) < 0.03:
            continue
        good = e["edge_epa"] > 0
        keys.append(templates[(kind, side, good)].format(team=team, opp=opp, u=unit[kind],
                                                         e=e["edge_epa"] if good else -e["edge_epa"]))
    t, o = tendencies.get(team, {}), tendencies.get(opp, {})
    if t.get("def_sack_rate") and o.get("sack_rate_allowed") and not np.isnan(t["def_sack_rate"]):
        keys.append(f"Pass rush: {team} sacks {t['def_sack_rate']:.1%} of dropbacks; {opp} allows {o['sack_rate_allowed']:.1%}.")
    if t.get("rz_td_rate") and o.get("def_rz_td_rate"):
        keys.append(f"Red zone: {team} scores TDs on {t['rz_td_rate']:.0%} of trips; {opp} allows TDs on {o['def_rz_td_rate']:.0%}.")
    if o.get("explosive_rate") and t.get("def_explosive_allowed"):
        keys.append(f"Explosives: {opp} hits explosive plays on {o['explosive_rate']:.1%} of snaps; "
                    f"{team} allows {t['def_explosive_allowed']:.1%}.")
    return keys[:6]
