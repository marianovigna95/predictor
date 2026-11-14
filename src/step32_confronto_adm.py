#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 32 — Confronto INTERNO quota best-price vs quota ADM giocabile.
===============================================================
Domanda a cui risponde: l'edge che vediamo sui prezzi aggregati internazionali
sopravvive quando si gioca davvero su un book italiano? Se la quota ADM e'
molto piu' bassa, l'EV calcolato e' illusorio.

⚠️ USO INTERNO (strada A, decisione utente 14/11). I termini della fonte
(odss-api.com/llms.txt) includono "internal use (models, bots, analysis,
backtests)" ma richiedono la licenza Display Redistribution (+120 EUR/mese)
per MOSTRARE i dati a utenti finali. Percio' questo report:
  - scrive in data/ (dati del repo, non pagine del sito);
  - NON viene linkato ne' incorporato in nessuna pagina pubblica;
  - non nomina la fonte (regola: sulle pagine pubbliche solo "fonti pubbliche gratuite").

Output: data/confronto_adm.csv + data/confronto_adm_meta.json
Nessuna chiamata API: legge solo CSV gia' presenti (non consuma quota).
"""
import json
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SOGLIA_TENUTA = -0.015   # la quota ADM puo' essere fino a 1.5% piu' bassa: EV ancora valido
SOGLIA_ROSSA = -0.05     # oltre -5% l'edge e' probabilmente svanito


def _n(s):
    """Nome partita normalizzato: minuscolo, senza accenti, senza squadre tra [..]."""
    s = str(s).split("[")[0]
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", "and")
    for ch in ".-'’`":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _merc(m):
    """Normalizza il mercato: 1X2 -> 1x2 · U2.5/O2.5 -> 2.5 · GG/NG -> gg."""
    m = str(m).upper().strip()
    if m in ("1X2", "1"): return "1x2"
    if "2.5" in m: return "2.5"
    if m in ("GG", "NG", "BTTS", "YES", "NO"): return "gg"
    return m.lower()


# 🆕 14/11 gli esiti sono il pezzo che mancava: senza, "2.5" puo' essere Over o Under
# e si confronterebbe la quota Under contro la migliore quota Over della partita.
_ESITI = {
    "U2.5": {"U2.5", "UNDER"}, "O2.5": {"O2.5", "OVER"},
    "GG": {"GG", "YES"}, "NG": {"NG", "NO"},
    "1": {"1", "HOME", "CASA"}, "X": {"X", "DRAW", "PAREGGIO"},
    "2": {"2", "AWAY", "TRASFERTA"},
}


def _esiti(m):
    """Esiti accettabili per un mercato; None = senza colonna esito (legacy, accetta tutto)."""
    k = str(m).upper().strip()
    return _ESITI.get(k)


def _merc_esito(mercato, esito):
    """Da 'U2.5' ricava il mercato '2.5' e gli esiti ammessi."""
    m = _merc(mercato)
    e = str(esito).upper().strip()
    amm = _esiti(e)
    if amm is None:
        # esito esplicito ma non in mappa (es. 'Over 2.5' scritto esteso)
        if "UNDER" in e or e.startswith("U"): amm = _ESITI["U2.5"]
        elif "OVER" in e or e.startswith("O"): amm = _ESITI["O2.5"]
        elif e.startswith("GG") or e == "YES": amm = _ESITI["GG"]
        elif e.startswith("NG") or e == "NO": amm = _ESITI["NG"]
    return m, amm


def _quota_best(r):
    for c in ("quota_best", "quota_best_dec", "quota"):
        if c in r and pd.notna(r[c]):
            try:
                v = float(r[c])
                return v if v > 1.05 else None
            except Exception:
                pass
    return None


def main():
    g_path = DATA / "giocata_multi.csv"
    a_path = DATA / "quote_adm.csv"
    meta = {"aggiornato": pd.Timestamp.now().isoformat(timespec="seconds")}

    if not g_path.exists():
        print("⚠️ manca data/giocata_multi.csv: niente da confrontare")
        (DATA / "confronto_adm_meta.json").write_text(json.dumps({**meta, "stato": "senza_giocate"}, indent=1))
        return 0
    if not a_path.exists():
        print("ℹ️ manca data/quote_adm.csv (nessuna chiave o nessuna richiesta): confronto saltato")
        (DATA / "confronto_adm_meta.json").write_text(json.dumps({**meta, "stato": "senza_quote_adm"}, indent=1))
        return 0

    g = pd.read_csv(g_path, low_memory=False)
    a = pd.read_csv(a_path, low_memory=False)
    # 🆕 14/11 solo SINGOLA: un raddoppio ha quota COMBINATA da due partite diverse,
    #   non esiste una "quota ADM" equivalente da confrontare.
    if "tipo" in g:
        g = g[g["tipo"] == "SINGOLA"]

    # indice delle quote ADM per (data, partita normalizzata, mercato)
    adm = {}
    for _, r in a.iterrows():
        try:
            q = float(r.get("quota_adm_best"))
        except Exception:
            continue
        if pd.isna(q) or q <= 1.05:
            continue
        k = (str(r.get("data", ""))[:10], _n(r.get("partita", "")), _merc(r.get("mercato", "")))
        adm.setdefault(k, []).append({
            "quota_adm": q, "book": r.get("book", ""), "n_book": r.get("n_book", ""),
            "esito": str(r.get("esito", "") or "").upper().strip(),
        })

    righe, senza = [], 0
    for _, r in g.iterrows():
        qb = _quota_best(r)
        if qb is None:
            continue
        mk = str(r.get("mercato", ""))
        amm = _esiti(mk) or _merc_esito(mk, r.get("esito", ""))[1]
        k = (str(r.get("data", ""))[:10], _n(r.get("partita", "")), _merc(mk))
        cand = adm.get(k) or []
        # tiene solo le quote dello STESSO esito (Under con Under, GG con GG...)
        if amm:
            cand = [c for c in cand if not c["esito"] or c["esito"] in amm]
        if not cand:
            senza += 1
            continue
        hit = max(cand, key=lambda c: c["quota_adm"])
        qa = hit["quota_adm"]
        delta = (qa - qb) / qb
        # EV ricalcolato: EV = p*(O-1) - (1-p)
        try:
            p = float(str(r.get("p_modello%", "")).replace(",", ".")) / 100
        except Exception:
            p = None
        ev_best = (p * (qb - 1) - (1 - p)) if p else None
        ev_adm = (p * (qa - 1) - (1 - p)) if p else None
        stato = "ok" if delta >= SOGLIA_TENUTA else ("limite" if delta >= SOGLIA_ROSSA else "edge_perso")
        righe.append({
            "data": k[0], "tipo": r.get("tipo", ""), "lega": r.get("lega", ""),
            "partita": r.get("partita", ""), "mercato": r.get("mercato", ""),
            "quota_best": round(qb, 3), "quota_adm": round(qa, 3),
            "delta_pct": round(delta * 100, 2), "book_adm": hit["book"], "n_book": hit["n_book"],
            "p_modello": round(p * 100, 1) if p else "",
            "EV_best_pct": round(ev_best * 100, 2) if ev_best is not None else "",
            "EV_adm_pct": round(ev_adm * 100, 2) if ev_adm is not None else "",
            "stato": stato,
        })

    if not righe:
        print(f"ℹ️ nessuna corrispondenza ({senza} giocate fuori copertura ADM oggi)")
        (DATA / "confronto_adm_meta.json").write_text(json.dumps(
            {**meta, "stato": "nessuna_corrispondenza", "giocate_non_coperte": senza}, indent=1))
        return 0

    df = pd.DataFrame(righe).sort_values("delta_pct", ascending=False)
    df.to_csv(DATA / "confronto_adm.csv", index=False)

    n = len(df)
    medi = df["delta_pct"].mean()
    ok = int((df["stato"] == "ok").sum())
    lim = int((df["stato"] == "limite").sum())
    perso = int((df["stato"] == "edge_perso").sum())
    ev_ok = int((pd.to_numeric(df["EV_adm_pct"], errors="coerce") > 0).sum())

    out = {**meta, "stato": "ok", "confronti": n, "giocate_non_coperte": senza,
           "delta_medio_pct": round(medi, 2),
           "delta_min_pct": round(df["delta_pct"].min(), 2),
           "delta_max_pct": round(df["delta_pct"].max(), 2),
           "tenuta_ok": ok, "tenuta_limite": lim, "edge_perso": perso,
           "EV_positivo_su_quota_adm": ev_ok,
           "soglie": {"ok": SOGLIA_TENUTA, "rossa": SOGLIA_ROSSA},
           "nota": "USO INTERNO: non pubblicato sul sito (licenza Display non acquisita)."}
    (DATA / "confronto_adm_meta.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    # report leggibile (resta in data/, NON e' una pagina del sito)
    md = [f"# Confronto interno quota best-price vs quota ADM\n",
          f"_Aggiornato: {meta['aggiornato']} — uso interno, non pubblicato_\n",
          f"- giocate confrontate: **{n}** (fuori copertura ADM: {senza})",
          f"- delta medio: **{medi:+.2f}%** (min {df['delta_pct'].min():+.2f}%, max {df['delta_pct'].max():+.2f}%)",
          f"- tenuta: **{ok} OK** · {lim} al limite · {perso} con edge perso",
          f"- EV ancora positivo con la quota ADM: **{ev_ok}/{n}**\n",
          "## Dettaglio\n",
          "| Data | Partita | Mercato | best | ADM | delta | EV best | EV ADM | esito |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        md.append(f"| {r['data']} | {r['partita']} | {r['mercato']} | {r['quota_best']} | "
                  f"{r['quota_adm']} | {r['delta_pct']:+.2f}% | {r['EV_best_pct']}% | {r['EV_adm_pct']}% | {r['stato']} |")
    (DATA / "confronto_adm.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"📊 confronto su {n} giocate (non coperte: {senza})")
    print(f"   delta medio quota ADM vs best: {medi:+.2f}%  (min {df['delta_pct'].min():+.2f}%, max {df['delta_pct'].max():+.2f}%)")
    print(f"   tenuta OK: {ok} · al limite: {lim} · edge perso: {perso}")
    print(f"   EV ancora > 0 con la quota ADM: {ev_ok}/{n}")
    for _, r in df.head(8).iterrows():
        print(f"   {r['data']} {str(r['partita'])[:34]:34s} {r['quota_best']:>5} → {r['quota_adm']:>5} "
              f"({r['delta_pct']:+6.2f}%) EV {r['EV_best_pct']:>6} → {r['EV_adm_pct']:>6}  {r['stato']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
