#!/usr/bin/env python3
"""step26_telegram.py — Telegram (gratis, Bot API): alert surebet + digest giornaliero su canale.

Env (repo secrets in Settings → Secrets and variables → Actions):
  TELEGRAM_BOT_TOKEN     token del bot (@BotFather)
  TELEGRAM_CHAT_ID       chat privata (alert surebet) — id numerico tuo
  TELEGRAM_CHANNEL_ID    id del canale (es. -100xxxxxxxxxx) — digest giornaliero del sito

Digest (giocate del giorno + esiti verificati ieri + top PPA) viene mandato:
- al run delle 23:00 IT (verifica sera), oppure
- a ogni Run workflow manuale (per testare subito), oppure con --digest.

Uso: python3 src/step26_telegram.py [--min 1.0] [--date 2026-11-09] [--digest]
"""
import argparse
import datetime
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "src"))
from step21_surebets import bestprice_surebets  # riusa il calcolo surebet

FOOTER = "⚠️ Solo analisi, mai certezze · 18+ · ADM · autoesclusione.it · 800 558822"


def _send(chat, text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok or not chat:
        print("⚠️ TELEGRAM_BOT_TOKEN/chat non impostati — solo log:")
        print("   " + text.replace("\n", "\n   "))
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20).read()
    print(f"📨 Telegram inviato a {chat}")
    return True


def send_alert(text):
    return _send(os.environ.get("TELEGRAM_CHAT_ID"), text)


def send_channel(text):
    return _send(os.environ.get("TELEGRAM_CHANNEL_ID") or os.environ.get("TELEGRAM_CHAT_ID"), text)


def digest(a):
    """Digest del giorno: giocate EV>0, esiti verificati (ieri), top PPA."""
    d = a.date
    lines = [f"📋 <b>Predictor — digest {d}</b>"]
    # 🎯 giocate del giorno (EV>0-only, Singola+Raddoppio)
    try:
        gj = pd.read_csv(DATA / "giocata_multi.csv", dtype=str).fillna("")
        day = gj[gj["data"] == d] if "data" in gj.columns else gj
        if len(day):
            lines.append("\n🎯 <b>Giocate del giorno (EV&gt;0):</b>")
            for _, r in day.iterrows():
                lines.append(f"• {r.get('tipo','')} — {r.get('partita', r.get('lega',''))} — <b>{r.get('mercato','')}</b> "
                             f"{r.get('esito','')} @ {r.get('quota_best', r.get('quota',''))} (EV {r.get('EV%','')})")
        else:
            lines.append("\n🎯 Oggi nessuna giocata EV&gt;0 (stake 0 — regola del sito).")
    except Exception as e:
        print(f"digest giocata: {e}")
    # ✅ verifica esiti di ieri
    try:
        y = (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()
        ev = pd.read_csv(DATA / f"eval_day_{y}.csv")
        ok = int((ev["esito"] == "✅").sum()) if "esito" in ev.columns else 0
        ko = int((ev["esito"] == "❌").sum()) if "esito" in ev.columns else 0
        lines.append(f"\n✅ <b>Verifica {y}:</b> {ok} vincenti / {ko} perdenti su {len(ev)} giocate")
    except Exception as e:
        print(f"digest verifica: {e}")
    # ⚡ top PPA (p>=60%)
    try:
        fc = pd.read_csv(DATA / "forecast_multi.csv", dtype=str).fillna("")
        fc["conf"] = pd.to_numeric(fc.get("conf%"), errors="coerce")
        top = fc[fc["conf"] >= 60].sort_values("conf", ascending=False).head(5)
        if len(top):
            lines.append("\n⚡ <b>Top PPA (p≥60%):</b>")
            for _, r in top.iterrows():
                lines.append(f"• {r.get('orario','')} {r.get('partita','')} — {r.get('pronostico','')} {r['conf']}% @ {r.get('quota_best','')}")
    except Exception as e:
        print(f"digest ppa: {e}")
    lines.append("\n🌐 " + "https://marianovigna95.github.io/predictor/")
    lines.append(FOOTER)
    send_channel("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=1.0, help="soglia margine %")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--digest", action="store_true", help="forza invio digest")
    a = ap.parse_args()

    # ⚖️ alert surebet (chat privata)
    try:
        bp = bestprice_surebets(a.date)
        hot = [r for r in bp if r["margine%"] >= a.min]
        if hot:
            lines = [f"⚖️ <b>Surebet {a.date}</b> (≥ +{a.min}%):"]
            for r in hot:
                lines.append(f"• {r['ora']} {r['lega']} — {r['partita']} — <b>{r['mercato']} +{r['margine%']}%</b> ({r['quote']})")
            lines.append(FOOTER)
            send_alert("\n".join(lines))
        else:
            print(f"nessuna surebet ≥ +{a.min}% per {a.date}")
    except Exception as e:
        print(f"surebet alert: {e}")

    # 📋 digest su canale: run 23:00 IT (ora Romana 22-23) o run manuale o --digest
    h_rome = datetime.datetime.now(ZoneInfo("Europe/Rome")).hour
    if a.digest or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" or h_rome in (22, 23):
        try:
            digest(a)
        except Exception as e:
            print(f"digest: {e}")


if __name__ == "__main__":
    main()
