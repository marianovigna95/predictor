#!/usr/bin/env python3
"""step12_tune_weights.py — tuning pesi ensemble (Elo / Dixon-Coles / mercato) + RPS anche su O2.5.

Walk-forward identico a validate_multi.py (g6-g10, train solo su partite precedenti),
ma: (a) griglia di pesi W_ELO/W_DC/W_MKT, (b) RPS anche per il mercato Over/Under 2.5.
Il training per (lega, giornata) viene fatto UNA sola volta e riutilizzato per tutti i pesi.

Uso:  python3 src/step12_tune_weights.py [--from-md 6] [--to-md 10]
Output: stampa tabella pesi + salva data/weights_tuning_0611.csv
"""
import argparse
import sys
from pathlib import Path

import os
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_multi as W
from weekly_multi import LEAGUES, train_league, predict_match, predict_match_full, standings, last_match

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def rps3(probs, y):
    cum_p = np.cumsum(probs)
    cum_o = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cum_p - cum_o) ** 2) / 2)


def rps2(p, y):
    return float((p - y) ** 2 + ((1 - p) - (1 - y)) ** 2) / 1.0  # RPS binario = (p-y)^2*2/2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-md", type=int, default=6)
    ap.add_argument("--to-md", type=int, default=40)
    args = ap.parse_args()

    matches = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"], low_memory=False)
    if os.environ.get("USE_WX", "1") == "1":
        W.load_weather()  # 🆕 13/11 meteo+derby in validazione
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"])

    # ---- cache training per (lega, md) ----
    cache = []
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
            res = {(r["Date"].normalize(), r["HomeTeam"], r["AwayTeam"]): r for _, r in cur.iterrows()}
            items = []
            for _, f in day.iterrows():
                r = res.get((f["Date"].normalize(), f["home"], f["away"]))
                if r is None:
                    continue
                y = 0 if r["FTHG"] > r["FTAG"] else (2 if r["FTHG"] < r["FTAG"] else 1)
                yo = 1 if (r["FTHG"] + r["FTAG"]) > 2.5 else 0
                odds = (r["AvgCH"], r["AvgCD"], r["AvgCA"]) if pd.notna(r.get("AvgCH")) else None
                oo = r.get("AvgC>2.5", None)  # se presente = over 2.5 (se i dati lo confermano)
                items.append((f, y, yo, odds, oo))
            if items:
                cache.append((league, md, (elo, dc_hist, ad, ahg, aag, draw_base, stand, last, hfa_l), items))
        print(f"  📦 cache {league} ok ({len([c for c in cache if c[0]==league])} giornate)")

    # ---- griglia pesi ----
    grid = []
    for wm in [0.0, 0.1, 0.2, 0.3]:
        rem = 1.0 - wm
        grid.append((round(rem / 2, 3), round(rem / 2, 3), wm))
    grid += [(0.6, 0.4, 0.0), (0.3, 0.5, 0.2), (0.5, 0.3, 0.2), (0.4, 0.4, 0.2)]

    rows = []
    for we, wd, wm in grid:
        W.W_ELO, W.W_DC, W.W_MKT = we, wd, wm
        rps_1x2, rps_ou, rps_mkt, rps_ou_mkt, n = [], [], [], [], 0
        allP = []
        allX = []
        allF = []
        allOU = []
        for league, md, state, items in cache:
            elo, dc_hist, ad, ahg, aag, draw_base, stand, last, hfa_l = state
            for f, y, yo, odds, oo in items:
                r = predict_match_full(elo, dc_hist, ad, ahg, aag, draw_base, f["Date"], f["home"], f["away"],
                                       stand=stand, last=last, odds=odds, hfa=hfa_l,
                                       wx=W.WX.get((f["home"], f["Date"].date().isoformat()), 1.0),
                                       derby=frozenset((f["home"], f["away"])) in W.DERBY)
                P, p_over = r[0], r[1]
                rps_1x2.append(rps3(P, y))
                allP.append((P, y, (league, md)))
                pmk = r[11] if r[11] is not None else (r[9] + r[10]) / 2.0
                allX.append((np.concatenate([r[9], r[10], pmk]), y, (league, md)))
                allF.append((r[12], y, (league, md)))
                rps_ou.append(rps2(p_over, yo))
                pm_ou = (1.0/float(oo)) if (oo is not None and pd.notna(oo) and float(oo) > 1.05) else p_over
                allOU.append((p_over, pm_ou, yo, (league, md)))
                n += 1
                if odds is not None:
                    inv = 1 / np.array(odds, float)
                    rps_mkt.append(rps3(inv / inv.sum(), y))
                if oo is not None and pd.notna(oo):
                    po = 1 / float(oo)
                    rps_ou_mkt.append(rps2(po, yo))
        rows.append({"W_ELO": we, "W_DC": wd, "W_MKT": wm, "n": n,
                     "RPS_1X2": round(np.mean(rps_1x2), 4), "RPS_O25": round(np.mean(rps_ou), 4),
                     "RPS_mercato_1X2": round(np.mean(rps_mkt), 4) if rps_mkt else "",
                     "RPS_mercato_O25": round(np.mean(rps_ou_mkt), 4) if rps_ou_mkt else ""})
        print(f"  ⚖️  ELO {we:.2f} / DC {wd:.2f} / MKT {wm:.2f}  →  RPS 1X2 {rows[-1]['RPS_1X2']:.4f}  RPS O2.5 {rows[-1]['RPS_O25']:.4f}  (n={n})")

    # 🆕 13/11 RPS con calibrazione isotonic leave-one-group-out (per (lega, giornata))
    try:
        from sklearn.isotonic import IsotonicRegression
        import numpy as _np
        groups = sorted({g for _, _, g in allP})
        rps_cal = []
        for g in groups:
            tr = [(P, y) for P, y, gg in allP if gg != g]
            te = [(P, y) for P, y, gg in allP if gg == g]
            if len(tr) < 60 or not te:
                continue
            X = _np.array([p for p, _ in tr]); Y = _np.array([y for _, y in tr])
            irs = [IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98).fit(X[:, k], (Y == k).astype(float)) for k in range(3)]
            for P, y in te:
                Q = _np.array([ir.predict(_np.atleast_1d(P[k]))[0] for k, ir in enumerate(irs)])
                Q = Q / Q.sum()
                rps_cal.append(rps3(Q, y))
        print(f"\n🎯 RPS 1X2 CALIBRATO (isotonic LOO): {sum(rps_cal)/len(rps_cal):.4f}  vs non calibrato (best pesi sotto)  n={len(rps_cal)}")
    except Exception as e:
        print("calibrazione saltata:", e)

    # 🆕 13/11 RPS dello STACKER (logistic sui 3 membri) leave-one-group-out
    try:
        from sklearn.linear_model import LogisticRegression
        groups = sorted({g for _, _, g in allX})
        rps_st = []
        for g in groups:
            tr = [(x, y) for x, y, gg in allX if gg != g]
            te = [(x, y) for x, y, gg in allX if gg == g]
            if len(tr) < 80 or not te:
                continue
            clf = LogisticRegression(max_iter=2000).fit(_np.array([x for x, _ in tr]), _np.array([y for _, y in tr]))
            for x, y in te:
                Q = clf.predict_proba(x.reshape(1, -1))[0]
                rps_st.append(rps3(Q, y))
        print(f"\n🧠 RPS 1X2 STACKER (logistic LOO): {sum(rps_st)/len(rps_st):.4f}  n={len(rps_st)}")
    except Exception as e:
        print("stacker saltato:", e)

    # 🆕 13/11 RPS del 4° membro GBM (feature tabellari) + stacker a 4 membri, LOO
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        groups = sorted({g for _, _, g in allF})
        rps_gbm, rps_st4 = [], []
        for g in groups:
            tr = [(x, y) for x, y, gg in allF if gg != g]
            te = [(x, y) for x, y, gg in allF if gg == g]
            trX = [(x, y) for x, y, gg in allX if gg != g]
            teX = [(x, y) for x, y, gg in allX if gg == g]
            if len(tr) < 80 or not te:
                continue
            gbm = HistGradientBoostingClassifier(max_iter=120, learning_rate=0.06, max_leaf_nodes=15, random_state=7).fit(
                _np.array([x for x, _ in tr]), _np.array([y for _, y in tr]))
            clf4 = LogisticRegression(max_iter=2000).fit(
                _np.array([_np.concatenate([x, gbm.predict_proba(f.reshape(1,-1))[0]]) for (x, _), (f, _) in zip(trX, tr)]),
                _np.array([y for _, y in trX]))
            for (x, y), (f, _) in zip(teX, te):
                pg = gbm.predict_proba(f.reshape(1, -1))[0]
                Qg = gbm.predict_proba(f.reshape(1, -1))[0]
                rps_gbm.append(rps3(Qg, y))
                Q4 = clf4.predict_proba(_np.concatenate([x, pg]).reshape(1, -1))[0]
                rps_st4.append(rps3(Q4, y))
        print(f"\n🌲 RPS GBM solo (LOO): {sum(rps_gbm)/len(rps_gbm):.4f}  n={len(rps_gbm)}")
        print(f"🧠 RPS STACKER 4 membri (LOO): {sum(rps_st4)/len(rps_st4):.4f}  n={len(rps_st4)}")
    except Exception as e:
        print("gbm saltato:", e)

    # 🆕 13/11 RPS O/U con stacker binario LOO (DC + mercato)
    try:
        from sklearn.linear_model import LogisticRegression as _LR2
        groups = sorted({g for *_, g in allOU})
        rps_ou_st = []
        for g in groups:
            tr = [(a, b, y) for a, b, y, gg in allOU if gg != g]
            te = [(a, b, y) for a, b, y, gg in allOU if gg == g]
            if len(tr) < 80 or not te:
                continue
            cl = _LR2(max_iter=1000).fit(_np.array([[a, b] for a, b, _ in tr]), _np.array([y for _, _, y in tr]))
            for a, b, y in te:
                p = cl.predict_proba(_np.array([[a, b]]))[0][1]
                rps_ou_st.append(rps2(p, y))
        print(f"\n📊 RPS O2.5 STACKER binario (LOO): {sum(rps_ou_st)/len(rps_ou_st):.4f}  n={len(rps_ou_st)}")
    except Exception as e:
        print("ou stacker saltato:", e)

    df = pd.DataFrame(rows).sort_values("RPS_1X2")
    out = DATA / "weights_tuning_0611.csv"
    df.to_csv(out, index=False)
    best = df.iloc[0]
    print(f"\n🏆 MIGLIOR PESO: W_ELO={best['W_ELO']} W_DC={best['W_DC']} W_MKT={best['W_MKT']}  RPS_1X2={best['RPS_1X2']}  RPS_O2.5={best['RPS_O25']}")
    print(f"   mercato: RPS_1X2 {df['RPS_mercato_1X2'].dropna().mean():.4f}")
    print(f"💾 {out}")


if __name__ == "__main__":
    main()
