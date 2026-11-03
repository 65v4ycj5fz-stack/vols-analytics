"""Game-time weather from Open-Meteo (free, no key; CC BY 4.0, attribution required).

* Historical: ERA5-based archive API, used to fit weather effects on scoring.
* Upcoming: forecast API (up to 16 days out).
Venues playing on the same date are batched into one request (Open-Meteo accepts
comma-separated coordinates); one-day ranges keep the request weight low on the free tier.
"""

from __future__ import annotations

import pandas as pd

from pipeline.cfbd import CFBDClient, REPO_ROOT

ARCHIVE = "https://archive-api.open-meteo.com/v1"
FORECAST = "https://api.open-meteo.com/v1"
HOURLY = "temperature_2m,wind_speed_10m,precipitation"
BATCH = 20
GAME_HOURS = 3  # average conditions over kickoff hour + next 2 hours
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


def client(kind: str, max_calls: int = 800, offline: bool = False) -> CFBDClient:
    return CFBDClient(api_key=None, send_auth=False, base_url=ARCHIVE if kind == "archive" else FORECAST,
                      cache_dir=REPO_ROOT / "data" / "cache" / "openmeteo", max_calls=max_calls,
                      offline=offline, min_interval_s=2.5)  # free tier: ~600 location-calls/min


def _params(lat: list[float], lon: list[float]) -> dict:
    return {"latitude": ",".join(f"{x:.4f}" for x in lat), "longitude": ",".join(f"{x:.4f}" for x in lon),
            "hourly": HOURLY, "wind_speed_unit": "mph", "temperature_unit": "fahrenheit", "timezone": "GMT"}


def _hourly_frame(resp: list[dict] | dict, venue_ids: list[int]) -> pd.DataFrame:
    resp = resp if isinstance(resp, list) else [resp]
    frames = []
    for vid, r in zip(venue_ids, resp):
        h = r["hourly"]
        frames.append(pd.DataFrame({"venue_id": vid, "time": pd.to_datetime(h["time"], utc=True),
                                    "temp_f": h["temperature_2m"], "wind_mph": h["wind_speed_10m"],
                                    "precip_mm": h["precipitation"]}))
    return pd.concat(frames, ignore_index=True)


def game_weather(games: pd.DataFrame, kind: str, om: CFBDClient, ttl_hours: float | None = None) -> pd.DataFrame:
    """Weather per game. ``games`` needs game_id, start_date, venue_id, lat, lon (outdoor games only)."""
    g = games.dropna(subset=["lat", "lon"]).copy()
    if g.empty:
        return pd.DataFrame(columns=["game_id", "temp_f", "wind_mph", "precip_mm"])
    g["kick"] = g["start_date"].dt.floor("h")
    out = []
    groups = [("all", g)] if kind == "forecast" else list(g.groupby(g["kick"].dt.strftime("%Y-%m-%d")))
    for _, sg in groups:
        venues = sg.drop_duplicates("venue_id")[["venue_id", "lat", "lon"]]
        start = sg["kick"].min().strftime("%Y-%m-%d")
        end = (sg["kick"].max() + pd.Timedelta(hours=GAME_HOURS)).strftime("%Y-%m-%d")
        for i in range(0, len(venues), BATCH):
            chunk = venues.iloc[i:i + BATCH]
            params = _params(chunk["lat"].tolist(), chunk["lon"].tolist())
            if kind == "archive":
                params.update(start_date=start, end_date=end)
                resp = om.get("/archive", params, ttl_hours=ttl_hours)
            else:
                params.update(forecast_days=16)
                resp = om.get("/forecast", params, ttl_hours=ttl_hours)
            out.append(_hourly_frame(resp, chunk["venue_id"].tolist()))
    hourly = pd.concat(out, ignore_index=True)
    rows = []
    for h in range(GAME_HOURS):
        m = g[["game_id", "venue_id", "kick"]].assign(time=g["kick"] + pd.Timedelta(hours=h))
        rows.append(m.merge(hourly, on=["venue_id", "time"], how="inner"))
    w = pd.concat(rows).groupby("game_id")[["temp_f", "wind_mph", "precip_mm"]].mean().reset_index()
    return w
