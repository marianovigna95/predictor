"""
STEP 9 — xG REALI da FotMob + risultati ufficiali delle partite giocate (stagione 2026/27).

Skarica la pagina calendario di FotMob (Serie A), prende tutte le partite giocate,
perognuna scarica la pagina partita e legge "Expected goals (xG)" dagli stats.
Salva:
  data/xg_fotmob_2627.csv   -> matchId,date,round,home,away,xgH,xgA,hg,ag
  data/matches_extra.csv    -> righe pronte per matches.csv (Date,HomeTeam,AwayTeam,FTHG,FTAG,HxG,AxG)
                              (solo le partite NON già presenti in matches.csv, es. giornata 10)

Uso:  python3 src/step9_fotmob_xg.py
"""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
LEAGUE_URL = "https://fotmob.com/leagues/55/fixtures"

NAME_MAP = {
    "Inter": "Inter", "Internazionale": "Inter", "AC Milan": "Milan", "Milan": "Milan",
    "AS Roma": "Roma", "Roma": "Roma", "SS Lazio": "Lazio", "Lazio": "Lazio",
    "SSC Napoli": "Napoli", "Napoli": "Napoli", "Atalanta": "Atalanta", "Juventus": "Juventus",
    "Fiorentina": "Fiorentina", "Bologna": "Bologna", "Torino": "Torino", "Udinese": "Udinese",
    "Monza": "Monza", "Genoa": "Genoa", "Lecce": "Lecce", "Parma": "Parma", "Cagliari": "Cagliari",
    "Sassuolo": "Sassuolo", "Venezia": "Venezia", "Frosinone": "Frosinone", "Como": "Como",
    "Hellas Verona": "Verona", "Empoli": "Empoli", "Cremonese": "Cremonese", "Pisa": "Pisa",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")


def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}


def match_xg(html):
    """Estrae (xgH, xgA) dalla pagina partita FotMob."""
    try:
        pp = next_data(html)["props"]["pageProps"]
        groups = pp["content"]["stats"]["Periods"]["All"]["stats"]
        for grp in groups:
            for s in grp["stats"]:
                if s.get("key") == "expected_goals":
                    raw = s.get("rawStats") or []
                    if len(raw) == 2 and raw[0] and raw[1]:
                        return float(raw[0]["value"]), float(raw[1]["value"])
    except Exception:
        pass
    return None, None


def player_xg(html):
    """Estrae xG e minuti di OGNI giocatore dalla pagina partita FotMob."""
    out = []
    try:
        ps = next_data(html)["props"]["pageProps"]["content"]["playerStats"]
        for pid, p in ps.items():
            xg = mins = sot = None
            for grp in p.get("stats", []):
                for name, s in grp.get("stats", {}).items():
                    k = s.get("key", "")
                    if k == "expected_goals":
                        xg = s["stat"].get("value")
                    if k == "minutes_played":
                        mins = s["stat"].get("value")
                    if k == "ShotsOnTarget":
                        sot = s["stat"].get("value")
            if xg is not None:
                out.append({"player": p.get("name", ""), "team": p.get("teamName", ""),
                            "xg": float(xg), "min": float(mins or 0),
                            "sot": float(sot or 0)})
    except Exception:
        pass
    return out


def main():
    print("⬇️  Scarico calendario FotMob Serie A...")
    league = next_data(get(LEAGUE_URL))
    matches = league["props"]["pageProps"]["fixtures"]["allMatches"]
    played = [m for m in matches if m.get("status", {}).get("finished")]
    print(f"📅 Partite giocate trovate: {len(played)} di {len(matches)}")

    # calendario COMPLETO della stagione (giocate + da giocare) → fixtures automatici
    def round_num(m):
        try:
            return int(m.get("round"))
        except Exception:
            mm = re.search(r"\d+", str(m.get("roundName", "")))
            return int(mm.group(0)) if mm else 0
    fx = pd.DataFrame([{
        "matchday": round_num(m),
        "date": m["status"]["utcTime"][:10],
        "home": NAME_MAP.get(m["home"]["name"], m["home"]["name"]),
        "away": NAME_MAP.get(m["away"]["name"], m["away"]["name"]),
    } for m in matches])
    fx = fx.sort_values(["matchday", "date"]).drop_duplicates(subset=["matchday", "home", "away"])
    fx.to_csv(DATA / "fixtures_fotmob.csv", index=False)
    print(f"💾 Calendario completo salvato: {DATA/'fixtures_fotmob.csv'} ({len(fx)} partite, giornate 1-{fx['matchday'].max()})")

    def fetch(m):
        try:
            url = "https://fotmob.com" + m["pageUrl"].split("#")[0]
            html = get(url)
            xh, xa = match_xg(html)
            players = player_xg(html)
            return {
                "matchId": m["id"],
                "date": m["status"]["utcTime"][:10],
                "round": m.get("roundName", ""),
                "home": m["home"]["name"], "away": m["away"]["name"],
                "xgH": xh, "xgA": xa,
                "scoreStr": m["status"].get("scoreStr", ""),
                "players": players,
            }
        except Exception as e:
            return {"matchId": m["id"], "error": str(e), "players": []}

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(fetch, played))
    df = pd.DataFrame(rows)
    df = df[~df.get("error").notna()] if "error" in df else df
    ok = df[df["xgH"].notna()]
    print(f"✅ xG estratti per {len(ok)}/{len(df)} partite")

    # punteggi dallo scoreStr ("2 - 1")
    def parse_score(s):
        try:
            a, b = s.replace("–", "-").split("-")
            return int(a.strip()), int(b.strip())
        except Exception:
            return None, None
    hg, ag = zip(*ok["scoreStr"].map(parse_score))
    ok = ok.assign(hg=hg, ag=ag)

    # mapping nomi FotMob -> nomi football-data
    name_map = {
        "Inter": "Inter", "AC Milan": "Milan", "Milan": "Milan", "AS Roma": "Roma", "Roma": "Roma",
        "SS Lazio": "Lazio", "Lazio": "Lazio", "SSC Napoli": "Napoli", "Napoli": "Napoli",
        "Atalanta": "Atalanta", "Juventus": "Juventus", "Fiorentina": "Fiorentina",
        "Bologna": "Bologna", "Torino": "Torino", "Udinese": "Udinese", "Monza": "Monza",
        "Genoa": "Genoa", "Lecce": "Lecce", "Parma": "Parma", "Cagliari": "Cagliari",
        "Sassuolo": "Sassuolo", "Venezia": "Venezia", "Frosinone": "Frosinone", "Como": "Como",
        "Hellas Verona": "Verona", "Empoli": "Empoli", "Cremonese": "Cremonese", "Pisa": "Pisa",
    }
    ok["home"] = ok["home"].map(lambda x: name_map.get(x, x))
    ok["away"] = ok["away"].map(lambda x: name_map.get(x, x))
    ok = ok.sort_values("date")
    ok.to_csv(DATA / "xg_fotmob_2627.csv", index=False)
    print(f"💾 Salvato: {DATA/'xg_fotmob_2627.csv'}")

    # matches_extra.csv: partite FotMob non ancora in matches.csv (es. g10)
    existing = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    ex_keys = set(zip(existing["Date"].dt.strftime("%Y-%m-%d"), existing["HomeTeam"], existing["AwayTeam"]))
    extra = ok[~ok.apply(lambda r: (r["date"], r["home"], r["away"]) in ex_keys, axis=1)]
    extra_out = pd.DataFrame({
        "Date": pd.to_datetime(extra["date"]), "HomeTeam": extra["home"], "AwayTeam": extra["away"],
        "FTHG": extra["hg"], "FTAG": extra["ag"], "HxG": extra["xgH"], "AxG": extra["xgA"],
    })
    extra_out.to_csv(DATA / "matches_extra.csv", index=False)
    print(f"💾 Salvato: {DATA/'matches_extra.csv'} ({len(extra_out)} partite nuove, es. g10)")
    # xG per giocatore (per penalità assenze precise)
    prows = []
    for r in rows:
        for p in r.get("players", []):
            prows.append({"matchId": r["matchId"], "date": r["date"],
                          "team": NAME_MAP.get(p["team"], p["team"]),
                          "player": p["player"], "xg": p["xg"], "min": p["min"],
                          "sot": p.get("sot", 0)})
    pdf = pd.DataFrame(prows)
    if len(pdf):
        pdf = pdf.sort_values("date")
        pdf.to_csv(DATA / "player_xg_fotmob.csv", index=False)
        print(f"💾 Salvato: {DATA/'player_xg_fotmob.csv'} ({len(pdf)} righe giocatore-partita)")

    g10 = extra_out[extra_out["Date"] >= "2026-10-31"]
    if len(g10):
        print("\n⚽ Risultati giornata 10 (fonte FotMob scoreStr):")
        print(g10[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HxG", "AxG"]].to_string(index=False))


if __name__ == "__main__":
    main()
