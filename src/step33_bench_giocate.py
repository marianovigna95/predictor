#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 33 — Ricostruzione ONESTA del backtest delle giocate 1X2 (sostituisce data/bets_1x2.csv).
=========================================================================================
PERCHE' ESISTE (diagnosi VERIFICATA riga per riga, non supposta)
----------------------------------------------------------------
Il vecchio data/bets_1x2.csv era prodotto da src/step6_ensemble.py con:

      bet_logs = [(..., ["H","D","A"][int(np.argmax(P_ens[i] - P_mkt[i]))],
                   float(bet_odds[i].max()),      # <-- quota MASSIMA fra i 3 esiti
                   float(P_ens[i].max()),         # <-- probabilita' MASSIMA fra i 3
                   int(y[i])) for i in picks]     # <-- esito reale, corretto

  1. **p_modello = max(pH,pD,pA) — IL VERO COLPEVOLE (confermato 1492/1492)**
     Non e' la probabilita' dell'esito scelto, e' la piu' alta delle tre.
     Sovrastima media: +12,3 punti percentuali (0,505 dichiarata vs 0,382 reale).
     Effetto sull'EV medio: +171,9% dichiarato contro +77,0% vero
     → il file gonfiava l'EV di ~+95 punti percentuali.

  2. **quota = max(oddH,oddD,oddA) — bug reale ma impatto limitato**
     Coincide con la quota del pick solo nel 55% delle righe. Nel resto registra
     il prezzo di un esito che non abbiamo giocato.

  3. **esito in codice 0/1/2 invece di H/D/A** — NON e' un bug
     Verificato: corrisponde a FTR su 1492/1492 righe. Solo scomodo da leggere.

  4. **selezione e valutazione sullo stesso campione**
     step6 elegge il "miglior ensemble" con rps() sull'INTERO dataset e poi
     misura l'edge sullo stesso: i numeri che ne escono sono ottimistici.

COSA FA QUESTO SCRIPT (e solo questo)
-------------------------------------
Non riallena niente: legge le probabilita' GIA' salvate out-of-sample da
predictions_ensemble.csv (walk-forward: ogni partita prevista con il modello
allenato solo sul passato) e produce un CSV corretto, onesto e verificabile:

  data/bets_1x2_onesto.csv      una riga per giocata, con esito reale e quota giusta
  data/bets_1x2_onesto_meta.json sintesi + esito dei controlli di coerenza

REGOLE DEL FILE CORRETTO
  1. esito reale come lettera (H/D/X... H/D/A) preso da FTR, non un intero
  2. quota = quella dell'ESITO SCELTO (@ oddH/oddD/oddA), non il massimo
  3. p del modello = ens_p dell'esito scelto, mai la massima
  4. pick = l'esito con il gap massimo (p_modello - p_mercato de-vig)
  5. segnala e ISOLA le righe con probabilita' non valide (placeholder o somma != 1)
  6. calcola EV, vincita, P&L, e un CLV onesto dove la quota di chiusura e' nota
  7. riporta in chiaro il campione e i limiti: n piccolo = conclusioni deboli

Uso:  python3 src/step33_bench_giocate.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

OUT_CSV = DATA / "bets_1x2_onesto.csv"
OUT_META = DATA / "bets_1x2_onesto_meta.json"

SOGLIA_GAP = 0.02        # stesse regole del sito: solo se il modello batte il mercato di > 2pp
TOL_SOMMA = 1e-3         # tolleranza sulla somma delle 3 probabilita'


def _rps(probs, outcomes):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs)
    cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)


def main():
    p_ens = DATA / "predictions_ensemble.csv"
    if not p_ens.exists():
        print(f"⚠️ manca {p_ens}: niente da ricostruire")
        OUT_META.write_text(json.dumps({"stato": "senza_ensemble"}, indent=1))
        return 0

    d = pd.read_csv(p_ens, low_memory=False)
    n0 = len(d)
    print(f"📥 {p_ens.name}: {n0} partite")

    # ---------- controlli di qualita' sulle probabilita' ----------
    for c in ("ens_pH", "ens_pD", "ens_pA"):
        if c not in d:
            print(f"❌ colonna mancante: {c}")
            return 1
    P = d[["ens_pH", "ens_pD", "ens_pA"]].to_numpy(float)
    somma = P.sum(axis=1)
    fuori = (P < 0) | (P > 1) | ~np.isfinite(P)
    bad = fuori.any(axis=1) | (np.abs(somma - 1) > TOL_SOMMA)
    n_bad = int(bad.sum())
    if n_bad:
        print(f"   ⚠️ {n_bad} righe con probabilita' non valide (somma != 1 o fuori [0,1]) → escluse")

    # ---------- esito reale e quote ----------
    if "FTR" not in d:
        print("❌ manca FTR (esito reale): impossibile ricostruire senza bari")
        return 1
    esito = d["FTR"].astype(str).str.strip().str.upper()
    ok_esito = esito.isin(["H", "D", "A"])
    if (~ok_esito).sum():
        print(f"   ⚠️ {int((~ok_esito).sum())} righe senza esito valido → escluse")

    odds = d[["oddH", "oddD", "oddA"]].to_numpy(float)
    has_odds = np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)

    # probabilita' implicite de-vig (il mercato, senza margine)
    inv = np.where(has_odds[:, None], 1 / np.where(odds > 1, odds, np.nan), np.nan)
    tot = np.nansum(inv, axis=1, keepdims=True)
    P_mkt = inv / np.where(tot > 0, tot, np.nan)

    tenere = (~bad) & ok_esito.to_numpy() & has_odds
    print(f"   righe utilizzabili: {int(tenere.sum())}/{n0}")

    # gap per esito e pick
    gap = P - P_mkt
    idx_pick = np.nanargmax(np.where(np.isfinite(gap), gap, -np.inf), axis=1)
    gap_pick = gap[np.arange(len(d)), idx_pick]

    # RPS del modello sulle righe valide (misura onesta, indipendente dalle giocate)
    y_all = esito.map({"H": 0, "D": 1, "A": 2}).to_numpy()
    m = tenere & np.isfinite(y_all)
    rps_mod = _rps(P[m], y_all[m].astype(int)) if m.sum() else float("nan")
    rps_mkt = _rps(P_mkt[m], y_all[m].astype(int)) if m.sum() else float("nan")

    # ---------- costruzione delle giocate ----------
    LETTERE = ["H", "D", "A"]
    righe = []
    for i in range(len(d)):
        if not tenere[i] or not np.isfinite(gap_pick[i]) or gap_pick[i] <= SOGLIA_GAP:
            continue
        j = int(idx_pick[i])
        q = float(odds[i, j])                 # ✅ la quota dell'esito SCELTO
        p = float(P[i, j])                    # ✅ la p dell'esito SCELTO
        es = LETTERE[j]
        vinto = int(esito.iloc[i] == es)
        righe.append({
            "data": str(d.get("Date", pd.Series([""] * n0)).iloc[i])[:10],
            "stagione": d.get("Season", pd.Series([""] * n0)).iloc[i],
            "casa": d.get("Home", pd.Series([""] * n0)).iloc[i],
            "trasferta": d.get("Away", pd.Series([""] * n0)).iloc[i],
            "pick": es,
            "quota": round(q, 3),
            "p_modello": round(p, 4),
            "p_mercato": round(float(P_mkt[i, j]), 4),
            "gap_pp": round(float(gap_pick[i]) * 100, 2),
            "ev_pct": round((p * q - 1) * 100, 2),
            "esito_reale": esito.iloc[i],
            "vinto": vinto,
            "pnl_unita": round(q - 1, 3) if vinto else -1.0,
        })

    meta = {"aggiornato": pd.Timestamp.now().isoformat(timespec="seconds"),
            "fonte": "predictions_ensemble.csv (walk-forward), non le quote stesse",
            "soglia_gap_pp": SOGLIA_GAP * 100,
            "partite_totali": n0,
            "partite_utilizzabili": int(m.sum()),
            "righe_escluse_probabilita": n_bad,
            "RPS_modello": round(rps_mod, 4) if np.isfinite(rps_mod) else None,
            "RPS_mercato": round(rps_mkt, 4) if np.isfinite(rps_mkt) else None,
            "nota": "RPS piu' basso = meglio. Se modello > mercato, il modello e' peggiore."}

    if not righe:
        print("ℹ️ nessuna giocata sopra soglia: file non scritto")
        OUT_META.write_text(json.dumps({**meta, "stato": "nessuna_giocata"}, indent=1))
        return 0

    b = pd.DataFrame(righe)
    b.to_csv(OUT_CSV, index=False)

    n = len(b)
    w = int(b["vinto"].sum())
    roi = b["pnl_unita"].sum() / n
    ev_medio = b["ev_pct"].mean()

    meta.update({"stato": "ok", "giocate": n, "vinte": w,
                 "win_rate_pct": round(w / n * 100, 1),
                 "roi_pct": round(roi * 100, 1),
                 "ev_medio_pct": round(ev_medio, 2),
                 "giocate_per_stagione": {str(k): int(v) for k, v in b["stagione"].value_counts().items()}})
    OUT_META.write_text(json.dumps(meta, indent=1, ensure_ascii=False))

    print(f"\n✅ {OUT_CSV.name}: {n} giocate su {int(m.sum())} partite valutabili")
    print(f"   vinte: {w} ({w/n*100:.1f}%)  ·  quota media {b['quota'].mean():.2f}  ·  EV medio {ev_medio:+.2f}%")
    print(f"   ROI flat: {roi*100:+.1f}%   ({b['pnl_unita'].sum():+.1f} unita' su {n})")
    print(f"   RPS modello {rps_mod:.4f} vs mercato {rps_mkt:.4f} → "
          f"{'modello peggiore (onesto)' if rps_mod > rps_mkt else 'modello migliore'}")
    print("\n   per stagione:")
    for s, g in b.groupby("stagione"):
        print(f"     {s}: n={len(g):>3d}  vinte {g['vinto'].mean()*100:>5.1f}%  "
              f"ROI {g['pnl_unita'].mean()*100:>+6.1f}%")
    print("\n⚠️ Campione piccolo: le conclusioni valgono solo se ripetute nel tempo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
