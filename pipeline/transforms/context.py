"""Per-game context: venue, dome, travel distance, rest days (all derived from CFBD games + venues)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.schemas import VenueRaw

EARTH_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def venues_frame(venues: list[VenueRaw]) -> pd.DataFrame:
    return pd.DataFrame([{"venue_id": v.id, "venue_name": v.name, "dome": bool(v.dome),
                          "lat": v.latitude, "lon": v.longitude} for v in venues])


def home_venues(games: pd.DataFrame) -> pd.DataFrame:
    """Each team-season's usual home venue: the venue it hosted most non-neutral games at.

    Teams with no home game that season fall back to their most recent known home venue.
    """
    h = games[~games["neutral_site"] & games["venue_id"].notna()]
    counts = h.groupby(["home_team", "season", "venue_id"]).size().rename("n").reset_index()
    best = counts.sort_values("n").drop_duplicates(["home_team", "season"], keep="last")
    best = best.rename(columns={"home_team": "team", "venue_id": "home_venue_id"})[["team", "season", "home_venue_id"]]
    teams = pd.unique(pd.concat([games["home_team"], games["away_team"]]))
    grid = pd.MultiIndex.from_product([teams, sorted(games["season"].unique())], names=["team", "season"]).to_frame(index=False)
    out = grid.merge(best, on=["team", "season"], how="left").sort_values(["team", "season"])
    out["home_venue_id"] = out.groupby("team")["home_venue_id"].transform(lambda s: s.ffill().bfill())
    return out


def rest_days(games: pd.DataFrame) -> pd.DataFrame:
    """Days since each team's previous game (any opponent) in the same season; NaN for a season opener."""
    rows = pd.concat([
        games[["game_id", "season", "start_date", "home_team"]].rename(columns={"home_team": "team"}),
        games[["game_id", "season", "start_date", "away_team"]].rename(columns={"away_team": "team"}),
    ]).sort_values(["team", "start_date"])
    prev = rows.groupby(["team", "season"])["start_date"].shift(1)
    rows["rest_days"] = (rows["start_date"] - prev).dt.total_seconds() / 86400
    return rows[["game_id", "team", "rest_days"]]


def game_context(games: pd.DataFrame, venues: pd.DataFrame) -> pd.DataFrame:
    """One row per game: dome flag, venue coordinates, each team's travel (km) and rest days."""
    g = games[["game_id", "season", "start_date", "home_team", "away_team", "venue_id", "neutral_site"]].copy()
    g = g.merge(venues[["venue_id", "dome", "lat", "lon"]], on="venue_id", how="left")
    hv = home_venues(games).merge(venues[["venue_id", "lat", "lon"]].rename(
        columns={"venue_id": "home_venue_id", "lat": "hlat", "lon": "hlon"}), on="home_venue_id", how="left")
    rest = rest_days(games)
    for side in ("home", "away"):
        x = g[["game_id", "season", f"{side}_team"]].rename(columns={f"{side}_team": "team"})
        x = x.merge(hv, on=["team", "season"], how="left")
        g[f"{side}_travel_km"] = haversine_km(x["hlat"], x["hlon"], g["lat"], g["lon"])
        g[f"{side}_rest_days"] = g[["game_id"]].assign(team=g[f"{side}_team"]).merge(
            rest, on=["game_id", "team"], how="left")["rest_days"].to_numpy()
    g["dome"] = g["dome"].fillna(False).astype(bool)
    return g
