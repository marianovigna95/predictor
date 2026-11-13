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
    # ⭐ squadre preferite (file fav_teams.txt a root repo, un nome per riga)
    fav = set()
    ff = ROOT / "fav_teams.txt"
    if ff.exists():
        fav = {_norm(x) for x in ff.read_text(encoding="utf-8").splitlines() if x.strip()}
    if fav:
        for _, r in fc.iterrows():
            if not str(r.get("orario", "")).startswith(today_dm) or " - " not in r.get("partita", ""):
                continue
            h, a = r["partita"].split(" - ", 1)
            hn, an = _norm(h), _norm(a)
            if hn in fav or an in fav:
                if not any(c["h"] == hn and c["a"] == an for c in cand):
                    cand.append({"h": hn, "a": an, "partita": r["partita"], "pick": "⭐", "ev": 0,
                                 "odds": "", "lega": r.get("lega", ""), "ora": str(r.get("orario", ""))[-5:], "fav": True})
    if not cand:
        print(f"alert_live: nessuna partita EV>0/⭐ oggi ({date_str})")
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
        if cd.get("fav"):
            txt = (f"🔴 <b>LIVE ora</b> — {cd['partita']} ({cd['lega']}, ore {cd['ora']}) ⭐ la tua squadra\n"
                   f"minuto {clk} · fonte ESPN\n{FOOTER}")
        else:
            txt = (f"🔴 <b>LIVE ora</b> — {cd['partita']} ({cd['lega']}, ore {cd['ora']})\n"
                   f"🚩 Pronostico EV+{cd['ev']}%: <b>{cd['pick']} @ {cd['odds']}</b>\n"
                   f"minuto {clk} · fonte ESPN\n{FOOTER}")
        if send_alert(txt):
            done.add(eid)
            sent_file.write_text(" ".join(sorted(done)))
            print(f"alert_live inviato: {cd['partita']} ({eid})")


def alert_clv(date_str, drop_pct=5.0):
    """📉 Avvisa (chat privata) se la quota ADM di una giocata EV>0 di oggi è calata
    di oltre drop_pct% rispetto alla quota registrata nella schedina (giocata_multi.csv)."""
    import glob
    try:
        gj = pd.read_csv(DATA / "giocata_multi.csv", dtype=str).fillna("")
        gj = gj[gj["data"] == date_str]
    except Exception as e:
        print(f"alert_clv giocata: {e}")
        return
    if not len(gj):
        return
    files = sorted(glob.glob(str(DATA / "odds_window_*_bestprice.csv")))
    if not files:
        return
    od = pd.read_csv(files[-1], dtype=str).fillna("")
    od = od[od["data"] == date_str]
    if not len(od):
        return
    sent_file = DATA / f"clv_alerted_{date_str}.txt"
    done = set(sent_file.read_text().split()) if sent_file.exists() else set()
    for _, g in gj.iterrows():
        key = (g.get("partita", "") or "").strip().lower()
        if not key or key in done:
            continue
        try:
            ev0 = float(g.get("EV%") or 0)
        except Exception:
            ev0 = 0.0
        if ev0 <= 2:  # solo giocate con stake (EV>+2%)
            continue
        try:
            q0 = float(g.get("quota_best") or 0)
        except Exception:
            continue
        # stessa partita nel best-price attuale
        m = od[od["partita"].str.lower().str.strip() == key]
        if not len(m):
            continue
        r = m.iloc[0]
        pick = str(g.get("mercato", "")).strip()
        col = {"1": "best_1", "X": "best_X", "2": "best_2", "Over 2.5": "best_O25", "Under 2.5": "best_U25",
               "GG": "best_GG", "NG": "best_NG"}.get(pick)
        if not col or not r.get(col):
            continue
        q1 = float(r[col])
        if q0 > 0 and q1 < q0 * (1 - drop_pct / 100.0):
            txt = (f"📉 <b>Quota in calo</b> — {g.get('partita','')}\n"
                   f"mercato {pick}: schedina {q0:.2f} → ora {q1:.2f} (-{100*(q0-q1)/q0:.1f}%)\n"
                   f"EV era +{ev0:.1f}% · controlla CLV prima di puntare (ADM)\n{FOOTER}")
            if send_alert(txt):
                done.add(key)
                sent_file.write_text(" ".join(sorted(done)))
                print(f"alert_clv inviato: {g.get('partita')} {pick} {q0}->{q1}")


def alert_ft(date_str):
    """🏁 Avvisa (chat privata) quando una partita EV>0/⭐ di oggi è FINITA (FT) con il risultato."""
    import json
    try:
        fc = pd.read_csv(DATA / "forecast_multi.csv", dtype=str).fillna("")
    except Exception:
        return
    today_dm = f"{date_str[8:10]}/{date_str[5:7]}"
    cand = []
    for _, r in fc.iterrows():
        if not str(r.get("orario", "")).startswith(today_dm) or " - " not in r.get("partita", ""):
            continue
        try:
            ev = float(r.get("EV%") or 0)
        except Exception:
            ev = 0.0
        if ev > 0:
            h, a = r["partita"].split(" - ", 1)
            cand.append({"h": _norm(h), "a": _norm(a), "partita": r["partita"], "ev": round(ev * 100, 1),
                         "pick": r.get("pronostico", ""), "odds": r.get("quota_best", ""), "lega": r.get("lega", "")})
    ff = ROOT / "fav_teams.txt"
    if ff.exists():
        fav = {_norm(x) for x in ff.read_text(encoding="utf-8").splitlines() if x.strip()}
        for _, r in fc.iterrows():
            if not str(r.get("orario", "")).startswith(today_dm) or " - " not in r.get("partita", ""):
                continue
            h, a = r["partita"].split(" - ", 1)
            if _norm(h) in fav or _norm(a) in fav:
                if not any(c["partita"] == r["partita"] for c in cand):
                    cand.append({"h": _norm(h), "a": _norm(a), "partita": r["partita"], "ev": 0,
                                 "pick": "⭐", "odds": "", "lega": r.get("lega", "")})
    if not cand:
        return
    ds = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    j = json.load(urllib.request.urlopen(req, timeout=30))
    sent_file = DATA / f"ft_alerted_{date_str}.txt"
    done = set(sent_file.read_text().split()) if sent_file.exists() else set()
    for ev_ in j.get("events", []):
        c = (ev_.get("competitions") or [{}])[0]
        st = (c.get("status") or {}).get("type") or {}
        if st.get("state") != "post":
            continue
        cs = c.get("competitors") or []
        h = next((x for x in cs if x.get("homeAway") == "home"), {})
        a = next((x for x in cs if x.get("homeAway") == "away"), {})
        hn, an = _norm(h.get("team", {}).get("displayName", "")), _norm(a.get("team", {}).get("displayName", ""))
        for cd in cand:
            if (cd["h"] == hn and cd["a"] == an) and ev_["id"] not in done:
                res = f"{h.get('score','?')} - {a.get('score','?')}"
                if cd["ev"] > 0:
                    txt = (f"🏁 <b>FT</b> — {cd['partita']} ({cd['lega']}): <b>{res}</b>\n"
                           f"🚩 era EV+{cd['ev']}%: {cd['pick']} @ {cd['odds']} · verifica esito a fine giornata\n{FOOTER}")
                else:
                    txt = f"🏁 <b>FT</b> — {cd['partita']} ({cd['lega']}): <b>{res}</b> ⭐\n{FOOTER}"
                if send_alert(txt):
                    done.add(ev_["id"])
                    sent_file.write_text(" ".join(sorted(done)))
                    print(f"alert_ft inviato: {cd['partita']} {res}")


def comandi():
    """🤖 Comandi Telegram in chat privata: /oggi /ppa /surebets /verifica /diretta /start."""
    import json
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    base = f"https://api.telegram.org/bot{tok}"
    try:
        up = json.load(urllib.request.urlopen(urllib.request.Request(base + "/getUpdates?offset=-100&timeout=0", headers={"User-Agent": "Mozilla/5.0"}), timeout=15))
    except Exception as e:
        print(f"comandi getUpdates: {e}")
        return
    today = datetime.date.today().isoformat()
    for u in up.get("result", []):
        msg = u.get("message") or {}
        txt = (msg.get("text") or "").strip()
        cid = str((msg.get("chat") or {}).get("id", ""))
        if not txt.startswith("/") or cid != str(chat):
            continue
        cmd = txt.split()[0].split("@")[0].lower()
        try:
            if cmd in ("/start", "/help"):
                ans = ("🤖 Comandi: /oggi (giocate EV>0 di oggi) · /ppa (top p≥60%) · /surebets · /verifica (esiti ieri) · /diretta (partite LIVE ora) · /schedina\n" + FOOTER)
            elif cmd == "/oggi":
                gj = pd.read_csv(DATA / "giocata_multi.csv", dtype=str).fillna("")
                day = gj[gj["data"] == today] if "data" in gj.columns else gj
                ans = "🎯 Giocate di oggi (EV>0):\n" + ("\n".join(
                    f"• {r.get('tipo','')} — {r.get('partita','')} — {r.get('mercato','')} @ {r.get('quota_best','')} (EV +{r.get('EV%','')}%)" for _, r in day.iterrows()) if len(day) else "nessuna (stake 0)") + f"\n{FOOTER}"
            elif cmd == "/schedina":
                ans = f"🧾 Schedina di oggi: https://marianovigna95.github.io/predictor/schedina.html\n{FOOTER}"
            elif cmd == "/ppa":
                fc = pd.read_csv(DATA / "forecast_multi.csv", dtype=str).fillna("")
                fc["conf"] = pd.to_numeric(fc.get("conf%"), errors="coerce")
                top = fc[fc["conf"] >= 60].sort_values("conf", ascending=False).head(5)
                ans = "⚡ Top PPA (p≥60%):\n" + ("\n".join(f"• {r.get('orario','')} {r.get('partita','')} — {r.get('pronostico','')} {r['conf']}% @ {r.get('quota_best','')}" for _, r in top.iterrows()) if len(top) else "nessuna") + f"\n{FOOTER}"
            elif cmd == "/surebets":
                bp = bestprice_surebets(today)
                hot = [r for r in bp if float(r.get("margine%") or 0) >= 1.0]
                ans = "⚖️ Surebets ≥+1%:\n" + ("\n".join(f"• {r['ora']} {r['partita']} — {r['mercato']} +{r['margine%']}%" for r in hot) if hot else "nessuna oggi") + f"\n{FOOTER}"
            elif cmd == "/verifica":
                y = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
                evf = DATA / f"eval_day_{y}.csv"
                if evf.exists():
                    ev = pd.read_csv(evf)
                    ok = int((ev["esito"] == "✅").sum()) if "esito" in ev.columns else 0
                    ko = int((ev["esito"] == "❌").sum()) if "esito" in ev.columns else 0
                    ans = f"✅ Verifica {y}: {ok} vincenti / {ko} perdenti su {len(ev)} giocate\n{FOOTER}"
                else:
                    ans = f"Verifica {y} non ancora disponibile.\n{FOOTER}"
            elif cmd == "/diretta":
                ds = today.replace("-", "")
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}"
                j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
                live = []
                for e in j.get("events", []):
                    c = (e.get("competitions") or [{}])[0]
                    st = (c.get("status") or {}).get("type") or {}
                    if st.get("state") == "in":
                        cs = c.get("competitors") or []
                        h = next((x for x in cs if x.get("homeAway") == "home"), {})
                        a = next((x for x in cs if x.get("homeAway") == "away"), {})
                        live.append(f"• {h.get('team',{}).get('displayName','?')} {h.get('score','0')} - {a.get('score','0')} {a.get('team',{}).get('displayName','?')} ({(c.get('status') or {}).get('displayClock','')})")
                ans = "🔴 LIVE ora:\n" + ("\n".join(live[:15]) if live else "nessuna partita in corso ora") + f"\n{FOOTER}"
            else:
                continue
            _send(chat, ans)
            print(f"comando {cmd} → risposto")
        except Exception as e:
            print(f"comando {cmd}: {e}")


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

    # 🏁 alert FT (risultato) per partite EV>0/⭐ finite
    try:
        alert_ft(a.date)
    except Exception as e:
        print(f"alert_ft: {e}")

    # 🤖 comandi Telegram (/oggi /ppa /surebets /verifica /diretta)
    try:
        comandi()
    except Exception as e:
        print(f"comandi: {e}")

    # 📉 alert CLV: quota giocata EV>+2% scesa >5% (chat privata)
    try:
        alert_clv(a.date)
    except Exception as e:
        print(f"alert_clv: {e}")

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
