#!/usr/bin/env python3
"""step10b_xg_backtest.py — backtest walk-forward: lambda da gol reali vs lambda da xG vs blend.

Domanda: usare l'xG (HxG/AxG di football-data/Opta in matches.csv) come stima dei gol attesi
migliora il RPS vs usare i gol reali (FTHG/FTAG) come proxy?

Modelli confrontati sullo STESSO test set (walk-forward, niente leakage):
  A) rolling GOALS  (ultime 6, half-life 3)  → lambda Poisson
  B) rolling xG     (ultime 6, half-life 3)  → lambda Poisson
  C) blend 50/50 A+B
Riferimento: mercato (quote medie AvgH/D/A).

Uso: python3 src/step10b_xg_backtest.py [--test-from 2026-07-01]
"""
import argparse
import math
import os
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def rps(probs, y):
    cum = np.cumsum(probs, axis=1)
    obs = np.zeros(3); obs[y] = 1.0
    return float(np.mean(np.sum((cum - obs) ** 2, axis=1) / 2.0))


def poisson_probs(lh, la, rho=0.08):
    """Dixon-Coles light: rho fisso per pareggi, max gol 6."""
    import math as m
    ph = [m.exp(-lh) * lh ** k / m.factorial(k) for k in range(7)]
    pa = [m.exp(-la) * la ** k / m.factorial(k) for k in range(7)]
    P = np.zeros((7, 7))
    for i in range(7):
        for j in range(7):
            w = 1.0
            if i == j and i <= 1:
                w = 1 - rho * (lh * la if i == 1 else 0) if i == 1 else 1 - rho * lh * la
                if i == 0:
                    w = 1 - rho * lh * la
            P[i, j] = ph[i] * pa[j] * w
    P /= P.sum()
    return np.array([P[i].sum() for i in range(7)]), np.array([P[:, j].sum() for j in range(7)]), P


def to_1x2(P):
    h = P[0].sum() + sum(P[i, j] for i in range(7) for j in range(7) if i > j)
    d = sum(P[i, i] for i in range(7))
    a = 1 - h - d
    return np.array([h, d, a])


def rolling_feats(df, col_h, col_a, n=6, hl=3.0):
    """Per ogni match: media pesata (exp decay) di xG/gol fatti e subiti delle ultime n partite della squadra."""
    df = df.sort_values("Date").reset_index(drop=True)
    hist = defaultdict(list)  # team -> list of (date, gf, ga)
    out_gf, out_ga = [], []
    for _, r in df.iterrows():
        h, a = r["HomeTeam"], r["AwayTeam"]
        def roll(team):
            hs = hist[team][-n:]
            if not hs:
                return (np.nan, np.nan)
            ws = [math.exp(-(len(hs) - 1 - i) / hl) for i in range(len(hs))]
            gf = sum(w * x[1] for w, x in zip(ws, hs)) / sum(ws)
            ga = sum(w * x[2] for w, x in zip(ws, hs)) / sum(ws)
            return gf, ga
        hgf, hga = roll(h)
        agf, aga = roll(a)
        out_gf.append((hgf, aga))  # attacco casa vs difesa ospite
        out_ga.append((hga, agf))
        # aggiorna storico DOPO (walk-forward)
        gf_h = r[col_h]; ga_h = r[col_a]
        hist[h].append((r["Date"], gf_h, ga_h))
        hist[a].append((r["Date"], ga_h, gf_h))
    lh = [ (x[0] + y[1]) / 2 for x, y in zip(out_gf, out_ga) ]
    la = [ (x[0] + y[1]) / 2 for x, y in zip(out_ga, out_gf) ]
    return np.array(lh, float), np.array(la, float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-from", default="2026-07-01")
    args = ap.parse_args()
    m = pd.read_csv(os.path.join(DATA, "matches.csv"), low_memory=False)
    m["Date"] = pd.to_datetime(m["Date"], errors="coerce")
    m = m.dropna(subset=["Date", "FTHG", "FTAG", "HxG", "AxG"]).copy()
    m = m[m["Date"] >= "2025-07-01"]
    print(f"📦 matches con xG: {len(m)} ({m['League'].nunique()} leghe, {m['Date'].min().date()} → {m['Date'].max().date()})")
    res = {"A_gol": [], "B_xG": [], "C_blend": [], "mercato": []}
    per_league = []
    for lg, df in m.groupby("League"):
        df = df.sort_values("Date").reset_index(drop=True)
        lh_g, la_g = rolling_feats(df, "FTHG", "FTAG")
        lh_x, la_x = rolling_feats(df, "HxG", "AxG")
        idx = np.where(df["Date"] >= args.test_from)[0]
        if len(idx) < 20:
            continue
        y = np.where(df["FTHG"].values > df["FTAG"].values, 0, np.where(df["FTHG"].values < df["FTAG"].values, 2, 1))[idx]
        ok = ~np.isnan(lh_g[idx]) & ~np.isnan(lh_x[idx])
        lhg, lag = lh_g[idx][ok], la_g[idx][ok]
        lhx, lax = lh_x[idx][ok], la_x[idx][ok]
        Pg = np.array([to_1x2(poisson_probs(a, b)[2]) for a, b in zip(lhg, lag)])
        Px = np.array([to_1x2(poisson_probs(a, b)[2]) for a, b in zip(lhx, lax)])
        Pc = np.array([to_1x2(poisson_probs((a + c) / 2, (b + d) / 2)[2]) for (a, b), (c, d) in zip(zip(lhg, lag), zip(lhx, lax))])
        res["A_gol"].append(rps(Pg, y[ok]))
        res["B_xG"].append(rps(Px, y[ok]))
        res["C_blend"].append(rps(Pc, y[ok]))
        q = df[["AvgH", "AvgD", "AvgA"]].values[idx][ok]
        Pm = 1.0 / q; Pm = Pm / Pm.sum(axis=1, keepdims=True)
        res["mercato"].append(rps(Pm, y[ok]))
        per_league.append({"lega": lg, "n": int(ok.sum()), "RPS_gol": round(rps(Pg, y[ok]), 4), "RPS_xG": round(rps(Px, y[ok]), 4)})
    print(f"\n🧪 Test set: dal {args.test_from} — RPS medio per lega (più basso = meglio):")
    print(f"  A) lambda da GOL reali : {np.mean(res['A_gol']):.4f}")
    print(f"  B) lambda da xG        : {np.mean(res['B_xG']):.4f}")
    print(f"  C) blend 50/50         : {np.mean(res['C_blend']):.4f}")
    print(f"  MERCATO (quote medie)  : {np.mean(res['mercato']):.4f}")
    pl = pd.DataFrame(per_league).sort_values("RPS_xG")
    print("\nPer lega (n test, RPS gol vs xG):")
    print(pl.to_string(index=False))


if __name__ == "__main__":
    main()
