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


def _norm(t):
    import re, unicodedata
    t = unicodedata.normalize("NFKD", str(t))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def alert_live(date_str):
    """🔴 Avvisa (chat privata) quando una partita con pronostico EV>0 entra in LIVE oggi."""
    import json
    try:
        fc = pd.read_csv(DATA / "forecast_multi.csv", dtype=str).fillna("")
    except Exception as e:
        print(f"alert_live forecast: {e}")
        return
    today_dm = f"{date_str[8:10]}/{date_str[5:7]}"
    cand = []
    for _, r in fc.iterrows():
        if not str(r.get("orario", "")).startswith(today_dm):
            continue
        pick = str(r.get("pronostico", "")).strip()
        pcol = {"1": "p1%", "X": "pX%", "2": "p2%"}.get(pick)
        if not pcol or not r.get(pcol) or not r.get("quota_best") or " - " not in r.get("partita", ""):
            continue
        p = float(r[pcol]) / 100.0
        O = float(r["quota_best"])
        ev = p * (O - 1) - (1 - p)
        if ev > 0:
            h, a = r["partita"].split(" - ", 1)
            cand.append({"h": _norm(h), "a": _norm(a), "partita": r["partita"],
                         "pick": pick, "ev": round(ev * 100, 1), "odds": r["quota_best"],
                         "lega": r.get("lega", ""), "ora": str(r.get("orario", ""))[-5:]})
    if not cand:
        print(f"alert_live: nessuna partita EV>0 oggi ({date_str})")
        return
    ds = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    j = json.load(urllib.request.urlopen(req, timeout=30))
    live = []
    for ev_ in j.get("events", []):
        c = (ev_.get("competitions") or [{}])[0]
        st = (c.get("status") or {}).get("type") or {}
        if st.get("state") != "in":
            continue
        cs = c.get("competitors") or []
        h = next((x for x in cs if x.get("homeAway") == "home"), cs[0] if cs else {})
        a = next((x for x in cs if x.get("homeAway") == "away"), cs[1] if len(cs) > 1 else {})
        hn, an = _norm(h.get("team", {}).get("displayName", "")), _norm(a.get("team", {}).get("displayName", ""))
        for cd in cand:
            if (cd["h"] == hn and cd["a"] == an) or (cd["h"] == an and cd["a"] == hn):
                live.append((ev_["id"], cd, st.get("name", ""), c.get("status", {}).get("displayClock", "")))
    if not live:
        print(f"alert_live: nessuna delle EV>0 in live ora ({date_str})")
        return
    sent_file = DATA / f"live_alerted_{date_str}.txt"
    done = set(sent_file.read_text().split()) if sent_file.exists() else set()
    for eid, cd, stname, clk in live:
        if eid in done:
            continue
        txt = (f"🔴 <b>LIVE ora</b> — {cd['partita']} ({cd['lega']}, ore {cd['ora']})\n"
               f"🚩 Pronostico EV+{cd['ev']}%: <b>{cd['pick']} @ {cd['odds']}</b>\n"
               f"minuto {clk} · fonte ESPN\n{FOOTER}")
        if send_alert(txt):
            done.add(eid)
            sent_file.write_text(" ".join(sorted(done)))
            print(f"alert_live inviato: {cd['partita']} ({eid})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=1.0, help="soglia margine %")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--digest", action="store_true", help="forza invio digest")
    a = ap.parse_args()

    # 🔴 alert LIVE per partite con pronostico EV>0 (chat privata)
    try:
        alert_live(a.date)
    except Exception as e:
        print(f"alert_live: {e}")

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
