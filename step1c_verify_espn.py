"""
STEP 1c — Verifica incrociata dei RISULTATI con la scoreboard pubblica ESPN (gratis, senza chiave).

Uso:  python3 src/step1c_verify_espn.py [YYYY-MM-DD]
Confronta le partite "played" di data/fixtures_leagues.csv con
https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUE}/scoreboard?dates=YYYYMMDD
Output: data/espn_check.csv  (lega, data, partita, ours, espn, stato OK/DIFF/MANCANTE)
        + stampa riepilogo. Serve per intercettare errori di transcription (2 fonti prima di segnare il risultato).
"""
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

# lega nostra -> codice scoreboard ESPN
ESPN = {
    "Serie A": "ita.1", "Serie B": "ita.2",
    "Premier League": "eng.1", "Championship": "eng.2",
    "LaLiga": "esp.1", "LaLiga 2": "esp.2",
    "Bundesliga": "ger.1", "Bundesliga 2": "ger.2",
    "Ligue 1": "fra.1", "Ligue 2": "fra.2",
    "Eredivisie": "ned.1", "Primeira Liga": "por.1", "Süper Lig": "tur.1",
    "Champions League": "uefa.champions", "Europa League": "uefa.europa",
    "Conference League": "uefa.europa.conf",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def tscore(a, b):
    na, nb = norm(a), norm(b)
    if na == nb:
        return 3
    if na in nb or nb in na:
        return 2
    return 1 if set(na.split()) & set(nb.split()) else 0


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")


def espn_events(code, d):
    """Eventi ESPN del giorno d (prova anche d-1 per fusi orari)."""
    out = {}
    for day in (d, d - timedelta(days=1)):
        try:
            j = json.loads(get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={day.strftime('%Y%m%d')}"))
        except Exception:
            continue
        for ev in j.get("events", []):
            comp = ev.get("competitions", [{}])[0]
            comps = comp.get("competitors", [])
            if len(comps) != 2:
                continue
            home = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
            away = next((c for c in comps if c.get("homeAway") == "away"), comps[-1])
            finished = comp.get("status", {}).get("type", {}).get("completed", False)
            if not finished:
                continue
            try:
                hs, as_ = int(home["score"]), int(away["score"])
            except Exception:
                continue
            hn, an = home["team"]["displayName"], away["team"]["displayName"]
            out[(norm(hn), norm(an))] = (hs, as_, hn, an)
    return out


def main():
    d = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"])
    played = fx[fx["played"] & fx["hg"].notna() & (fx["Date"].dt.date >= d - timedelta(days=6))].copy()
    rows, cache = [], {}
    # cache per (lega, giorno): ESPN restituisce solo gli eventi del giorno richiesto
    days = sorted(set(played["Date"].dt.date))
    for lg, code in ESPN.items():
        for day in days:
            cache[(lg, day)] = espn_events(code, day)
    for _, r in played.iterrows():
        lg = r["league"]
        if lg not in ESPN:
            continue
        ev = cache.get((lg, r["Date"].date()), {})
        # match per nomi squadra
        best, bs = None, 0
        for (hn, an), v in ev.items():
            sc = tscore(r["home"], hn) + tscore(r["away"], an)
            if sc > bs:
                best, bs = v, sc
        ours = f"{int(float(r['hg']))}-{int(float(r['ag']))}"
        if best is None or bs < 4:
            rows.append({"lega": lg, "data": str(r["Date"].date()), "partita": f"{r['home']} - {r['away']}",
                         "noi": ours, "espn": "—", "stato": "MANCANTE-ESPN"})
        else:
            hs, as_, hn, an = best
            esp = f"{hs}-{as_}"
            stato = "OK" if esp == ours else "⚠️ DIFF"
            rows.append({"lega": lg, "data": str(r["Date"].date()), "partita": f"{r['home']} - {r['away']}",
                         "noi": ours, "espn": f"{esp} ({hn} - {an})", "stato": stato})
    df = pd.DataFrame(rows)
    out = DATA / "espn_check.csv"
    df.to_csv(out, index=False)
    print(f"🔎 Verifica ESPN vs FotMob per {d} (ultimi 7 gg): {len(df)} partite giocate")
    print(df["stato"].value_counts().to_string())
    diff = df[df.stato.str.contains("DIFF|MANCANTE")]
    if len(diff):
        print("\n⚠️ Da ricontrollare:")
        print(diff.to_string(index=False))
    print(f"\n💾 Salvato: {out}")


if __name__ == "__main__":
    main()
