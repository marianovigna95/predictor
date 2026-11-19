#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step36_check.py — CONTROLLO DI SALUTE DEI DATI (fallisce se sono vecchi)
=======================================================================
PERCHE' ESISTE
    Nel workflow OGNI passo ha "|| true". Se uno script si rompe, la pipeline
    resta VERDE e il sito continua a mostrare dati vecchi senza dirlo.
    E' il tipo di guasto peggiore: sembra tutto a posto.

    Questo passo e' l'unico SENZA "|| true": se i dati non sono freschi,
    la run fallisce e GitHub manda la mail. Meglio un allarme rosso che un
    sito silenziosamente fermo.

COSA CONTROLLA
    1. data/forecast_multi.csv        → il cuore dei pronostici. Se manca o ha
                                         meno di 5 partite, la run e' inutile.
    2. data/pronostico_motore.csv     → il motore. Se vuoto, la pagina e' vuota.
    3. eta' dei file                  → se l'ultima scrittura supera la soglia,
                                         i dati non si stanno aggiornando.
    4. file da 1 byte in data/        → avanzi che gonfiano i conteggi.
    5. bilancio_motore.json           → deve essere leggibile e non assurdo.

⚠️ Le soglie sono GENEROSE di proposito: questo passo deve accorgersi di un
   guasto vero (sito fermo da giorni), non di un ritardo di un'ora. Un
   controllo troppo severo che fallisce a caso e' peggio di nessun controllo,
   perché insegna a ignorare gli allarmi.

Uso: python3 src/step36_check.py [--max-ore 30]
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# (nome logico, percorso, min righe accettabili)
CRITICI = [
    ("forecast_multi.csv", os.path.join(DATA, "forecast_multi.csv"), 5),
    ("pronostico_motore.csv", os.path.join(DATA, "pronostico_motore.csv"), 5),
]
# questi possono mancare senza far fallire la run (primo avvio, dati opzionali)
OPZIONALI = [
    ("giocata_multi.csv", os.path.join(DATA, "giocata_multi.csv")),
    ("bilancio_motore.json", os.path.join(DATA, "bilancio_motore.json")),
    ("quote_adm.csv", os.path.join(DATA, "quote_adm.csv")),
]


def eta_ore(p):
    try:
        return (datetime.now(timezone.utc).timestamp() - os.path.getmtime(p)) / 3600.0
    except Exception:
        return None


def conta_righe(p):
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f) - 1        # meno l'intestazione
    except Exception:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ore", type=float, default=30.0,
                    help="eta' massima accettabile dei file critici (default 30h)")
    ap.add_argument("--no-clean", action="store_true",
                    help="non eliminare i file da 1 byte (solo segnalarli)")
    ap.add_argument("--max-fermo", type=int, default=3,
                    help="dopo quante run con forecast identico avvisare (default 3)")
    a = ap.parse_args()

    errori, avvisi = [], []

    print("🩺 CONTROLLO DI SALUTE DEI DATI")
    print(f"   soglia di freschezza: {a.max_ore:.0f} ore")

    # ---- 1. file critici: esistono, hanno righe, sono freschi ----
    for nome, p, minr in CRITICI:
        if not os.path.exists(p):
            errori.append(f"{nome}: MANCANTE")
            print(f"   ❌ {nome}: mancante")
            continue
        n = conta_righe(p)
        eta = eta_ore(p)
        stato = f"{n} righe"
        if eta is not None:
            stato += f", {eta:.1f}h fa"
        if n < minr:
            errori.append(f"{nome}: solo {n} righe (minimo {minr})")
            print(f"   ❌ {nome}: {stato} → troppo poche righe")
            continue
        if eta is not None and eta > a.max_ore:
            errori.append(f"{nome}: vecchio di {eta:.0f}h")
            print(f"   ❌ {nome}: {stato} → NON aggiornato")
            continue
        print(f"   ✅ {nome}: {stato}")

    # ---- 2. file opzionali: si segnalano, non bloccano ----
    for nome, p in OPZIONALI:
        if not os.path.exists(p):
            avvisi.append(f"{nome}: assente")
            print(f"   ⚠️  {nome}: assente (non bloccante)")
            continue
        eta = eta_ore(p)
        print(f"   ✅ {nome}: {conta_righe(p)} righe"
              + (f", {eta:.1f}h fa" if eta is not None else ""))

    # ---- 3. file da 1 byte (avanzi che gonfiano i conteggi) ----
    # 🆕 19/11 i file da 1 byte si ELIMINANO: sono avanzi del vecchio bug di step20
    #    (scriveva il CSV anche con 0 righe). Non contengono nulla, e la loro presenza
    #    gonfia i conteggi: "esiti caricati da 12 file" quando i file veri sono 9.
    #    ⚠️ step20 è già stato corretto e non li scrive più: questa è pulizia una volta sola.
    vuoti = [p for p in glob.glob(os.path.join(DATA, "*.csv"))
             if os.path.getsize(p) <= 1]
    if vuoti and not a.no_clean:
        rimossi = 0
        for p in vuoti:
            try:
                os.remove(p)
                rimossi += 1
                print(f"   🧹 rimosso file vuoto: {os.path.basename(p)}")
            except Exception as e:
                print(f"   ⚠️  {os.path.basename(p)}: non rimosso ({e})")
        if rimossi:
            print(f"   🧹 {rimossi} file da 1 byte eliminati")
        vuoti = [p for p in vuoti if os.path.exists(p)]
    if vuoti:
        avvisi.append(f"{len(vuoti)} file da 1 byte in data/")
        print(f"   ⚠️  {len(vuoti)} file da 1 byte (avanzi del vecchio bug):")
        for p in vuoti[:8]:
            print(f"      {os.path.basename(p)}")
    else:
        print("   ✅ nessun file da 1 byte in data/")

    # ---- 4. bilancio motore: leggibile e coerente ----
    bp = os.path.join(DATA, "bilancio_motore.json")
    if os.path.exists(bp):
        try:
            with open(bp) as f:
                b = json.load(f)
            ver = b.get("verificati")
            acc = b.get("acc_pct")
            if ver is not None and acc is not None:
                if not (0 <= acc <= 100):
                    errori.append(f"bilancio_motore: acc_pct={acc} fuori da [0,100]")
                    print(f"   ❌ bilancio_motore.json: acc_pct={acc} impossibile")
                else:
                    print(f"   ✅ bilancio_motore.json: {ver} verificati, acc {acc}%")
        except Exception as e:
            avvisi.append(f"bilancio_motore.json illeggibile: {e}")
            print(f"   ⚠️  bilancio_motore.json illeggibile ({type(e).__name__})")

    # ---- 5. FORECAST FERMO: il file è fresco ma il contenuto non cambia ----
    #    🆕 19/11 un file riscritto identico ogni run è "fresco" per il controllo
    #    sull'età, ma il sito mostra le stesse partite da giorni. Qui si guarda una
    #    IMPRONTA del contenuto: se non cambia per N run consecutive, si avvisa.
    #    Non fa fallire la run: a fine finestra (es. pausa nazionali) è normale.
    impronta_p = os.path.join(DATA, "forecast_impronta.json")
    fp = os.path.join(DATA, "forecast_multi.csv")
    if os.path.exists(fp):
        try:
            import hashlib
            with open(fp, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()[:12]
            st = {"impronta": h, "invariata_da": 0}
            if os.path.exists(impronta_p):
                try:
                    with open(impronta_p) as f:
                        st = json.load(f)
                except Exception:
                    pass
            if st.get("impronta") == h:
                st["invariata_da"] = int(st.get("invariata_da", 0)) + 1
            else:
                st = {"impronta": h, "invariata_da": 1}
            with open(impronta_p, "w") as f:
                json.dump(st, f)
            n_inv = st["invariata_da"]
            if n_inv >= a.max_fermo:
                avvisi.append(f"forecast invariato da {n_inv} run consecutive")
                print(f"   ⚠️  forecast_multi.csv: contenuto INVARIATO da {n_inv} run")
                print(f"      (non bloccante: può essere la pausa del campionato, "
                      f"ma se dura giorni è un sintomo)")
            else:
                print(f"   ✅ forecast_multi.csv: contenuto aggiornato (invariato da {n_inv} run)")
        except Exception as e:
            print(f"   ⚠️  impronta forecast non calcolata ({type(e).__name__})")

    # ---- verdetto ----
    print()
    if errori:
        print(f"❌ CONTROLLO FALLITO — {len(errori)} problema/i critico/i:")
        for e in errori:
            print(f"   · {e}")
        if avvisi:
            print(f"   ({len(avvisi)} avvisi non bloccanti)")
        print("\n   La run si ferma QUI di proposito: se i dati non sono freschi,")
        print("   pubblicare sarebbe peggio che non pubblicare.")
        return 1
    print(f"✅ CONTROLLO SUPERATO" + (f" · {len(avvisi)} avvisi non bloccanti" if avvisi else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
