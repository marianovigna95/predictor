#!/usr/bin/env python3
"""step20_eval_day.py — valutazione di TUTTI i pronostici del giorno (non solo le giocate).
Confronta forecast_multi.csv (per la data) con i risultati reali ESPN:
acc 1X2 (pronostico), RPS modello vs RPS mercato (da quota_best), hit O2.5, per lega.
Uso: python3 src/step20_eval_day.py [--date 2026-11-07]
"""
import argparse
import difflib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
SLUGS = {"ita.1": "Serie A", "ita.2": "Serie B", "eng.1": "Premier League", "eng.2": "Championship",
         "esp.1": "LaLiga", "esp.2": "LaLiga 2", "ger.1": "Bundesliga", "ger.2": "Bundesliga 2",
         "fra.1": "Ligue 1", "fra.2": "Ligue 2", "ned.1": "Eredivisie", "por.1": "Primeira Liga",
         "tur.1": "Süper Lig", "uefa.champions": "Champions League", "uefa.europa": "Europa League",
         "uefa.europa.conf": "Conference League"}


def nn(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


def rps3(p, y):
    cp = np.cumsum(p)
    co = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cp - co) ** 2) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-11-07")
    a = ap.parse_args()
    ds = a.date.replace("-", "")
    # risultati reali ESPN
    res = {}
    for slg, lg in SLUGS.items():
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slg}/scoreboard?dates={ds}", headers=UA), timeout=20))
        except Exception:
            continue
        for ev in d.get("events", []):
            c = ev["competitions"][0]
            st = c["status"]["type"]["name"]
            if "FULL" not in st and "FINAL" not in st:
                continue
            h = next(x for x in c["competitors"] if x["homeAway"] == "home")
            aw = next(x for x in c["competitors"] if x["homeAway"] == "away")
            res[(lg, nn(h["team"]["displayName"]), nn(aw["team"]["displayName"]))] = (
                int(float(h.get("score", 0))), int(float(aw.get("score", 0))))
    # forecast del giorno: giornata mappate via odds file
    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)
    od["data"] = od["data"].astype(str)
    gg = od[od["data"] == a.date][["lega", "giornata"]].drop_duplicates()
    fo = pd.read_csv(DATA / "forecast_multi.csv")
    fo["giornata"] = fo["giornata"].astype(int)
    f = fo.merge(gg, on=["lega", "giornata"])
    rows = []
    for _, r in f.iterrows():
        key = None
        for (lg, h, aw), sc in res.items():
            if lg != r["lega"]:
                continue
            if difflib.SequenceMatcher(None, h + "vs" + aw, nn(r["partita"].split(" - ")[0]) + "vs" + nn(r["partita"].split(" - ")[-1])).ratio() > 0.55:
                key = (lg, h, aw)
                break
        if key is None:
            continue
        gh, ga = res[key]
        y = 0 if gh > ga else (2 if gh < ga else 1)
        p1, px, p2 = r["p1%"] / 100, r["pX%"] / 100, r["p2%"] / 100
        P = np.array([p1, px, p2])
        q = r.get("quota_best")
        qm = None
        if pd.notna(q):
            # quota del pronostico: scegli 1/X/2 in base a pronostico
            mkt = {"1": "quota_best", "X": None, "2": None}.get(str(r["pronostico"]))
        pr = str(r["pronostico"]).strip()
        pick = {"1": 0, "X": 1, "2": 2}.get(pr, int(P.argmax()))
        # RPS mercato da quota_best (best price del pick)
        if pd.notna(q) and q > 1:
            imp = np.array([1 / q if i == pick else 0 for i in range(3)], dtype=float)
            # distribuisci il resto come margin: approx X/2 da p modello
            rest = 1 - 1 / q
            others = [i for i in range(3) if i != pick]
            imp[others[0]] = rest * P[others[0]] / (P[others[0]] + P[others[1]] + 1e-9)
            imp[others[1]] = rest * P[others[1]] / (P[others[0]] + P[others[1]] + 1e-9)
            qm = imp
        ou_hit = (gh + ga) > 2.5
        rows.append({"lega": r["lega"], "partita": r["partita"], "pronostico": pr, "reale": "1X2"[y],
                     "hit": int(pick == y), "p%": round(P[pick] * 100, 1), "quota": q,
                     "rps_mod": rps3(P, y), "rps_mkt": rps3(qm, y) if qm is not None else np.nan,
                     "pO25%": r.get("Over2.5%"), "ou_reale": "Over" if ou_hit else "Under",
                     "ou_hit": int((r["Over2.5%"] > 50) == ou_hit)})
    df = pd.DataFrame(rows)
    df.to_csv(DATA / f"eval_day_{a.date}.csv", index=False)
    n = len(df)
    print(f"📅 Valutazione TUTTI i pronostici del {a.date}: {n} partite giocate (su {len(f)} con forecast)")
    if n:
        print(f"  1X2 accuracy: {df['hit'].mean()*100:.1f}%  (random ~33%)")
        print(f"  RPS modello: {df['rps_mod'].mean():.4f} | RPS mercato: {df['rps_mkt'].mean():.4f}")
        print(f"  O2.5 hit (p>50% vs reale): {df['ou_hit'].mean()*100:.1f}%")
        print(df.groupby("lega")[["hit", "rps_mod", "rps_mkt"]].agg({"hit": "mean", "rps_mod": "mean", "rps_mkt": "mean"}).round(3).to_string())
        print("💾 data/eval_day_%s.csv" % a.date)


if __name__ == "__main__":
    main()
