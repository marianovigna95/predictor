#!/usr/bin/env python3
"""step19_diretta.py — pagina DIREtta (live scores + statistiche) come diretta.it.

Fonte: ESPN scoreboard API (gratis, no key) per score/minuto live di oggi (o --date),
+ summary per evento per le statistiche (tiro, possesso, xG se disponibile) delle NOSTRE leghe.
Output: site/diretta.html (auto-refresh 30s) — patchato anche nel tabbar di make_site.
Uso: python3 src/step19_diretta.py [--date 2026-11-07]
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from make_site import footer  # 🛠 09/11 tabbar+legale condivisi

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

NOSTRE = {"Italian Serie A", "English Premier League", "Spanish La Liga", "German Bundesliga", "French Ligue 1",
          "Italian Serie B", "English Championship", "Dutch Eredivisie", "Portuguese Primeira Liga",
          "Spanish Segunda Division", "German 2. Bundesliga", "French Ligue 2", "Turkish Super Lig",
          "UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def league_short(name):
    return {"Italian Serie A": "Serie A", "English Premier League": "Premier League", "Spanish La Liga": "LaLiga",
            "German Bundesliga": "Bundesliga", "French Ligue 1": "Ligue 1", "Italian Serie B": "Serie B",
            "English Championship": "Championship", "Dutch Eredivisie": "Eredivisie", "Portuguese Primeira Liga": "Primeira Liga",
            "Spanish Segunda Division": "LaLiga 2", "German 2. Bundesliga": "Bundesliga 2", "French Ligue 2": "Ligue 2",
            "Turkish Super Lig": "Süper Lig", "UEFA Champions League": "Champions League", "UEFA Europa League": "Europa League",
            "UEFA Europa Conference League": "Conference League"}.get(name, name)


IT_MAP = [("Goal","⚽ Gol"),("Penalty","⚽ Rigore"),("Own Goal","⚽ Autogol"),("Red Card","🟥 Rosso"),
          ("Yellow Card","🟨 Giallo"),("Substitution","🔁 Sostituzione"),("VAR","🖥️ VAR"),("Offside","🚩 Fuorigioco"),
          ("Corner","🚩 Corner"),("Shot","💥 Tiro"),("Save","🧤 Parata"),("Foul","⚠️ Fallio"),("Free Kick","🆓 Punizione")]

def it_tr(txt):
    for en, it in IT_MAP:
        if txt.lower().startswith(en.lower()):
            return it + txt[len(en):]
    return txt


def stats_for(event_id):
    """Statistiche dal summary ESPN: possession, tiri, tiri in porta, xG, corner, falli."""
    try:
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}&lang=it&region=it")
    except Exception:
        return None
    out = {}
    for box in d.get("boxscore", {}).get("teams", []):
        for st in box.get("statistics", []):
            nm = st.get("name", "")
            val = st.get("displayValue", "")
            tname = st.get("team", {}).get("displayName", "") if isinstance(st.get("team"), dict) else ""
            out.setdefault(nm, {})[tname] = val
    goals = []
    for ke in d.get("keyEvents", []):
        txt = ke.get("text", "")
        clock = ke.get("clock", {}).get("displayValue", "")
        tid = str(ke.get("type", {}).get("id", ""))
        if txt and tid in ("70", "80", "75"):  # goal, own goal, penalty
            goals.append(f"{clock} {it_tr(txt)}")
    out["_goals"] = goals[:10]
    pbp = []
    for cm in d.get("commentary", [])[:12]:
        t = cm.get("clock", {}).get("displayValue", "") if isinstance(cm.get("clock"), dict) else str(cm.get("time", ""))
        txt = cm.get("text", "")
        if txt:
            pbp.append(f"{t} {it_tr(txt)}")
    out["_plays"] = pbp
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    ds = a.date.replace("-", "")
    # endpoint per lega ESPN -> nome nostro (solo nostre leghe + coppe, come diretta.it ma filtrato)
    SLUGS = {"ita.1": "Italian Serie A", "ita.2": "Italian Serie B", "eng.1": "English Premier League",
             "eng.2": "English Championship", "esp.1": "Spanish La Liga", "esp.2": "Spanish Segunda Division",
             "ger.1": "German Bundesliga", "ger.2": "German 2. Bundesliga", "fra.1": "French Ligue 1",
             "fra.2": "French Ligue 2", "ned.1": "Dutch Eredivisie", "por.1": "Portuguese Primeira Liga",
             "tur.1": "Turkish Super Lig", "uefa.champions": "UEFA Champions League",
             "uefa.europa": "UEFA Europa League", "uefa.europa.conf": "UEFA Europa Conference League"}
    evs = []
    for slg, lg in SLUGS.items():
        try:
            d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slg}/scoreboard?dates={ds}")
        except Exception:
            continue
        for ev in d.get("events", []):
            comp = ev["competitions"][0]
            cs = comp["competitors"]
            h = next((c for c in cs if c["homeAway"] == "home"), cs[0])
            aw = next((c for c in cs if c["homeAway"] == "away"), cs[1])
            st = comp["status"]
            live = st["type"]["state"] == "in"
            minute = st.get("displayClock", "")
            evs.append({"id": ev["id"], "lg": lg, "h": h["team"]["displayName"], "a": aw["team"]["displayName"],
                        "hs": h.get("score", "0"), "as": aw.get("score", "0"), "live": live,
                        "status": st["type"]["name"], "minute": minute, "ours": True,
                        "t": ev.get("date", "")})
    evs.sort(key=lambda e: (not e["live"], e["lg"], e["t"]))
    ours = [e for e in evs if e["ours"]]
    live_n = sum(1 for e in evs if e["live"])

    cards = []
    for e in evs:
        cls = "live" if e["live"] else ("ft" if "FULL" in e["status"] or "FINAL" in e["status"] else "pre")
        badge = f'<span class="badge {"b-live" if e["live"] else ("b-ft" if cls=="ft" else "b-pre")}">' + \
                (f"🔴 LIVE {e['minute']}" if e["live"] else ("FT" if cls == "ft" else "da giocare")) + "</span>"
        ours_tag = ' <span class="ours">★ nostra lega</span>' if e["ours"] else ""
        stats_html = goals_html = plays_html = ""
        st = stats_for(e["id"]) if e["ours"] else None
        if st:
            gl = st.pop("_goals", []); pl = st.pop("_plays", [])
            if gl:
                goals_html = '<p class="stt">⚽ Marcatori</p><ul class="ev">' + "".join(f"<li>{html.escape(g)}</li>" for g in gl) + "</ul>"
            if pl:
                plays_html = '<p class="stt">📜 Ultime azioni (commento live)</p><ul class="ev">' + "".join(f"<li>{html.escape(x)}</li>" for x in reversed(pl)) + "</ul>"
        if True:
            if st:
                keep = ["possession", "shots", "shotsOnTarget", "expectedGoals", "totalShotsOnGoal", "cornerKicks", "foulsCommitted", "offsides", "yellowCards"]
                rows = []
                for nm in keep:
                    if nm in st:
                        vals = list(st[nm].values())
                        if len(vals) >= 2:
                            rows.append(f"<tr><td>{html.escape(nm.replace('expectedGoals','xG').replace('shotsOnTarget','tiri in porta').replace('cornerKicks','corner').replace('foulsCommitted','falli').replace('totalShotsOnGoal','tiri in porta').replace('yellowCards','gialli').replace('offsides','fuorigioco'))}</td><td>{html.escape(str(vals[0]))}</td><td>{html.escape(str(vals[1]))}</td></tr>")
                if rows:
                    stats_html = f'<p class="stt">📊 statistiche</p><table>{"".join(rows)}</table>' 
        cards.append(f"""
      <div class="card {cls}">
        <div class="top"><span class="lg">{html.escape(league_short(e['lg']))}{ours_tag}</span>{badge}</div>
        <details class="m">
        <summary class="teams"><span class="t home">{html.escape(e['h'])}</span><span class="score">{html.escape(str(e['hs']))} - {html.escape(str(e['as']))}</span><span class="t away">{html.escape(e['a'])}</span></summary>
        <div class="body">{goals_html}{plays_html}{stats_html}<p class="ext">🔗 <a href="https://www.espn.com/soccer/match/_/gameId/{e['id']}" target="_blank">scheda ESPN ↗</a> <span style="color:#475569">(nel browser vero o nel live preview 8002 — nel preview incorporato i link esterni sono bloccati)</span></p></div>
        </details>
      </div>""")

    page = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<meta http-equiv="refresh" content="30">
<title>🔴 Diretta — Predictor</title>
<style>
:root{{--bg:#0b1220;--card:#111c33;--txt:#e2e8f0;--sub:#94a3b8;--acc:#2563eb}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:rgba(11,18,32,.92);backdrop-filter:blur(6px);padding:10px 14px;border-bottom:1px solid #1e293b;z-index:5}}
header b{{font-size:18px}} header .sub{{color:var(--sub);font-size:12px;margin-left:8px}}
nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:#16233d}}
nav a.on{{background:var(--acc);color:#fff}} nav a:hover{{background:#1e3a8a}}
main{{max-width:860px;margin:0 auto;padding:12px}}
.card{{background:var(--card);border:1px solid #1e293b;border-radius:12px;padding:10px 12px;margin-bottom:8px}}
.card.live{{border-color:#dc2626;box-shadow:0 0 0 1px #dc2626 inset}}
.top{{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--sub)}}
.ours{{color:#fbbf24}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700}}
.b-live{{background:#dc2626;color:#fff}} .b-ft{{background:#334155;color:#cbd5e1}} .b-pre{{background:#14532d;color:#86efac}}
.teams{{display:flex;align-items:center;gap:10px;margin-top:6px;font-size:15px;color:inherit;text-decoration:none;border-radius:8px;padding:4px 6px;margin-left:-6px;margin-right:-6px;cursor:pointer;transition:background .15s}}.teams:hover{{background:#1e293b}}
summary.teams{{list-style:none}}
summary.teams::-webkit-details-marker{{display:none}}
summary.teams::after{{content:"▸";margin-left:auto;color:#64748b}}
details.m[open] summary.teams::after{{content:"▾"}}
.body{{padding:8px 2px 2px;font-size:13px;color:var(--sub)}}
.stt{{margin:4px 0 2px;color:#93c5fd;font-weight:700}}
.ext{{margin-top:8px;font-size:12px}} .ext a{{color:#60a5fa}}
ul.ev{{margin:4px 0 8px;padding-left:18px}} ul.ev li{{margin-bottom:2px}}
.t{{flex:1}} .t.away{{text-align:right}} .score{{font-weight:800;font-size:18px;background:#0b1220;padding:4px 10px;border-radius:8px}}
details.st{{margin-top:8px;font-size:12px;color:var(--sub)}}
details.st summary{{cursor:pointer;color:#93c5fd}}
table{{width:100%;border-collapse:collapse;margin-top:6px}} td{{padding:3px 6px;border-bottom:1px solid #1e293b;text-align:center}} td:first-child{{text-align:left;color:var(--txt)}}
</style></head><body>
<header><b>🔴 Diretta {html.escape(a.date)}</b><span class="sub">{len(evs)} partite · {live_n} LIVE · auto-refresh 30s · fonte ESPN</span></header>
<nav>
<a href="index.html">Home</a><a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a><a href="altre-leghe.html">Altre leghe</a><a href="giocata_multi.html">Giocate</a><a href="quote_giornata10.html">Quote</a><a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a><a class="on" href="diretta.html">🔴 Diretta</a>
</nav>
<main>{''.join(cards)}</main>
<p style="text-align:center;color:#475569;font-size:12px;padding:14px">⚠️ Solo analisi, mai certezze · 18+ · ADM · autoesclusione.it · 800 558822</p>
</body>{footer("")}</html>"""
    SITE.mkdir(exist_ok=True)
    (SITE / "diretta.html").write_text(page, encoding="utf-8")
    print(f"🔴 site/diretta.html: {len(evs)} partite ({live_n} live, {len(ours)} nostre leghe) — {a.date}")


if __name__ == "__main__":
    main()
