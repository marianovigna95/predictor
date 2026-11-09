"""
STEP 12 — xG REALI Understat per TUTTE le stagioni (API pubblica getLeagueData).

Scarga https://understat.com/getLeagueData/Serie_A/{stagione}/ per 2022-2026:
  - dates: tutte le partite con gol e xG (home/away)
  - players: xG di ogni giocatore per stagione
Salva:
  data/understat_xg.csv      -> season,date,home,away,hg,ag,xgH,xgA   (nomi team in formato football-data)
  data/understat_players.csv -> season,player,team,xG,games,time

Uso:  python3 src/step12_understat_xg.py
"""
import json
import urllib.request
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "X-Requested-With": "XMLHttpRequest",
      "Referer": "https://understat.com/"}

# nomi Understat -> nomi football-data (quelli usati in matches.csv)
NAME_MAP = {
    "AC Milan": "Milan", "AS Roma": "Roma", "SS Lazio": "Lazio", "SSC Napoli": "Napoli",
    "Parma Calcio 1913": "Parma", "Hellas Verona": "Verona", "Internazionale": "Inter",
    "FROSINONE": "Frosinone", "Como 1907": "Como", "US Cremonese": "Cremonese",
    "Spezia Calcio": "Spezia", "UC Sampdoria": "Sampdoria", "US Salernitana 1919": "Salernitana",
    "AC Pisa": "Pisa", "EMPOLI": "Empoli",
}


def get_json(url):
    import gzip
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def main():
    all_matches, all_players = [], []
    for season in [2022, 2023, 2024, 2025, 2026]:
        url = f"https://understat.com/getLeagueData/Serie_A/{season}/"
        try:
            d = get_json(url)
        except Exception as e:
            print(f"⚠️  stagione {season}: errore {e}")
            continue
        n = 0
        for m in d.get("dates", []):
            if not m.get("isResult"):
                continue
            all_matches.append({
                "season": f"{season}/{season+1}",
                "date": m["datetime"][:10],
                "home": NAME_MAP.get(m["h"]["title"], m["h"]["title"]),
                "away": NAME_MAP.get(m["a"]["title"], m["a"]["title"]),
                "hg": m["goals"]["h"], "ag": m["goals"]["a"],
                "xgH": round(float(m["xG"]["h"]), 3), "xgA": round(float(m["xG"]["a"]), 3),
            })
            n += 1
        for p in d.get("players", []):
            all_players.append({
                "season": f"{season}/{season+1}",
                "player": p["player_name"],
                "team": NAME_MAP.get(p["team_title"], p["team_title"]),
                "xG": round(float(p["xG"]), 2), "games": p["games"], "time": p["time"],
                "shots": p.get("shots", 0), "goals": p.get("goals", 0),
                "position": p.get("position", ""),
                "yellow": p.get("yellow_cards", 0), "red": p.get("red_cards", 0),
            })
        print(f"✅ stagione {season}/{season+1}: {n} partite con xG, {len(d.get('players', []))} giocatori")

    mdf = pd.DataFrame(all_matches).sort_values("date")
    mdf.to_csv(DATA / "understat_xg.csv", index=False)
    pdf = pd.DataFrame(all_players)
    pdf.to_csv(DATA / "understat_players.csv", index=False)
    print(f"\n💾 Salvato: {DATA/'understat_xg.csv'} ({len(mdf)} partite)")
    print(f"💾 Salvato: {DATA/'understat_players.csv'} ({len(pdf)} righe giocatore-stagione)")
    # copertura sulle nostre 5 stagioni
    have = set(zip(mdf["date"], mdf["home"], mdf["away"]))
    mc = pd.read_csv(DATA / "matches.csv")
    mc["d"] = pd.to_datetime(mc["Date"]).dt.strftime("%Y-%m-%d")
    keys = list(zip(mc["d"], mc["HomeTeam"], mc["AwayTeam"]))
    cov = sum(k in have for k in keys)
    print(f"📊 Copertura xG Understat su matches.csv: {cov}/{len(keys)} partite ({cov/len(keys)*100:.0f}%)")


if __name__ == "__main__":
    main()
