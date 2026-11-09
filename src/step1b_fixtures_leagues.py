"""
STEP 1b — Calendario (fixtures) di TUTTE le top-5 leghe da FotMob, con giornata (round).

Uso:  python3 src/step1b_fixtures_leagues.py
Output: data/fixtures_leagues.csv  -> league, matchday, date, home, away, played, hg, ag
        (nomi squadre normalizzati ai nomi football-data.co.uk per poter fare join con matches.csv)
"""
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
ROME = ZoneInfo("Europe/Rome")

# code football-data -> (fotmob league id, nome lega)
LEAGUES = {
    "I1": (55, "Serie A"),
    "E0": (47, "Premier League"),
    "SP1": (87, "LaLiga"),
    "D1": (54, "Bundesliga"),
    "F1": (53, "Ligue 1"),
    # 🏆 COPPE EUROPEE (FotMob id verificati 03/11/2026): UCL=42, UEL=73, UECL=10216
    "UCL": (42, "Champions League"),
    "UEL": (73, "Europa League"),
    "UECL": (10216, "Conference League"),
    # 🆕 LEGHE EXTRA (FotMob id da sitemap ufficiale 04/11/2026; div football-data)
    "I2": (86, "Serie B"),
    "E1": (48, "Championship"),  # 123=scozzese, 8870=NZ, 48=EFL inglese
    "N1": (57, "Eredivisie"),
    "P1": (61, "Primeira Liga"),
    "T1": (71, "Süper Lig"),
    "D2": (146, "Bundesliga 2"),
    "SP2": (140, "LaLiga 2"),  # 9122 = Segunda Uruguay! laliga2 = 140
    "F2": (110, "Ligue 2"),
}

# fotmob name -> football-data name (per lega 2026/27)
NAME_MAP = {
    "E0": {
        "AFC Bournemouth": "Bournemouth", "Brighton & Hove Albion": "Brighton",
        "Coventry City": "Coventry", "Hull City": "Hull", "Ipswich Town": "Ipswich",
        "Leeds United": "Leeds", "Manchester City": "Man City", "Manchester United": "Man United",
        "Newcastle United": "Newcastle", "Nottingham Forest": "Nott'm Forest",
        "Tottenham Hotspur": "Tottenham",
    },
    "SP1": {
        "Athletic Club": "Ath Bilbao", "Atlético Madrid": "Ath Madrid",
        "Celta Vigo": "Celta", "Deportivo A Coruña": "La Coruna",
        "Deportivo Alavés": "Alaves", "Espanyol": "Espanol", "Málaga": "Malaga",
        "Racing Santander": "Santander", "Rayo Vallecano": "Vallecano",
        "Real Betis": "Betis", "Real Sociedad": "Sociedad",
    },
    "D1": {
        "1. FC Köln": "FC Koln", "Bayer Leverkusen": "Leverkusen",
        "Bayern München": "Bayern Munich", "Borussia Dortmund": "Dortmund",
        "Borussia Mönchengladbach": "M'gladbach", "Eintracht Frankfurt": "Ein Frankfurt",
        "Freiburg": "Freiburg", "Hamburger SV": "Hamburg", "Mainz 05": "Mainz",
        "VfB Stuttgart": "Stuttgart",
    },
    "F1": {
        "Paris Saint-Germain": "Paris SG",
    },
    "I1": {},
    # nomi comuni coppe europee -> nomi football-data delle leghe nazionali (per seminare l'Elo)
    "UCL": {"Paris Saint-Germain": "Paris SG", "Bayern München": "Bayern Munich", "Atlético Madrid": "Ath Madrid",
            "Borussia Dortmund": "Dortmund", "1. FC Köln": "FC Koln", "Bayer Leverkusen": "Leverkusen",
            "Borussia Mönchengladbach": "M'gladbach", "Eintracht Frankfurt": "Ein Frankfurt", "Hamburger SV": "Hamburg",
            "Mainz 05": "Mainz", "VfB Stuttgart": "Stuttgart", "Manchester City": "Man City", "Manchester United": "Man United",
            "Newcastle United": "Newcastle", "Nottingham Forest": "Nott'm Forest", "Tottenham Hotspur": "Tottenham",
            "Leeds United": "Leeds", "AFC Bournemouth": "Bournemouth", "Brighton & Hove Albion": "Brighton",
            "Athletic Club": "Ath Bilbao", "Celta Vigo": "Celta", "Deportivo Alavés": "Alaves", "Rayo Vallecano": "Vallecano",
            "Real Betis": "Betis", "Real Sociedad": "Sociedad", "Deportivo A Coruña": "La Coruna", "Málaga": "Malaga",
            "Racing Santander": "Santander", "Espanyol": "Espanol"},
    "UEL": {},
    "UECL": {},
    "I2": {"Hellas Verona": "Verona", "LR Vicenza": "Vicenza", "Südtirol": "Sudtirol"},
    "E1": {"Queens Park Rangers": "QPR", "Wolverhampton Wanderers": "Wolves"},
    "N1": {"ADO Den Haag": "Den Haag", "FC Groningen": "Groningen", "FC Twente": "Twente", "FC Utrecht": "Utrecht",
            "NEC Nijmegen": "Nijmegen", "PEC Zwolle": "Zwolle", "SC Heerenveen": "Heerenveen", "Fortuna Sittard": "For Sittard"},
    "P1": {"Braga": "Sp Braga", "FC Porto": "Porto", "Sporting CP": "Sp Lisbon", "Estrela da Amadora": "Estrela",
            "Académico Viseu": "Academico Viseu", "Famalicão": "Famalicao", "Marítimo": "Maritimo",
            "Vitória de Guimarães": "Guimaraes", "Casa Pia AC": "Casa Pia"},
    "T1": {"Beşiktaş": "Besiktas", "Fenerbahçe": "Fenerbahce", "Kasımpaşa": "Kasimpasa", "Başakşehir": "Buyuksehyr",
            "Amed Sportif": "Amedspor", "Eyüpspor": "Eyupspor", "Göztepe": "Goztep", "Gençlerbirliği": "Genclerbirligi",
            "Gaziantep FK": "Gaziantep", "Erzurumspor FK": "Erzurumspor", "Çorum FK": "Corum"},
    "D2": {"1. FC Nürnberg": "Nurnberg", "Arminia Bielefeld": "Bielefeld", "Dynamo Dresden": "Dresden",
            "Eintracht Braunschweig": "Braunschweig", "Energie Cottbus": "Cottbus", "FC Heidenheim": "Heidenheim",
            "Greuther Fürth": "Greuther Furth", "Hannover 96": "Hannover", "Hertha BSC": "Hertha",
            "Karlsruher SC": "Karlsruhe", "St. Pauli": "St Pauli", "VfL Osnabrück": "Osnabruck"},
    "SP2": {"Celta Fortuna": "Celta B", "Sporting Gijón": "Sp Gijon"},
    "F2": {"Annecy FC": "Annecy", "Clermont Foot": "Clermont", "Pau": "Pau FC", "Saint-Étienne": "St Etienne"},
}
# per UEL/UECL applico la stessa mappa UCL (nomi uguali) a runtime
NAME_MAP["UEL"] = NAME_MAP["UCL"]
NAME_MAP["UECL"] = NAME_MAP["UCL"]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}


def norm(code, name):
    return NAME_MAP.get(code, {}).get(name, name)


def main():
    rows = []
    for code, (fid, lname) in LEAGUES.items():
        d = next_data(get(f"https://fotmob.com/leagues/{fid}/fixtures"))
        allm = d["props"]["pageProps"]["fixtures"]["allMatches"]
        for m in allm:
            utc = m["status"].get("utcTime")
            if not utc:
                continue
            dt = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(ROME)
            finished = bool(m["status"].get("finished"))
            hg = ag = ""
            sc = m["status"].get("scoreStr") or ""
            if finished and " - " in sc:
                a, b = sc.split(" - ")
                hg, ag = a.strip(), b.strip()
            rn = str(m["roundName"])
            rows.append({
                "league": lname, "div": code, "matchday": int(rn) if rn.isdigit() else 0,
                "date": dt.strftime("%Y-%m-%d %H:%M"),
                "home": norm(code, m["home"]["name"]), "away": norm(code, m["away"]["name"]),
                "played": finished, "hg": hg, "ag": ag,
            })
        print(f"  {lname}: {len(allm)} partite dal calendario FotMob")
    df = pd.DataFrame(rows).sort_values(["date", "league"]).reset_index(drop=True)
    out = DATA / "fixtures_leagues.csv"
    df.to_csv(out, index=False)
    print(f"\n✅ Salvato: {out} ({len(df)} righe)")
    nxt = df[~df.played].groupby("league")["matchday"].min()
    print("📅 Prossima giornata per lega:")
    print(nxt.to_string())


if __name__ == "__main__":
    main()
