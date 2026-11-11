#!/usr/bin/env python3
"""step1f — NAZIONALI: calendario + storico per competizioni internazionali.

Fonti (gratis, no key):
- ESPN scoreboard per gli slug uefa.nations / fifa.worldq.uefa / fifa.friendly
  (finestra: oggi-40 → oggi+14, così prende sia risultati recenti sia prossime partite)
- kaggle_matches.csv (storico 2018→2026: UEFA Nations League, WCQ UEFA, International Friendlies)
Output: data/fixtures_intl.csv  (stesso schema di fixtures_leagues.csv:
        league, div, matchday, date, home, away, played, hg, ag)
I nomi squadre sono canonicalizzati verso quelli di kaggle (match via forma normalizzata).
Uso: python3 src/step1f_internationals.py
"""
import datetime
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
ROME = ZoneInfo("Europe/Rome")

ESPN_SLUGS = {
    "uefa.nations": ("Nations League", "UNL"),
    "fifa.worldq.uefa": ("WC Qual. UEFA", "WCQ"),
    "fifa.friendly": ("Friendlies", "FRD"),
}
KAGGLE2OURS = {
    "UEFA Nations League": "Nations League",
    "FIFA World Cup Qualifiers - UEFA": "WC Qual. UEFA",
    "International Friendlies": "Friendlies",
}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")


def nrm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def main():
    # --- nomi canonici da kaggle (storico) ---
    kaggle_names = {}
    kg = pd.read_csv(DATA / "kaggle_matches.csv", low_memory=False)
    for t in set(kg["home_team"]) | set(kg["away_team"]):
        if str(t).endswith(" VI"):
            continue
        kaggle_names.setdefault(nrm(t), str(t))

    def canon(name):
        n = nrm(name)
        return kaggle_names.get(n, str(name))

    rows = []

    # --- storico kaggle (2023→oggi) ---
    hist = kg[kg["league_name"].isin(KAGGLE2OURS) & (kg["season"].astype(str) >= "2023") &
              kg["ft_home"].notna() & kg["ft_away"].notna()].copy()
    for _, r in hist.iterrows():
        if str(r["home_team"]).endswith(" VI") or str(r["away_team"]).endswith(" VI"):
            continue
        dt = pd.to_datetime(r["kickoff_utc"], utc=True).tz_convert(ROME)
        hg, ag = int(r["ft_home"]), int(r["ft_away"])
        rows.append({"league": KAGGLE2OURS[r["league_name"]],
                     "div": {"Nations League": "UNL", "WC Qual. UEFA": "WCQ", "Friendlies": "FRD"}[KAGGLE2OURS[r["league_name"]]],
                     "matchday": 0, "date": dt.strftime("%Y-%m-%d %H:%M"),
                     "home": canon(r["home_team"]), "away": canon(r["away_team"]),
                     "played": True, "hg": hg, "ag": ag})
    print(f"📚 storico kaggle: {len(rows)} match internazionali (2023+)")

    # --- ESPN: risultati recenti + calendario ---
    today = datetime.date.today()
    n_espn = 0
    for slug, (lname, div) in ESPN_SLUGS.items():
        for off in range(-40, 15):
            d = today + datetime.timedelta(days=off)
            try:
                j = json.loads(get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d.strftime('%Y%m%d')}"))
            except Exception:
                continue
            for ev in j.get("events", []):
                comp = ev["competitions"][0]
                cs = comp["competitors"]
                h = next((c for c in cs if c["homeAway"] == "home"), cs[0])
                a = next((c for c in cs if c["homeAway"] == "away"), cs[1])
                st = comp["status"]
                played = st["type"]["state"] == "post"
                hg = ag = ""
                if played:
                    hg, ag = h.get("score", ""), a.get("score", "")
                dt = datetime.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ROME)
                rows.append({"league": lname, "div": div, "matchday": 0,
                             "date": dt.strftime("%Y-%m-%d %H:%M"),
                             "home": canon(h["team"]["displayName"]), "away": canon(a["team"]["displayName"]),
                             "played": played, "hg": hg, "ag": ag})
                n_espn += 1
    print(f"📡 ESPN: {n_espn} eventi (ultimi 40gg + prossimi 14gg)")

    df = pd.DataFrame(rows)
    # dedup: preferisci ESPN (più recente) allo storico kaggle sulla stessa partita
    df["_src"] = ["kaggle"] * (len(df) - n_espn) + ["espn"] * n_espn
    df["key"] = df["league"] + "|" + df["date"].str[:10] + "|" + df["home"].map(nrm) + "|" + df["away"].map(nrm)
    df = df.sort_values("_src").drop_duplicates("key", keep="last").drop(columns=["_src", "key"])
    df = df.sort_values(["date", "league"]).reset_index(drop=True)
    out = DATA / "fixtures_intl.csv"
    df.to_csv(out, index=False)
    nxt = df[~df.played].groupby("league")["date"].min()
    print(f"\n✅ Salvato: {out} ({len(df)} righe, {int(df.played.sum())} giocate)")
    print("📅 Prossime partite per competizione nazionale:")
    print(nxt.to_string())


if __name__ == "__main__":
    main()
