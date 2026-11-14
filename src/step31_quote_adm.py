#!/usr/bin/env python3
"""step31_quote_adm.py — 🇮🇹 13/11-b QUOTE ADM REALI (il passo di qualità)

PERCHÉ ESISTE
-------------
Il best-price che pubblichiamo viene da un comparatore che copre book NON-ADM
(bet365/betway/betsson/unibet): sono quote che in Italia NON puoi giocare.
Questo script legge una fonte che espone le quote di 40+ operatori con licenza ADM
e salva, per ogni partita della finestra, la MIGLIORE quota ADM disponibile.

REGOLA D'ORO: senza chiave API lo script NON fa danni — esce con "SKIP" e il sito
continua a funzionare con le quote attuali. La chiave si mette in una variabile
d'ambiente / secret del repo:  ODSS_API_KEY

USO
---
    export ODSS_API_KEY=odss_live_xxx      # una volta sola (o secret su GitHub)
    python3 src/step31_quote_adm.py                 # finestra standard
    python3 src/step31_quote_adm.py --dry-run       # non scrive nulla, mostra solo

OUTPUT
------
    data/quote_adm.csv       → data,lega,partita,mercato,quota_adm_best,book,n_book,aggiornato
    data/quote_adm_meta.json → quando è stato aggiornato, copertura, quota richieste usate

Il file viene poi letto da make_site.py (colonna facoltativa) per mostrare, accanto
alla quota best-price, la quota ADM realmente giocabile.

NOTE DI ONESTÀ
--------------
- I book NON-ADM non vengono mai pubblicati: si salvano solo gli operatori con
  playable_it == true (licenza ADM). Gli altri restano fuori dal file.
- Se la fonte risponde male o è giù, si scrive solo il meta con "stato": "errore"
  e si esce senza toccare i dati esistenti (nessun peggioramento silenzioso).
- Nessuna affiliazione, nessun link ai book: si leggono prezzi, non si promuove nulla.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = "https://odss-api.com/api/v1"
UA = {"User-Agent": "predictor-analisi/1.0 (analysis-only; 18+; ADM)", "Accept": "application/json"}

# 🆕 13/11-b tetto richieste per run — CALCOLATO SUL FREE TIER (500/mese)
#   4 run/giorno × 3 richieste × 30 gg = 360/mese → resta ~140 di margine
#   (2 = 240/mese: troppo prudente, copriva 1 sola lega; 4 = 480/mese: rischio di sforare
#    nei mesi da 31 giorni e con run manuali extra; 6 = 720/mese: fuori dal free tier)
MAX_CALLS_PER_RUN = 3
# 💰 TETTO MENSILE DI SICUREZZA: se il mese sta per esaurirsi, lo script si ferma da solo.
#    Il contatore vive in data/quote_adm_usage.json e si azzera al cambio di mese.
MONTHLY_BUDGET = 480

# 🆕 14/11 chiavi CANONICHE della fonte (documentate, non da indovinare):
#   "1x2" · "ou" (over/under, CON linea 2.5) · "btts" (GG/NG). NON esiste "over_under".
MERCATI = ("1x2", "ou")


def _get(path: str, params: dict | None = None, key: str | None = None, timeout: int = 25):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(url, headers=dict(UA))
    if key:
        req.add_header("x-api-key", key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def copertura():
    """Endpoint pubblico, senza chiave: serve a capire se la fonte è viva."""
    try:
        d = _get("/coverage")
        return {"ok": True, "italy": d.get("regions", {}).get("italy"), "total": d.get("total")}
    except Exception as e:
        return {"ok": False, "errore": str(e)}


def stato():
    try:
        d = _get("/status")
        return {"ok": True, "stato": d.get("status"), "live": d.get("liveEnabled"),
                "scan_s": d.get("scanIntervalSeconds")}
    except Exception as e:
        return {"ok": False, "errore": str(e)}


# 🆕 14/11 la fonte filtra la lega per SOTTOSTRINGA sul nome reale del listino (spesso localizzato).
#   "Friendlies" NON esiste: i nomi veri sono "International Friendlies", "Club Friendlies", ecc.
#   "Nations League" esiste ma ci sono anche "UEFA Nations League", "Uefa Nations League", "CONCACAF...".
#   Qui ogni nostra lega si traduce in una query che la trova davvero.
LEGA_QUERY = {
    "Friendlies": "international friendlies",
    "Nations League": "nations league",
    "Serie A": "serie a",
    "Serie B": "serie b",
    "LaLiga": "laliga",
    "LaLiga 2": "laliga 2",
    "Bundesliga": "bundesliga",
    "Bundesliga 2": "2. bundesliga",
    "Ligue 1": "ligue 1",
    "Ligue 2": "ligue 2",
    "Premier League": "premier league",
    "Championship": "championship",
    "Eredivisie": "eredivisie",
    "Primeira Liga": "primeira liga",
    "Super Lig": "super lig",
    "Champions League": "champions league",
    "Europa League": "europa league",
}


def _num(x):
    try:
        v = float(x)
        return v if v > 1.05 else None
    except Exception:
        return None


def miglior_quota(outcomes: dict, esiti: list[str]):
    """Data {HOME: 2.1, DRAW: 3.4, AWAY: 3.6} → miglior quota per ciascun esito richiesto."""
    best = {}
    for k in esiti:
        v = _num(outcomes.get(k))
        if v:
            best[k] = v
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=8, help="quanti giorni di finestra leggere")
    ap.add_argument("--league", default=None, help="filtra una lega (default: tutte)")
    a = ap.parse_args()

    key = os.environ.get("ODSS_API_KEY") or os.environ.get("ODDS_ADM_KEY")
    out_csv = DATA / "quote_adm.csv"
    meta_p = DATA / "quote_adm_meta.json"
    usage_p = DATA / "quote_adm_usage.json"

    # 💰 contatore mensile (si azzera da solo al cambio di mese)
    oggi = dt.date.today()
    mese = oggi.strftime("%Y-%m")
    usate_mese = 0
    try:
        if usage_p.exists():
            u = json.loads(usage_p.read_text())
            if u.get("mese") == mese:
                usate_mese = int(u.get("usate") or 0)
    except Exception:
        usate_mese = 0
    restanti = max(0, MONTHLY_BUDGET - usate_mese)
    cap_run = min(MAX_CALLS_PER_RUN, restanti)
    print(f"💰 budget mese {mese}: usate {usate_mese}/{MONTHLY_BUDGET} → richieste disponibili in questa run: {cap_run}")

    print("🇮🇹 Quote ADM — fonte: aggregatore operatori con licenza ADM")
    cov = copertura()
    print(f"   copertura: {cov}")

    if not key:
        meta = {"aggiornato": dt.datetime.now().isoformat(timespec="seconds"),
                "stato": "senza_chiave", "copertura": cov,
                "nota": "ODSS_API_KEY non impostata: nessun dato ADM scaricato. "
                        "Il sito continua con le quote best-price attuali."}
        if not a.dry_run:
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        print("⚠️  SKIP: manca ODSS_API_KEY. Nessun file di quote ADM scritto.")
        print("    Per attivarlo: chiave free su odss-api.com (500 req/mese, senza carta)")
        print("    poi  export ODSS_API_KEY=odss_live_...  (o secret del repo).")
        return 0

    if cap_run <= 0:
        meta = {"aggiornato": dt.datetime.now().isoformat(timespec="seconds"),
                "stato": "budget_esaurito", "mese": mese, "usate_mese": usate_mese,
                "tetto_mensile": MONTHLY_BUDGET,
                "nota": "Budget mensile del free tier esaurito: nessuna richiesta in questa run. "
                        "Si riprende il mese prossimo (il contatore si azzera da solo)."}
        if not a.dry_run:
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        print(f"⏸  BUDGET ESAURITO ({usate_mese}/{MONTHLY_BUDGET}): nessuna richiesta fatta.")
        return 0

    st = stato()
    print(f"   stato feed: {st}")

    # partite su cui vale la pena interrogare (solo quelle con quote nel nostro CSV)
    fx = DATA / "fixtures_all_2627.csv"
    partite = []
    if fx.exists():
        d = pd.read_csv(fx, low_memory=False)
        col_data = next((c for c in ("Date", "data", "Data") if c in d.columns), None)
        if col_data:
            d[col_data] = pd.to_datetime(d[col_data], errors="coerce", dayfirst=True)  # gg/mm/aaaa
            oggi = pd.Timestamp(dt.date.today())
            d = d[(d[col_data] >= oggi) & (d[col_data] <= oggi + pd.Timedelta(days=a.days))]
            print(f"   partite nella finestra: {len(d)}")

    calls = 0
    righe = []
    # 1 lega × 2 mercati = 2 richieste esatte (tetto MAX_CALLS_PER_RUN)
    mercati = ["1x2", "ou"] if not a.league else ["1x2"]
    for league in ([a.league] if a.league else []):
        pass

    # 🆕 13/11-b PRIORITÀ: prima le leghe dove abbiamo GIOCATE attive (è lì che serve la quota ADM),
    # poi il resto della finestra. Altrimenti si consumavano richieste su leghe senza valore.
    leghe_da_chiedere = []   # nomi NOSTRI (poi tradotti con LEGA_QUERY)
    gj = DATA / "giocata_multi.csv"
    if gj.exists():
        try:
            g = pd.read_csv(gj, low_memory=False)
            g = g[g["tipo"].isin(["SINGOLA", "RADDOPPIO"])]
            for le in g["lega"].astype(str):
                for parte in le.split("+"):
                    parte = parte.strip()
                    if parte and parte not in leghe_da_chiedere:
                        leghe_da_chiedere.append(parte)
        except Exception:
            pass
    fc = DATA / "forecast_multi.csv"
    if fc.exists():
        try:
            for le in pd.read_csv(fc, low_memory=False)["lega"].dropna().astype(str).unique():
                if le not in leghe_da_chiedere:
                    leghe_da_chiedere.append(le)
        except Exception:
            pass
    print(f"   ordine leghe: {leghe_da_chiedere[:4]}")
    if a.league:
        leghe_da_chiedere = [a.league]
    for lega in leghe_da_chiedere:
        if calls >= cap_run:
            print(f"   ⏹ stop a {calls} richieste (tetto run: {MAX_CALLS_PER_RUN}, budget mese: {restanti})")
            break
        for mercato in mercati:
            if calls >= cap_run:
                break
            q_lega = LEGA_QUERY.get(lega, lega)
            try:
                calls += 1
                d = _get("/odds", {"sport": "calcio", "league": q_lega, "market": mercato, "limit": 50}, key=key)
            except urllib.error.HTTPError as e:
                print(f"   ⚠️ {lega}/{mercato}: HTTP {e.code}")
                continue
            except Exception as e:
                print(f"   ⚠️ {lega}/{mercato}: {e}")
                continue
            n_ev = 0
            for ev in d.get("odds", []):
                books = [b for b in (ev.get("bookmakers") or []) if b.get("playable_it") is True]
                if not books:
                    continue
                # esiti canonici della fonte: 1x2 = HOME/DRAW/AWAY · ou = OVER/UNDER · btts = YES/NO
                esiti = {"1x2": ["HOME", "DRAW", "AWAY"], "ou": ["OVER", "UNDER"],
                         "btts": ["YES", "NO"]}.get(mercato, [])
                # 🆕 14/11 UNA RIGA PER ESITO (non solo il migliore): senza l'esito una quota
                #   "2.5" non si sa se e' Over o Under, e il confronto con la giocata sarebbe sbagliato.
                for k in esiti:
                    best, best_book = None, None
                    for b in books:
                        v = _num((b.get("outcomes") or {}).get(k))
                        if v and (best is None or v > best):
                            best, best_book = v, b.get("key")
                    if best:
                        righe.append({"data": (ev.get("commence_time") or "")[:10],
                                      "lega": ev.get("league") or lega,
                                      "partita": ev.get("event") or "",
                                      "mercato": {"ou": "2.5", "btts": "gg"}.get(mercato, mercato)
                                                 if mercato != "1x2" else "1x2",
                                      "esito": {"ou": {"OVER": "O2.5", "UNDER": "U2.5"},
                                                "btts": {"YES": "GG", "NO": "NG"},
                                                "1x2": {"HOME": "1", "DRAW": "X", "AWAY": "2"}}
                                               .get(mercato, {}).get(k, k),
                                      "quota_adm_best": round(best, 2),
                                      "book": best_book, "n_book": len(books),
                                      "aggiornato": dt.datetime.now().isoformat(timespec="seconds")})
                n_ev += 1
            print(f"   ✅ {lega} [{q_lega}]/{mercato}: {n_ev} eventi, {len(righe)} quote (richieste: {calls})")
            time.sleep(0.4)

    # 🆕 14/11 dedup PRIMA di contare (il meta diceva 176 "righe" mentre il CSV ne aveva 22)
    df_out = pd.DataFrame(righe).drop_duplicates(subset=["data", "partita", "mercato", "esito"]) if righe else None
    meta = {"aggiornato": dt.datetime.now().isoformat(timespec="seconds"),
            "stato": "ok" if righe else "vuoto", "richieste_usate": calls,
            "quote": len(righe), "righe": (len(df_out) if df_out is not None else 0),
            "copertura": cov, "feed": st}
    if a.dry_run:
        print(f"\n🔍 dry-run: {len(righe)} righe, nessun file scritto")
        for r in righe[:8]:
            print("   ", r)
        return 0
    if righe:
        df_out.to_csv(out_csv, index=False)
        print(f"💾 {out_csv} — {len(df_out)} righe (solo book ADM, playable_it=true)")
    else:
        print("ℹ️ nessuna quota ADM ottenuta: il file precedente (se c'è) resta intatto")
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    try:
        usage_p.write_text(json.dumps({"mese": mese, "usate": usate_mese + calls,
                                       "aggiornato": dt.datetime.now().isoformat(timespec="seconds")},
                                      ensure_ascii=False, indent=1))
        print(f"💰 contatore mese: {usate_mese + calls}/{MONTHLY_BUDGET}")
    except Exception as e:
        print("  ⚠️ contatore non salvato:", e)
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (usato in _get)
    sys.exit(main())
