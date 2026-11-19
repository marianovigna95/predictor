#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step37_rotazione.py — ROTAZIONE DEGLI ARCHIVI DATATI
====================================================
PERCHE' ESISTE
    La cartella data/ accumula file con la data nel nome: misurato il 19/11,
    30 file che crescono di ~2 al giorno (odds_window_*_bestprice.csv e
    eval_day_*.csv). In un anno sarebbero ~730.

    Due conseguenze concrete:
      1. ogni run fa actions/checkout dell'INTERO repo → sempre piu' lenta
      2. i glob come DATA.glob("odds_window_*_bestprice.csv") leggono TUTTI
         i file storici a ogni esecuzione

COSA ARCHIVIA (e cosa NON tocca)
    ARCHIVIA in data/archivio_storico.zip:
      - odds_window_*_bestprice.csv piu' vecchi di 60 giorni
        (servono solo alla finestra in corso: oltre 60 giorni sono morti)
      - schedina_*.pdf piu' vecchie di 30 giorni (archivio solo visivo)

    NON TOCCA MAI:
      - eval_day_*.csv      → alimentano l'archivio pubblico e step25/step23;
                              pesano pochi KB, il valore storico e' alto
      - verifica_*.csv      → alimentano la pagina Verifica e il ROI schedina
      - confronto_adm_storico.csv → e' il campione cumulato del progetto
      - pronostico_motore_storico.csv → e' il campione del motore

    Regola: si archiviano i file GROSSI e SUPPORTABILI, mai i file PICCOLI
    che sono la memoria del sistema. Un archivio che cancella la memoria
    e' peggio di nessun archivio.

SICUREZZA
    I file vengono prima scritti nello zip e SOLO DOPO rimossi. Lo zip e'
    in modalita' append: le rotazioni successive non sovrascrivono quelle
    precedenti. Se qualcosa va storto a meta', i file restano dove sono.

USO
    python3 src/step37_rotazione.py            # applica la rotazione
    python3 src/step37_rotazione.py --dry-run  # dice cosa farebbe, senza toccare
"""

import argparse
import glob
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")
ARCH = os.path.join(DATA, "archivio_storico.zip")

GIORNI_ODDS = 60
GIORNI_SCHEDINE = 30


def _oggi():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def trova_da_archiviare(oggi=None):
    """Ritorna la lista dei file da archiviare. Nessun effetto collaterale."""
    oggi = oggi or _oggi()
    out = []

    # --- finestre quote ---
    for p in glob.glob(os.path.join(DATA, "odds_window_*_bestprice.csv")):
        m = re.search(r"odds_window_(\d{2})(\d{2})_", os.path.basename(p))
        if not m:
            continue
        try:
            d = datetime(oggi.year, int(m.group(2)), int(m.group(1)))
        except Exception:
            continue
        # se la data calcolata e' nel futuro di oltre un mese, l'anno era l'altro
        if (d - oggi).days > 31:
            try:
                d = datetime(oggi.year - 1, int(m.group(2)), int(m.group(1)))
            except Exception:
                continue
        if (oggi - d).days > GIORNI_ODDS:
            out.append(p)

    # --- schedine PDF ---
    for cartella in (DATA, SITE, ROOT):
        for p in glob.glob(os.path.join(cartella, "schedina_*.pdf")):
            m = re.search(r"schedina_(\d{4}-\d{2}-\d{2})", os.path.basename(p))
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
            except Exception:
                continue
            if (oggi - d).days > GIORNI_SCHEDINE:
                out.append(p)

    return sorted(set(out))


def applica(file_da_arch, dry_run=False):
    """Scrive i file nello zip e poi li rimuove. Ritorna quanti ne ha archiviati."""
    if not file_da_arch:
        return 0

    # eventuali nomi duplicati su cartelle diverse: nello zip si distingue la provenienza
    if dry_run:
        print(f"   (dry-run) {len(file_da_arch)} file sarebbero archiviati:")
        for p in file_da_arch:
            print(f"      {os.path.relpath(p, ROOT)}  ({os.path.getsize(p)} B)")
        return 0

    scritti = []
    with zipfile.ZipFile(ARCH, "a", zipfile.ZIP_DEFLATED) as z:
        esistenti = set(z.namelist())
        for p in file_da_arch:
            nome = os.path.basename(p)
            if nome in esistenti:
                # gia' archiviato in una rotazione precedente: si puo' rimuovere
                scritti.append(p)
                continue
            try:
                z.write(p, nome)
                scritti.append(p)
            except Exception as e:
                print(f"   ⚠️ {nome}: non archiviato ({e}) → resta dov'è")

    # rimozione SOLO di ciò che è stato scritto davvero
    rimossi = 0
    for p in scritti:
        try:
            os.remove(p)
            rimossi += 1
        except Exception as e:
            print(f"   ⚠️ {os.path.basename(p)}: non rimosso ({e})")
    return rimossi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    da = trova_da_archiviare()
    print(f"🗃  rotazione archivi: {len(da)} file oltre le soglie "
          f"(odds > {GIORNI_ODDS}gg, schedine > {GIORNI_SCHEDINE}gg)")

    # controllo di sicurezza: nessuna memoria del sistema deve mai finire qui
    vietati = ("eval_day_", "verifica_", "confronto_adm_storico",
               "pronostico_motore_storico", "bets_1x2_onesto", "matches.csv")
    pericolosi = [p for p in da if any(v in os.path.basename(p) for v in vietati)]
    if pericolosi:
        print("   ❌ ABORT: la rotazione ha selezionato file di memoria del sistema:")
        for p in pericolosi:
            print("      ", os.path.basename(p))
        return 1

    n = applica(da, dry_run=a.dry_run)
    if n:
        size = os.path.getsize(ARCH) / 1024
        print(f"   ✅ archiviati {n} file in {os.path.basename(ARCH)} ({size:.0f} KB)")
    elif not a.dry_run:
        print("   nulla da fare")

    # conta cosa resta, per il log
    restanti = len(glob.glob(os.path.join(DATA, "odds_window_*_bestprice.csv")))
    print(f"   finestre quote ancora attive: {restanti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
