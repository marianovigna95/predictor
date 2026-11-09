#!/usr/bin/env python3
"""step26_telegram.py — alert Telegram (gratis, Bot API) su surebet best-price sopra soglia.
Config via env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (bot creato gratis con @BotFather)
Uso: python3 src/step26_telegram.py [--min 1.0] [--date 2026-11-09]
Chiamato automaticamente da step21 (se le env sono impostate) oppure a mano.
"""
import argparse
import datetime
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from step21_surebets import bestprice_surebets  # riusa il calcolo surebet


def send(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("⚠️ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID non impostati — alert disattivato (solo log)")
        print("   " + text.replace("\n", "\n   "))
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20).read()
    print("📨 alert Telegram inviato")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=1.0, help="soglia margine %")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    bp = bestprice_surebets(a.date)
    hot = [r for r in bp if r["margine%"] >= a.min]
    if not hot:
        print(f"nessuna surebet ≥ +{a.min}% per {a.date}")
        return
    lines = [f"⚖️ <b>Surebet {a.date}</b> (≥ +{a.min}%):"]
    for r in hot:
        lines.append(f"• {r['ora']} {r['lega']} — {r['partita']} — <b>{r['mercato']} +{r['margine%']}%</b> ({r['quote']})")
    lines.append("⚠️ Solo analisi · 18+ · ADM · autoesclusione.it · 800 558822")
    send("\n".join(lines))


if __name__ == "__main__":
    import urllib.parse
    main()
