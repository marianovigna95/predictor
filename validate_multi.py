"""
VALIDAZIONE MULTI-LEGA — walk-forward per ogni lega (stagione 2026/27).

Per ogni lega e per ognuna delle ultime giornate giocate (default g6-g10):
  - addestra Elo+Dixon-Coles solo sulle partite ANTERIORI a quella giornata (per quella lega)
  - confronta RPS del modello vs RPS del mercato (quote di chiusura AvgCH/CD/CA)
  - accuratezza (pick = argmax p) modello vs mercato

Uso:  python3 src/validate_multi.py [--from-md 6] [--to-md 10]
Output: tabella per lega + salva data/validation_multi.csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_multi import (LEAGUES, train_league, predict_match, standings, last_match)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def rps(probs, y):
    cum_p = np.cumsum(probs)
    cum_o = np.zeros(3); cum_o[y] = 1
    cum_o = np.cumsum(cum_o)
    return float(np.sum((cum_p - cum_o) ** 2) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-md", type=int, default=6)
    ap.add_argument("--to-md", type=int, default=10)
    args = ap.parse_args()

    matches = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"])

    rows = []
    for league in LEAGUES:
        m_all = matches[matches["League"] == league].sort_values("Date").reset_index(drop=True)
        cur = m_all[m_all["Season"] == "2026/2027"]
        mds = sorted(fx[(fx["league"] == league) & (fx["played"])]["matchday"].unique())
        mds = [m for m in mds if args.from_md <= m <= args.to_md]
        for md in mds:
            day = fx[(fx["league"] == league) & (fx["matchday"] == md) & (fx["played"])]
            if day.empty:
                continue
            day0 = day["Date"].min()
            played = m_all[m_all["Date"] < day0]
            if len(played) < 300:
                continue
            elo, dc_hist, ad, ahg, aag, draw_base, hfa_l = train_league(played)
            stand = standings(played)
            last = last_match(played, day0)
            # risultati reali dalla lega 2627 (matches.csv ha FTR)
            res = {(r["Date"].normalize(), r["HomeTeam"], r["AwayTeam"]): r for _, r in cur.iterrows()}
            rps_m, rps_k, hits_m, hits_k, n = [], [], 0, 0, 0
            for _, f in day.iterrows():
                key = (f["Date"].normalize(), f["home"], f["away"])
                r = res.get(key)
                if r is None:
                    continue
                y = 0 if r["FTHG"] > r["FTAG"] else (2 if r["FTHG"] < r["FTAG"] else 1)
                odds = None
                if pd.notna(r.get("AvgCH")):
                    odds = (r["AvgCH"], r["AvgCD"], r["AvgCA"])
                from weekly_multi import form_weighted
                form = {f["home"]: form_weighted(played, elo, f["home"], f["Date"]),
                        f["away"]: form_weighted(played, elo, f["away"], f["Date"])}
                P, *_ = predict_match(elo, dc_hist, ad, ahg, aag, draw_base, f["Date"], f["home"], f["away"],
                                      stand=stand, last=last, odds=odds, form=form)
                rps_m.append(rps(P, y))
                n += 1
                if P.argmax() == y:
                    hits_m += 1
                if odds is not None:
                    inv = 1 / np.array(odds, float)
                    Pm = inv / inv.sum()
                    rps_k.append(rps(Pm, y))
                    if Pm.argmax() == y:
                        hits_k += 1
            rows.append({
                "lega": league, "giornata": md, "partite": n,
                "acc_modello%": round(hits_m / n * 100, 1) if n else "",
                "RPS_modello": round(np.mean(rps_m), 4) if rps_m else "",
                "acc_mercato%": round(hits_k / len(rps_k) * 100, 1) if rps_k else "",
                "RPS_mercato": round(np.mean(rps_k), 4) if rps_k else "",
            })
        print(f"  ✅ {league}: validato g{args.from_md}-g{args.to_md}")

    df = pd.DataFrame(rows)
    for c in ["partite", "acc_modello%", "RPS_modello", "acc_mercato%", "RPS_mercato"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    out = DATA / "validation_multi.csv"
    df.to_csv(out, index=False)
    print(f"\n💾 Salvato: {out}\n")
    summ = df.groupby("lega").agg(
        partite=("partite", "sum"),
        acc_modello=("acc_modello%", "mean"),
        RPS_modello=("RPS_modello", "mean"),
        acc_mercato=("acc_mercato%", "mean"),
        RPS_mercato=("RPS_mercato", "mean"),
    ).round(3)
    summ["edge_RPS (mkt-modello)"] = (summ["RPS_mercato"] - summ["RPS_modello"]).round(4)
    print("📊 RIEPILOGO PER LEGA (g%d-g%d 2026/27):" % (args.from_md, args.to_md))
    print(summ.to_string())
    print("\n✅ Edge positivo = il modello ha RPS più basso del mercato (meglio).")


import subprocess, sys
subprocess.run([sys.executable, 'src/test_standings.py'], check=True)

if __name__ == "__main__":
    main()
