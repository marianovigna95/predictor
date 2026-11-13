#!/usr/bin/env python3
"""step30_weather.py — coordinate squadre (ESPN core API, gratis) + meteo (open-meteo, gratis, no key).

Output in data/:
  team_coords.csv   team,city,lat,lon        (geocoding Nominatim, cache)
  weather_hist.csv  city,date,factor         (open-meteo ARCHIVE 2026-08-01 -> oggi, per validazione)
  weather_fore.csv  city,date,factor         (open-meteo FORECAST oggi -> +16gg, per le partite future)

factor < 1 = meteo avverso (pioggia/vento/freddo/caldo) -> meno gol attesi.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ESPN_SLUGS = {
    "Serie A": ("ita.1", "Italy"), "Premier League": ("eng.1", "United Kingdom"),
    "LaLiga": ("esp.1", "Spain"), "Bundesliga": ("ger.1", "Germany"), "Ligue 1": ("fra.1", "France"),
    "Serie B": ("ita.2", "Italy"), "Championship": ("eng.2", "United Kingdom"),
    "LaLiga 2": ("esp.2", "Spain"), "Bundesliga 2": ("ger.2", "Germany"), "Ligue 2": ("fra.2", "France"),
    "Eredivisie": ("ned.1", "Netherlands"), "Primeira Liga": ("por.1", "Portugal"),
    "Süper Lig": ("tur.1", "Turkey"),
    "Champions League": ("uefa.champions", "Europe"), "Europa League": ("uefa.europa", "Europe"),
    "Conference League": ("uefa.europa.conf", "Europe"),
}
UA = {"User-Agent": "football-predictor-analysis/1.0 (educational, no commercial use)"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.load(f)


def fetch_team_coords(force=False):
    """team -> (city, lat, lon). Cache in data/team_coords.csv."""
    out = DATA / "team_coords.csv"
    coords = {}
    if out.exists() and not force:
        for _, r in pd.read_csv(out).iterrows():
            coords[r["team"]] = (r["city"], r.get("lat"), r.get("lon"))
    for league, (slug, country) in ESPN_SLUGS.items():
        try:
            d = _get(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{slug}/teams?limit=100&lang=en&region=us")
            for it in d.get("items", []):
                ref = (it.get("$ref") or "").replace("http://", "https://")
                if not ref:
                    continue
                try:
                    it = _get(ref, timeout=10)
                except Exception:
                    continue
                name, tid = it.get("displayName"), it.get("id")
                if not name or not tid:
                    continue
                if name in coords and coords[name][1] is not None and not (isinstance(coords[name][1], float) and pd.isna(coords[name][1])):
                    continue
                city = ""
                vid = (it.get("venue") or {}).get("id")
                if vid:
                    try:
                        v = _get(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{slug}/venues/{vid}?lang=en&region=us", timeout=10)
                        city = (v.get("address") or {}).get("city") or ""
                    except Exception:
                        pass
                if not city:
                    city = it.get("location") or ""
                coords[name] = (city, None, None)
                time.sleep(0.05)
        except Exception as e:
            print(f"  ⚠️ ESPN teams {league}: {e}")
    # geocode città mancanti (Nominatim, 1 req/s, cache)
    need = sorted({c for (c, la, lo) in coords.values() if c and (la is None or (isinstance(la, float) and pd.isna(la)))})
    geo = {}
    if out.exists():
        for _, r in pd.read_csv(out).iterrows():
            if pd.notna(r.get("lat")):
                geo[r["city"]] = (float(r["lat"]), float(r["lon"]))
    for c in need:
        if c in geo:
            continue
        try:
            q = urllib.parse.quote(c)
            d = _get(f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1", timeout=15)
            if d:
                geo[c] = (float(d[0]["lat"]), float(d[0]["lon"]))
            time.sleep(1.1)
        except Exception:
            pass
    rows = []
    for team, (city, la, lo) in coords.items():
        if city in geo:
            la, lo = geo[city]
        rows.append({"team": team, "city": city, "lat": la, "lon": lo})
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"📍 team_coords.csv: {len(rows)} squadre, {sum(1 for r in rows if r['lat'] is not None and not (isinstance(r['lat'], float) and pd.isna(r['lat'])))} geocodificate")
    return out


def weather_factor(rain, wind, temp):
    """Meteo avverso -> meno gol. Valori da open-meteo daily."""
    f = 1.0
    if rain is not None:
        if rain >= 10:
            f *= 0.90
        elif rain >= 3:
            f *= 0.95
    if wind is not None and wind >= 50:
        f *= 0.95
    if temp is not None:
        if temp <= 0:
            f *= 0.97
        elif temp >= 32:
            f *= 0.96
    return round(f, 4)


def _fetch_meteo(cities_geo, start, end, archive):
    """Ritorna {(city, 'YYYY-MM-DD'): factor}."""
    out = {}
    for city, (lat, lon) in cities_geo.items():
        try:
            base = ("https://archive-api.open-meteo.com/v1/archive" if archive
                    else "https://api.open-meteo.com/v1/forecast")
            url = (f"{base}?latitude={lat}&longitude={lon}"
                   f"&daily=precipitation_sum,wind_speed_10m_max,temperature_2m_mean"
                   f"&start_date={start}&end_date={end}&timezone=Europe%2FRome")
            d = _get(url)
            daily = d.get("daily", {})
            dates = daily.get("time", [])
            for i, dt in enumerate(dates):
                rain = daily.get("precipitation_sum", [None] * len(dates))[i]
                wind = daily.get("wind_speed_10m_max", [None] * len(dates))[i]
                temp = daily.get("temperature_2m_mean", [None] * len(dates))[i]
                out[(city, dt)] = weather_factor(rain, wind, temp)
            time.sleep(0.15)
        except Exception as e:
            print(f"  ⚠️ meteo {city}: {e}")
    return out


def fetch_weather(hist_start="2026-08-01", fore_days=15):
    """Scrive weather_hist.csv (archive) e weather_fore.csv (forecast). Ritorna i dizionari."""
    fetch_team_coords()
    cd = pd.read_csv(DATA / "team_coords.csv")
    geo = {r["city"]: (float(r["lat"]), float(r["lon"])) for _, r in cd.iterrows()
           if r["city"] and pd.notna(r.get("lat")) and pd.notna(r.get("lon"))}
    today = pd.Timestamp.now(tz="Europe/Rome").normalize().date()
    hist_end = (today - pd.Timedelta(days=1)).isoformat()
    fore_end = (today + pd.Timedelta(days=fore_days)).isoformat()
    wh = _fetch_meteo(geo, hist_start, hist_end, archive=True)
    wf = _fetch_meteo(geo, today.isoformat(), fore_end, archive=False)
    pd.DataFrame([{"city": c, "date": d, "factor": f} for (c, d), f in wh.items()]).to_csv(DATA / "weather_hist.csv", index=False)
    pd.DataFrame([{"city": c, "date": d, "factor": f} for (c, d), f in wf.items()]).to_csv(DATA / "weather_fore.csv", index=False)
    print(f"🌦️ meteo: {len(wh)} giorni storici, {len(wf)} giorni forecast ({len(geo)} città)")
    return wh, wf


if __name__ == "__main__":
    fetch_weather()
