"""Pregame context features for the adjustments layer and the totals model (no lookahead).

All "season so far" quantities use only games that started before the game in question.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from model.features import EffParams, adjusted_pregame

TURNOVER_PRIOR_GAMES = 4.0  # shrinks early-season turnover margins toward 0
PACE_PRIOR_GAMES = 3.0
FORM_HALF_LIFE = 3.0        # weeks, for the recent-form rating


def team_rows(games: pd.DataFrame) -> pd.DataFrame:
    done = games[games["completed"]]
    parts = []
    for side, opp in (("home", "away"), ("away", "home")):
        parts.append(pd.DataFrame({"game_id": done["game_id"], "season": done["season"],
                                   "start_date": done["start_date"], "team": done[f"{side}_team"],
                                   "opponent": done[f"{opp}_team"]}))
    return pd.concat(parts, ignore_index=True)


def turnover_margin_pregame(games: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """Pregame shrunk turnover margin per game (takeaways - giveaways) for each team in each game."""
    tr = team_rows(games)
    tos = box[["game_id", "team", "turnovers"]]
    tr = tr.merge(tos, on=["game_id", "team"], how="inner").merge(
        tos.rename(columns={"team": "opponent", "turnovers": "opp_turnovers"}), on=["game_id", "opponent"], how="inner")
    tr["to_margin"] = tr["opp_turnovers"] - tr["turnovers"]
    return _pregame_for_all(games, tr, "to_pre", 0.0, TURNOVER_PRIOR_GAMES, "to_margin",
                            seasons=set(box["season"]) if "season" in box else None)


def pace_pregame(games: pd.DataFrame, adv: pd.DataFrame) -> pd.DataFrame:
    """Pregame shrunk average total plays (both offenses) in each team's games."""
    tr = team_rows(games)
    plays = adv[["game_id", "team", "off_plays"]]
    tr = tr.merge(plays, on=["game_id", "team"]).merge(
        plays.rename(columns={"team": "opponent", "off_plays": "opp_plays"}), on=["game_id", "opponent"])
    tr["game_plays"] = tr["off_plays"] + tr["opp_plays"]
    league = float(tr["game_plays"].mean())
    return _pregame_for_all(games, tr, "pace_pre", league, PACE_PRIOR_GAMES, "game_plays")


def _pregame_for_all(games: pd.DataFrame, tr: pd.DataFrame, col: str, prior: float, k: float, raw: str,
                     seasons: set | None = None) -> pd.DataFrame:
    """Shrunk mean of ``raw`` over each team's earlier completed games that season, for every
    (game, team) including unplayed games: (sum + k * prior) / (n + k)."""
    out = []
    for side in ("home", "away"):
        x = games[["game_id", "season", "start_date", f"{side}_team"]].rename(columns={f"{side}_team": "team"})
        done = tr[["team", "season", "start_date", raw]].sort_values("start_date")
        x = x.sort_values("start_date")
        merged = pd.merge_asof(x, done.assign(cum=done.groupby(["team", "season"])[raw].cumsum(),
                                              n=done.groupby(["team", "season"]).cumcount() + 1),
                               on="start_date", by=["team", "season"], allow_exact_matches=False)
        val = (merged["cum"].fillna(0) + k * prior) / (merged["n"].fillna(0) + k)
        if seasons is not None:
            val = val.where(merged["season"].isin(seasons))
        out.append(pd.DataFrame({"game_id": merged["game_id"], "side": side, col: val.to_numpy()}))
    return pd.concat(out).pivot_table(index="game_id", columns="side", values=col, aggfunc="first").add_prefix(f"{col}_")


def add_context(f: pd.DataFrame, games: pd.DataFrame, adv: pd.DataFrame, ctx: pd.DataFrame,
                box: pd.DataFrame, weather: pd.DataFrame, eff_p: EffParams) -> pd.DataFrame:
    """Attach adjustment and totals features to a game-feature frame ``f`` (home perspective)."""
    f = f.merge(ctx[["game_id", "dome", "home_travel_km", "away_travel_km", "home_rest_days", "away_rest_days"]],
                on="game_id", how="left")
    rest_h = f["home_rest_days"].round().fillna(7).clip(upper=21)
    rest_a = f["away_rest_days"].round().fillna(7).clip(upper=21)
    f["rest_diff"] = (rest_h - rest_a).clip(-7, 7)
    f["travel_diff"] = (f["away_travel_km"].fillna(0) - f["home_travel_km"].fillna(0)) / 1000.0

    to = turnover_margin_pregame(games, box)
    f = f.join(to, on="game_id")
    f["to_diff"] = f["to_pre_home"] - f["to_pre_away"]

    pace = pace_pregame(games, adv)
    f = f.join(pace, on="game_id")
    f["pace"] = (f["pace_pre_home"] + f["pace_pre_away"]) / 2

    f["epa_sum"] = f["home_adj_off"] + f["away_adj_def"] + f["away_adj_off"] + f["home_adj_def"]

    form = adjusted_pregame(games, adv, EffParams(**{**eff_p.__dict__, "half_life": FORM_HALF_LIFE}))
    form = form.set_index(["game_id", "team"])
    for side in ("home", "away"):
        a = form.reindex(pd.MultiIndex.from_arrays([f["game_id"], f[f"{side}_team"]]))
        f[f"{side}_form_net"] = (a["adj_off"] - a["adj_def"]).to_numpy(dtype=float)
    flat_net = (f["home_adj_off"] - f["home_adj_def"]) - (f["away_adj_off"] - f["away_adj_def"])
    f["form_edge"] = (f["home_form_net"] - f["away_form_net"]) - flat_net  # EPA/play, recent minus flat

    w = weather.drop_duplicates("game_id", keep="last").set_index("game_id")
    for c in ("temp_f", "wind_mph", "precip_mm"):
        f[c] = f["game_id"].map(w[c]) if c in w else np.nan
    f["weather_kind"] = f["game_id"].map(w["kind"]) if "kind" in w else None
    indoor = f["dome"].fillna(False).astype(bool)
    f.loc[indoor, ["wind_mph", "precip_mm"]] = 0.0
    f.loc[indoor, "temp_f"] = 70.0
    f["wind_over_10"] = (f["wind_mph"] - 10).clip(lower=0)
    f["cold"] = (f["temp_f"] < 40).astype(float).where(f["temp_f"].notna())
    return f
