#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step34_wmkt_ablation.py — QUANTO CONTA IL MERCATO DENTRO IL NOSTRO PRONOSTICO
==============================================================================
DOMANDA A CUI RISPONDE
    In src/weekly_multi.py (il file che produce le giocate pubblicate) la
    probabilita' finale e':

        P = W_ELO*P_elo + W_DC*P_dc + W_MKT*P_mkt     (default 0.5 / 0.3 / 0.2)

    Dato che P_mkt e' la probabilita' IMPLICITA DEL MERCATO STESSO, il 20% del
    nostro pronostico viene dal mercato. Poi confrontiamo quel pronostico con il
    mercato per trovare "valore". Domanda: quel 20% aiuta o e' solo un giro
    vizioso?

METODO (onesto, non simulato)
    1. prende le partite GIA' GIOCATE piu' recenti di ogni lega (le stesse che
       weekly_multi usa come storico)
    2. addestra Elo + Dixon-Coles SOLO su quelle precedenti a ogni data
       (walk-forward: nessun futuro nel passato)
    3. per ognuna calcola P con W_MKT = 0.0, 0.1, 0.2 (default attuale), 0.3
    4. misura RPS e accuratezza di ogni variante contro l'esito reale,
       confrontandole con il MERCATO de-vig (il "non modello")

⚠️ COSA NON FA
    - non tocca nessun file di dati, nessuna pagina, nessuna giocata pubblicata
    - non decide niente: produce numeri, la scelta resta all'utente
    - e' lento (riaddestra per lega): ~1-3 minuti

Output: data/wmkt_ablation.csv + stampa a video
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "wmkt_ablation.csv"

# stesse leghe di weekly_multi, quelle con storico sufficiente
LEAGUES = {
    "Serie A": "I1", "Serie B": "I2", "Premier League": "E0", "Championship": "E1",
    "LaLiga": "SP1", "LaLiga 2": "SP2", "Bundesliga": "D1", "Bundesliga 2": "D2",
    "Ligue 1": "F1", "Ligue 2": "F2", "Eredivisie": "N1",
}

W_GRID = [0.0, 0.1, 0.2, 0.3]      # 0.2 = default attuale
N_TAIL = 80                        # quante partite recenti per lega valutare


def rps(probs, outcomes):
    """Ranked Probability Score medio (piu' basso = meglio)."""
    probs = np.asarray(probs, float)
    outcomes = np.asarray(outcomes, int)
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(cum_p)
    cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)


def load_league(div):
    """Storico di una lega dai CSV football-data gia' presenti in data/."""
    files = sorted(DATA.glob(f"{div}_2*.csv"))
    if not files:
        return None
    frames = []
    for f in files:
        try:
            d = pd.read_csv(f, encoding="utf-8-sig", on_bad_lines="skip")
        except Exception:
            continue
        if "Date" not in d or "FTR" not in d:
            continue
        frames.append(d)
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
    d = d.dropna(subset=["Date", "FTR", "HomeTeam", "AwayTeam"])
    for c in ("FTHG", "FTAG"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["FTHG", "FTAG"])
    d = d[d["FTR"].isin(["H", "D", "A"])]
    # train_league pretende la colonna Season: la ricostruisco dalla data
    # (stagione europea: da luglio a giugno dell'anno dopo)
    def _season(dt):
        try:
            y = dt.year if dt.month >= 7 else dt.year - 1
            return f"{y}/{y + 1}"
        except Exception:
            return ""
    d["Season"] = d["Date"].apply(_season)
    return d.sort_values("Date").reset_index(drop=True)


def main():
    try:
        from weekly_multi import (
            W_ELO, W_DC, train_league, standings, last_match, predict_match_full,
        )
    except Exception as e:
        print(f"❌ impossibile importare weekly_multi: {e}")
        return 1

    print("=" * 78)
    print(" ABLATION W_MKT — quanto del nostro pronostico viene dal mercato?")
    print("=" * 78)
    print(f" pesi attuali: W_ELO={W_ELO}  W_DC={W_DC}  W_MKT={0.2 if abs(W_ELO+W_DC+0.2-0.9)<1e-9 else None}"
          f"   (griglia provata: {W_GRID})")
    print()

    righe = []
    for lega, div in LEAGUES.items():
        d = load_league(div)
        if d is None or len(d) < 250:
            print(f"  ⏭️  {lega}: storico insufficiente")
            continue
        tail = d.tail(N_TAIL)
        # addestra su tutto cio' che precede la prima partita valutata
        cut = tail["Date"].min()
        tr = d[d["Date"] < cut]
        if len(tr) < 150:
            print(f"  ⏭️  {lega}: training insufficiente ({len(tr)})")
            continue
        try:
            elo, dc_hist, ad, ahg, aag, draw_base, hfa = train_league(tr)
            stand = standings(tr)
            last = last_match(tr, d["Date"].max())
        except Exception as e:
            print(f"  ⏭️  {lega}: train_league fallito ({e})")
            continue

        P_pred = {w: [] for w in W_GRID}
        P_mkt, ys = [], []
        n_ok = 0
        for _, m in tail.iterrows():
            y = 0 if m["FTHG"] > m["FTAG"] else (2 if m["FTHG"] < m["FTAG"] else 1)
            odds = None
            if all(pd.notna(m.get(c)) for c in ("AvgCH", "AvgCD", "AvgCA")):
                odds = (m["AvgCH"], m["AvgCD"], m["AvgCA"])
            # P_mkt de-vigata (stessa logica di odds_util.devig usata nel fix #2)
            if odds is not None:
                inv = 1.0 / np.array(odds, float)
                pm = inv / inv.sum()
            else:
                pm = None
            try:
                r = predict_match_full(
                    elo, dc_hist, ad, ahg, aag, draw_base, m["Date"],
                    m["HomeTeam"], m["AwayTeam"], stand=stand, last=last,
                    odds=odds, hfa=hfa,
                )
            except Exception:
                continue
            P_elo_, P_dc_ = r[9], r[10]
            for w in W_GRID:
                if pm is not None:
                    P = (W_ELO * np.asarray(P_elo_, float)
                         + W_DC * np.asarray(P_dc_, float)
                         + w * np.asarray(pm, float))
                else:
                    P = 0.5 * np.asarray(P_elo_, float) + 0.5 * np.asarray(P_dc_, float)
                s = P.sum()
                P = P / s if s > 0 else np.array([1 / 3, 1 / 3, 1 / 3])
                P_pred[w].append(P)
            if pm is not None:
                P_mkt.append(pm)
            ys.append(y)
            n_ok += 1

        if n_ok < 40:
            print(f"  ⏭️  {lega}: campione troppo piccolo ({n_ok})")
            continue

        y_ = np.array(ys, int)
        acc_mkt = None
        rps_mkt = None
        if P_mkt:
            Pm = np.array(P_mkt, float)
            rps_mkt = rps(Pm, y_[:len(Pm)])
            acc_mkt = float(np.mean(Pm.argmax(axis=1) == y_[:len(Pm)]))
            righe.append({"lega": lega, "w_mkt": "MERCATO DE-VIG (non modello)",
                          "rps": round(rps_mkt, 4), "accuracy_pct": round(acc_mkt * 100, 1),
                          "n": len(Pm)})
        for w in W_GRID:
            Pp = np.array(P_pred[w], float)
            righe.append({"lega": lega, "w_mkt": f"{w:.1f}" + (" (attuale)" if w == 0.2 else ""),
                          "rps": round(rps(Pp, y_), 4),
                          "accuracy_pct": round(float(np.mean(Pp.argmax(axis=1) == y_) * 100), 1),
                          "n": len(y_)})
        print(f"  ✅ {lega}: {n_ok} partite valutate")

    if not righe:
        print("\n❌ nessuna lega valutabile")
        return 1

    df = pd.DataFrame(righe)
    df.to_csv(OUT, index=False)

    print("\n" + "=" * 78)
    print(" RISULTATI — RPS medio per valore di W_MKT (piu' basso = meglio)")
    print("=" * 78)
    summary = (df.groupby("w_mkt")
                 .agg(rps=("rps", "mean"), acc=("accuracy_pct", "mean"), n=("n", "sum"))
                 .reset_index())
    # ordina: mercato in cima (baseline), poi i W crescenti
    ordine = ["MERCATO DE-VIG (non modello)"] + [f"{w:.1f}" + (" (attuale)" if w == 0.2 else "") for w in W_GRID]
    summary["_o"] = summary["w_mkt"].apply(lambda x: ordine.index(x) if x in ordine else 99)
    summary = summary.sort_values("_o").drop(columns="_o")
    print(f"  {'variante':32s} {'RPS':>8s} {'accuracy':>10s} {'partite':>9s}")
    best = summary.loc[summary[summary['w_mkt'] != "MERCATO DE-VIG (non modello)"]["rps"].idxmin()]
    for _, r in summary.iterrows():
        mark = "  ←" if r["w_mkt"] == best["w_mkt"] else ""
        print(f"  {r['w_mkt']:32s} {r['rps']:8.4f} {r['acc']:9.1f}% {int(r['n']):9d}{mark}")
    print()
    print(f"  💾 {OUT.name}  ({len(df)} righe lega×variante)")
    print("\n⚠️ Lettura onesta: differenze sotto 0.005 di RPS NON sono distinguibili")
    print("   con questi campioni. Guarda se la differenza e' coerente tra leghe")
    print("   (colonna 'lega' nel CSV), non solo la media.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
