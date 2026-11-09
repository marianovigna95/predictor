#!/usr/bin/env python3
"""step18_cascade.py — 'cascata' sequenziale: 5 partite di OGGI non sovrapposte in orario,
quote basse (~1.20-1.45), solo pick con EV>0 del modello. Calcola quota/probabilità/EV
combinati della cascata (reinvesto = accumulatore 5 leg) e 1/4 Kelly.
Uso: python3 src/step18_cascade.py [--date 2026-11-07] [--maxodd 1.45] [--n 5]
Output: stampa + data/cascata_<date>.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MARKETS = [("1", "p1%", "best_1"), ("X", "pX%", "best_X"), ("2", "p2%", "best_2"),
           ("O2.5", "Over2.5%", "best_O25"), ("U2.5", "Under2.5%", "best_U25"),
           ("GG", "BTTS%", "best_GG"), ("NG", "BTTS_NG%", "best_NG")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-11-07")
    ap.add_argument("--minodd", type=float, default=1.20)
    ap.add_argument("--maxodd", type=float, default=1.45)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--gapmin", type=int, default=135, help="minuti tra un kickoff e l'altro (durata ~2h15)")
    a = ap.parse_args()

    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)
    od["data"] = od["data"].astype(str)
    od = od[od["data"] == a.date]
    fo = pd.read_csv(DATA / "forecast_multi.csv")
    fo["giornata"] = fo["giornata"].astype(int)

    cands = []
    for _, o in od.iterrows():
        lg, md = o["lega"], int(o["giornata"])
        dt = pd.to_datetime(a.date + " " + str(o["orario"]).replace("/", "-").split()[-1] if "/" in str(o["orario"]) else str(o["orario"]), errors="coerce")
        try:
            hhmm = str(o["orario"]).split()[-1]
            dt = pd.Timestamp(a.date + " " + hhmm)
        except Exception:
            dt = pd.Timestamp(a.date)
        f = fo[(fo["lega"] == lg) & (fo["giornata"] == md)]
        f = f[f["partita"].str.lower().str.contains(str(o["home"]).split()[0].lower()[:6], na=False)]
        if len(f) == 0:
            continue
        f = f.iloc[0]
        r = {"home": o["home"], "away": o["away"]}
        f = f.copy()
        if "Over2.5%" in f: f["Under2.5%"] = 100 - f["Over2.5%"]
        if "BTTS%" in f: f["BTTS_NG%"] = 100 - f["BTTS%"]
        for mk, pcol, ocol in MARKETS:
            if pcol not in f:
                continue
            p = f[pcol]
            if pd.isna(p):
                continue
            q = o[ocol]
            if pd.isna(q) or q < a.minodd or q > a.maxodd:
                continue
            p = p / 100.0
            ev = p * (q - 1) - (1 - p)
            if ev <= 0.02:
                continue
            cands.append({"orario": dt, "lega": lg, "partita": f'{o["home"]} - {o["away"]}',
                          "mercato": mk, "p": round(p * 100, 1), "quota": q, "EV%": round(ev * 100, 2)})
    c = pd.DataFrame(cands).sort_values("orario")
    print(f"📋 Candidati oggi {a.date} (quota {a.minodd}-{a.maxodd}, EV>+2%): {len(c)}")
    # greedy non-sovrapposto
    chain, last_t = [], None
    for _, r in c.iterrows():
        t = r["orario"]
        if last_t is None or (t - last_t).total_seconds() >= a.gapmin * 60:
            chain.append(r)
            last_t = t
        if len(chain) >= a.n:
            break
    ch = pd.DataFrame(chain)
    if len(ch):
        ch.to_csv(DATA / f"cascata_{a.date}.csv", index=False)
        p_combo = 1.0
        q_combo = 1.0
        for _, r in ch.iterrows():
            p_combo *= r["p"] / 100
            q_combo *= r["quota"]
        ev = p_combo * (q_combo - 1) - (1 - p_combo)
        kelly = (p_combo * (q_combo - 1) - (1 - p_combo)) / (q_combo - 1)
        print(f"\n⛓️  CASCATA di {len(ch)} partite (non sovrapposte):")
        for _, r in ch.iterrows():
            print(f"  {r['orario'].strftime('%H:%M')} {r['lega'][:14]:14s} {r['partita'][:38]:38s} {r['mercato']:5s} p={r['p']}% @ {r['quota']} EV+{r['EV%']}%")
        print(f"\n  ➡️ Quota totale: {q_combo:.2f} | p combo (indipendenza): {p_combo*100:.1f}% | EV {ev*100:+.2f}% | 1/4 Kelly: {kelly/4*100:.2f}% del bankroll")
        print(f"  ⚠️  Se UNA leg perde, tutta la cascata perde (p perdre = {(1-p_combo)*100:.1f}%).")
        print(f"💾 data/cascata_{a.date}.csv")
    else:
        print("Nessuna catena trovata con questi vincoli.")


if __name__ == "__main__":
    main()
