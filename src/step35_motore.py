#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step35_motore.py — IL MOTORE DEI PRONOSTICI (non delle scommesse)
=================================================================
IDEA
    Il sito aveva un difetto di impostazione: partiva dal 1X2 e cercava il
    "valore" dentro quel mercato. Cosi' il pronostico migliore della giornata
    poteva essere scartato solo perche' la sua quota non era conveniente.

    Questo script ribalta la logica. Per OGNI partita del palinsesto valuta
    tutti i mercati disponibili e pubblica l'esito piu' probabile, con la sua
    probabilita'. Nessun filtro di quota, nessun filtro di EV: se il pronostico
    piu' solido della partita e' un Over 2.5 al 74%, quello viene pubblicato.

    Il "valore" (EV, stake) resta un'altra cosa e vive altrove. Qui si risponde
    a una domanda sola: "qual e' l'esito piu' probabile di questa partita,
    su tutti i mercati che sappiamo valutare?"

MERCATI (scelta utente 16/11)
    1X2 ................. 1 / X / 2
    Over/Under 2.5 ...... O2.5 / U2.5
    GG/NG ............... GG / NG
    Sono i tre con storico solido e verifica automatica affidabile.

SELEZIONE (scelta utente: "tutti i pronostici, con la loro %")
    Nessuna soglia: ogni partita produce una riga. La probabilita' e' sempre
    visibile, cosi' il lettore sa quanto e' solida la stima. La pagina ordina
    per probabilita', ma non nasconde nulla.

VERIFICA (per il bilancio immediato)
    Il motore salva la sua previsione PRIMA delle partite. Dopo, quando gli
    esiti sono disponibili, li recupera da due fonti indipendenti (file locali
    gia' popolati dagli altri step, e API pubblica ESPN) e scrive il bilancio.
    Nessuna auto-valutazione compiacente: se non trova l'esito, segna "n.d.".

FILE PRODOTTI (tutti in data/)
    pronostico_motore.csv       una riga per partita: il pronostico migliore
    pronostico_motore_storico.csv  accumulo in append (mai sovrascritto)
    bilancio_motore.csv         esiti + hit + riepilogo per giorno
    bilancio_motore.json        sintesi per la pagina

USO
    python3 src/step35_motore.py                      # pronostici di oggi
    python3 src/step35_motore.py --bilancio           # solo bilancio
    python3 src/step35_motore.py --date 2026-11-20    # una data specifica
"""

import argparse
import csv
import difflib
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

OUT_OGGI = DATA / "pronostico_motore.csv"
OUT_STO = DATA / "pronostico_motore_storico.csv"
OUT_BIL = DATA / "bilancio_motore.csv"
OUT_JSON = DATA / "bilancio_motore.json"

# stesse leghe/slug di step20 (risultati ESPN)
SLUGS = {"ita.1": "Serie A", "ita.2": "Serie B", "eng.1": "Premier League", "eng.2": "Championship",
         "esp.1": "LaLiga", "esp.2": "LaLiga 2", "ger.1": "Bundesliga", "ger.2": "Bundesliga 2",
         "fra.1": "Ligue 1", "fra.2": "Ligue 2", "ned.1": "Eredivisie", "por.1": "Primeira Liga",
         "tur.1": "Süper Lig", "uefa.champions": "Champions League", "uefa.europa": "Europa League",
         "fifa.friendly": "Friendlies", "uefa.nations": "Nations League",
         "uefa.nations.league": "Nations League", "concacaf.nations": "Nations League",
         "uefa.europa.conf": "Conference League"}


def nn(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


# ---------------------------------------------------------------- 1. PRONOSTICI
def costruisci_pronostici():
    """Legge forecast_multi.csv e sceglie, per ogni partita, l'esito piu' probabile
    su TUTTI i mercati. Ritorna un DataFrame."""
    fp = DATA / "forecast_multi.csv"
    if not fp.exists():
        print("❌ manca data/forecast_multi.csv (lo produce weekly_multi.py)")
        return None
    f = pd.read_csv(fp)
    need = {"partita", "lega", "orario", "p1%", "pX%", "p2%", "Over2.5%", "BTTS%"}
    manc = need - set(f.columns)
    if manc:
        print(f"❌ colonne mancanti in forecast_multi: {manc}")
        return None

    righe = []
    for _, r in f.iterrows():
        cand = []
        # --- 1X2 ---
        for esito, col in (("1", "p1%"), ("X", "pX%"), ("2", "p2%")):
            try:
                p = float(r[col]) / 100.0
            except Exception:
                continue
            if 0 < p < 1:
                cand.append(("1X2", esito, p))
        # --- Over/Under 2.5 ---
        try:
            po = float(r["Over2.5%"]) / 100.0
            if 0 < po < 1:
                cand.append(("O/U 2.5", "Over 2.5", po))
                cand.append(("O/U 2.5", "Under 2.5", 1.0 - po))
        except Exception:
            pass
        # --- GG/NG ---
        try:
            pg = float(r["BTTS%"]) / 100.0
            if 0 < pg < 1:
                cand.append(("GG/NG", "GG", pg))
                cand.append(("GG/NG", "NG", 1.0 - pg))
        except Exception:
            pass
        if not cand:
            continue
        cand.sort(key=lambda x: -x[2])
        mercato, esito, p = cand[0]
        # margine sul secondo: quanto e' netta la scelta
        secondo = cand[1][2] if len(cand) > 1 else 0.0
        # quota di riferimento, se disponibile, per la colonna "quota"
        q = ""
        try:
            if mercato == "1X2":
                q = r.get("quota_best", "")
            elif esito == "Over 2.5":
                q = r.get("quota_O25_best", "")
            elif esito == "Under 2.5":
                q = r.get("quota_U25_best", "")
            elif esito == "GG":
                q = r.get("quota_GG_best", "")
            elif esito == "NG":
                q = r.get("quota_NG_best", "")
        except Exception:
            q = ""
        # data ISO dall'orario "dd/mm HH:MM"
        try:
            dd, mm = str(r["orario"]).split(" ")[0].split("/")
            iso = f"2026-{mm}-{dd}"
            ora = str(r["orario"]).split(" ")[1]
        except Exception:
            iso, ora = "", ""
        # 🆕 19/11 CALCIO D'INIZIO in UTC: l'orario del forecast è Europe/Rome, i timestamp
        #    delle run sono UTC. Senza conversione si sbaglia di 1-2 ore e si rischia di
        #    includere una rilevazione fatta DOPO l'inizio (guardare il futuro).
        kick = ""
        try:
            _loc = datetime.strptime(f"{iso} {ora}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Rome"))
            kick = _loc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            kick = ""
        righe.append({
            "data": iso, "ora": ora, "kickoff_utc": kick,
            "lega": r["lega"], "partita": r["partita"],
            "mercato": mercato, "esito": esito,
            "prob_pct": round(p * 100, 1),
            "margine_pp": round((p - secondo) * 100, 1),
            "quota": q,
            "p1": r.get("p1%", ""), "pX": r.get("pX%", ""), "p2": r.get("p2%", ""),
            "p_over": r.get("Over2.5%", ""), "p_gg": r.get("BTTS%", ""),
        })
    return pd.DataFrame(righe)


def salva_pronostici(df, quando=None):
    # 🆕 19/11 timestamp SEMPRE in UTC: servono per congelare il pronostico prima del via
    quando = quando or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    df = df.copy()
    df["rilevato"] = quando
    df.to_csv(OUT_OGGI, index=False)
    # accumulo: dedup su (data, partita, mercato, esito), tiene l'ultima
    try:
        if OUT_STO.exists():
            old = pd.read_csv(OUT_STO)
            comb = pd.concat([old, df], ignore_index=True)
        else:
            comb = df
        comb = comb.drop_duplicates(subset=["data", "partita", "mercato", "esito"], keep="last")
        comb.sort_values(["data", "partita"], inplace=True)
        comb.to_csv(OUT_STO, index=False)
    except Exception as e:
        print(f"   ⚠️ storico non aggiornato: {e}")
    print(f"💾 {OUT_OGGI.name}: {len(df)} pronostici · storico {len(comb)} righe")


# ---------------------------------------------------------------- 2. ESITI
def esiti_da_espn(data_iso):
    """Risultati reali da ESPN (gratis, senza chiave). Ritorna {(lega,nn_casa,nn_ospite):(gol_casa,gol_ospite)}."""
    ds = data_iso.replace("-", "")
    res = {}
    for slg, lg in SLUGS.items():
        try:
            req = urllib.request.Request(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slg}/scoreboard?dates={ds}",
                headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=20))
        except Exception:
            continue
        for ev in d.get("events", []):
            try:
                c = ev["competitions"][0]
                st = c["status"]["type"]["name"]
                if "FULL" not in st and "FINAL" not in st:
                    continue
                h = next(x for x in c["competitors"] if x["homeAway"] == "home")
                aw = next(x for x in c["competitors"] if x["homeAway"] == "away")
                res[(lg, nn(h["team"]["displayName"]), nn(aw["team"]["displayName"]))] = (
                    int(float(h.get("score", 0))), int(float(aw.get("score", 0))))
            except Exception:
                continue
    return res


def esiti_da_locali(data_iso):
    """Risultati gia' presenti in data/matches.csv (football-data), se la data e' coperta."""
    res = {}
    mp = DATA / "matches.csv"
    if not mp.exists():
        return res
    try:
        m = pd.read_csv(mp, low_memory=False)
        m["Date"] = pd.to_datetime(m["Date"], errors="coerce")
        m = m[(m["Date"].dt.strftime("%Y-%m-%d") == data_iso) & m["FTHG"].notna() & m["FTAG"].notna()]
        for _, r in m.iterrows():
            res[(r.get("League"), nn(r["HomeTeam"]), nn(r["AwayTeam"]))] = (
                int(r["FTHG"]), int(r["FTAG"]))
    except Exception:
        pass
    return res


def esito_osservato(mercato, esito, gh, ga):
    """True/False se il pronostico era corretto, None se non verificabile."""
    tot = gh + ga
    if mercato == "1X2":
        y = "1" if gh > ga else ("2" if gh < ga else "X")
        return esito == y
    if mercato == "O/U 2.5":
        if esito == "Over 2.5":
            return tot > 2.5
        return tot < 2.5
    if mercato == "GG/NG":
        gg = gh > 0 and ga > 0
        return gg if esito == "GG" else (not gg)
    return None


# ---------------------------------------------------------------- 3. BILANCIO
def pronostico_congelato(st):
    """🆕 19/11 IL PRONOSTICO CHE IL SITO MOSTRAVA PRIMA DEL VIA.

    REGOLA (scelta utente 19/11)
        Per ogni partita si tiene l'ULTIMA rilevazione fatta PRIMA del calcio d'inizio.
        E' la piu' informata: se il pronostico e' cambiato durante la giornata, vuol dire
        che sono arrivate notizie, movimenti di quota o formazioni ufficiali. Quella e'
        la versione da cui il lettore ha deciso, quindi quella va conteggiata.

    PERCHE' SERVE
        Senza questo, il bilancio contava piu' righe per la stessa partita (una per ogni
        run in cui il pronostico cambiava) e finiva per pesare due volte partite come
        Bosnia-Romania e Wales-Portugal, dove il motore era passato da GG a Over 2.5.
        Due mercati correlati sulla stessa partita = due successi facili da incassare.
        MISURATO: 38 righe di bilancio su 36 partite distinte, accuratezza gonfiata
        dal 56,3% al 58,8%.

    SICUREZZA
        Si scartano le rilevazioni con timestamp successivo al via (guarderebbero il
        futuro). Se una partita non ha NESSUNA rilevazione prima del via, resta fuori
        dal bilancio: meglio un caso in meno che un caso disonesto.
    """
    if st.empty:
        return st
    d = st.copy()
    d["rilevato_dt"] = pd.to_datetime(d["rilevato"], errors="coerce", utc=True)
    if "kickoff_utc" in d.columns:
        d["kick_dt"] = pd.to_datetime(d["kickoff_utc"], errors="coerce", utc=True)
    else:
        # 🆕 19/11 righe scritte PRIMA di questa modifica: niente kickoff. Serve un NaT
        #   CONSAPEVOLE DEL FUSO, altrimenti il confronto con rilevato_dt (UTC) solleva
        #   "Cannot compare tz-naive and tz-aware" e il bilancio non si aggiorna piu'.
        #   (bug trovato dal test sullo storico reale di 266 righe, non in produzione)
        d["kick_dt"] = pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns, UTC]")
    # se manca il calcio d'inizio (righe vecchie), si tiene l'ultima rilevazione e basta
    noto = d["kick_dt"].notna()
    prima = d[noto & (d["rilevato_dt"] < d["kick_dt"])].copy()
    senza_via = d[~noto].copy()
    senza_via = senza_via.sort_values("rilevato_dt").groupby(
        ["data", "partita"], as_index=False).last()
    cong = (pd.concat([prima, senza_via], ignore_index=True)
              .sort_values("rilevato_dt")
              .groupby(["data", "partita"], as_index=False).last())
    n_escluse = 0
    if noto.any():
        tutte = d[d["rilevato_dt"].notna()]
        n_escluse = len(tutte) - len(prima) - len(senza_via)
    return cong, n_escluse


def aggiorna_bilancio(giorni_indietro=7):
    if not OUT_STO.exists():
        print("❌ nessuno storico pronostici: niente bilancio")
        return None
    st = pd.read_csv(OUT_STO)
    st["data"] = st["data"].astype(str)
    # 🆕 19/11 si conteggia SOLO l'ultimo pronostico fatto prima del via (una riga per partita)
    st, _n_escl = pronostico_congelato(st)
    print(f"   🧊 pronostici congelati prima del via: {len(st)} partite"
          + (f" · {_n_escl} rilevazioni scartate (dopo il via o sostituite)" if _n_escl else ""))
    oggi = datetime.now().date()
    date_da_verificare = sorted({
        d for d in st["data"].unique()
        if d and d != "nan" and str(oggi - timedelta(days=giorni_indietro)) <= d < str(oggi)
    })
    # includi anche oggi: le partite gia' finite devono entrare subito
    date_da_verificare.append(str(oggi))

    righe = []
    for d in date_da_verificare:
        sub = st[st["data"] == d]
        if sub.empty:
            continue
        res = esiti_da_locali(d)
        espn = None
        for _, r in sub.iterrows():
            aggancio = None
            parti = str(r["partita"]).split(" - ")
            if len(parti) < 2:
                continue
            ch, ca = nn(parti[0]), nn(parti[-1])
            # 1) match esatto sulle fonti locali
            for (lg, h, a), sc in res.items():
                if h == ch and a == ca:
                    aggancio = sc
                    break
            # 2) ESPN (scaricato una volta sola per data, alla prima necessita')
            if aggancio is None and (r["data"] == str(oggi) or True):
                if espn is None:
                    espn = esiti_da_espn(d)
                for (lg, h, a), sc in espn.items():
                    if h == ch and a == ca:
                        aggancio = sc
                        break
            if aggancio is None:
                # 3) fuzzy, come step20 (nomi tradotti diversi)
                for (lg, h, a), sc in {**res, **(espn or {})}.items():
                    if difflib.SequenceMatcher(None, h + "vs" + a, ch + "vs" + ca).ratio() > 0.62:
                        aggancio = sc
                        break
            ok = None
            if aggancio is not None:
                ok = esito_osservato(r["mercato"], r["esito"], *aggancio)
            righe.append({
                "data": d, "lega": r["lega"], "partita": r["partita"],
                "mercato": r["mercato"], "esito": r["esito"],
                "prob_pct": r["prob_pct"], "margine_pp": r["margine_pp"],
                "gol_casa": aggancio[0] if aggancio else "",
                "gol_ospite": aggancio[1] if aggancio else "",
                "risultato": (f"{aggancio[0]}-{aggancio[1]}" if aggancio else "n.d."),
                "colto": "" if ok is None else int(ok),
                "verificato": 0 if ok is None else 1,
            })
    if not righe:
        print("ℹ️ nessun pronostico verificabile in archivio")
        return None
    b = pd.DataFrame(righe)
    b.to_csv(OUT_BIL, index=False)

    v = b[b["verificato"] == 1]
    per_giorno = []
    for d, s in v.groupby("data"):
        per_giorno.append({
            "data": d, "pronostici": int(len(s)), "colti": int(s["colto"].sum()),
            "acc_pct": round(float(s["colto"].mean() * 100), 1),
            "prob_media": round(float(s["prob_pct"].mean()), 1),
        })
    tot = {
        "aggiornato": datetime.now().isoformat(timespec="seconds"),
        "pronostici_totali": int(len(b)),
        "partite_distinte": int(b.groupby(["data", "partita"]).ngroups),
        "regola": "si conteggia l'ultimo pronostico pubblicato prima del calcio d'inizio",
        "verificati": int(len(v)),
        "colti": int(v["colto"].sum()) if len(v) else 0,
        "acc_pct": round(float(v["colto"].mean() * 100), 1) if len(v) else None,
        "prob_media_pct": round(float(v["prob_pct"].mean()), 1) if len(v) else None,
        "scarto_pp": (round(float(v["colto"].mean() * 100 - v["prob_pct"].mean()), 1)
                      if len(v) else None),
        "per_mercato": ({str(k): {"n": int(len(s)), "acc_pct": round(float(s["colto"].mean() * 100), 1)}
                         for k, s in v.groupby("mercato")} if len(v) else {}),
        "per_giorno": per_giorno,
        "non_verificabili": int((b["verificato"] == 0).sum()),
    }
    OUT_JSON.write_text(json.dumps(tot, indent=1, ensure_ascii=False))
    print(f"📊 BILANCIO: {tot['verificati']} verificati · colti {tot['colti']} "
          f"({tot['acc_pct']}%) · prob media dichiarata {tot['prob_media_pct']}% · "
          f"scarto {tot['scarto_pp']:+}pp" if tot["verificati"] else "📊 BILANCIO: nessun esito ancora")
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="data ISO per i pronostici (default: tutte le partite del forecast)")
    ap.add_argument("--bilancio", action="store_true", help="aggiorna solo il bilancio")
    ap.add_argument("--giorni", type=int, default=7, help="quanti giorni indietro verificare")
    a = ap.parse_args()

    if a.bilancio:
        aggiorna_bilancio(a.giorni)
        return 0

    df = costruisci_pronostici()
    if df is None:
        return 1
    if a.date:
        df = df[df["data"] == a.date]
    if df.empty:
        print("ℹ️ nessun pronostico: forecast_multi.csv non copre le date richieste")
        return 0
    salva_pronostici(df)

    print(f"\n🎯 PRONOSTICI (il piu' probabile per partita, tutti i mercati):")
    top = df.sort_values("prob_pct", ascending=False).head(10)
    for _, r in top.iterrows():
        print(f"   {r['data']} {r['partita'][:34]:34s} → {r['mercato']:9s} {r['esito']:10s} "
              f"{r['prob_pct']:5.1f}%  (margine +{r['margine_pp']:.1f}pp)")
    print(f"\n   distribuzione per mercato: {df['mercato'].value_counts().to_dict()}")
    print(f"   probabilità media: {df['prob_pct'].mean():.1f}%")

    aggiorna_bilancio(a.giorni)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
