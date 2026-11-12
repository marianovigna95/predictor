#!/usr/bin/env python3
"""step19_diretta.py — pagina DIREtta in stile diretta.it: lista compatta per lega (orario, squadre,
   risultato, minuto LIVE) + barra date (oggi-2 … oggi+7) con render client-side via ESPN.

- Server: genera diretta.html per --date (default oggi) come fallback no-JS.
- Browser: LIVE_JS legge ?d=YYYY-MM-DD, interroga ESPN scoreboard 'all' ogni 30s e ri-renderizza
  la lista (funziona per tutte le date, non solo oggi). Clic su una riga = dettaglio (statistiche/gol)
  per le nostre leghe. Nessun link a siti esterni.
Output: site/diretta.html
Uso: python3 src/step19_diretta.py [--date 2026-11-12]
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from make_site import footer  # 🛠 tabbar+legale condivisi

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ROME = ZoneInfo("Europe/Rome")

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

NOSTRE = {"Italian Serie A", "English Premier League", "Spanish La Liga", "German Bundesliga", "French Ligue 1",
          "Italian Serie B", "English Championship", "Dutch Eredivisie", "Portuguese Primeira Liga",
          "Spanish Segunda Division", "German 2. Bundesliga", "French Ligue 2", "Turkish Super Lig",
          "UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League",
          "UEFA Nations League", "World Cup Qualifying - Europe", "International Friendlies"}  # 🆕 11/11 nazionali

SLUGS = {"ita.1": "Italian Serie A", "ita.2": "Italian Serie B", "eng.1": "English Premier League",
         "eng.2": "English Championship", "esp.1": "Spanish La Liga", "esp.2": "Spanish Segunda Division",
         "ger.1": "German Bundesliga", "ger.2": "German 2. Bundesliga", "fra.1": "French Ligue 1",
         "fra.2": "French Ligue 2", "ned.1": "Dutch Eredivisie", "por.1": "Portuguese Primeira Liga",
         "tur.1": "Turkish Super Lig", "uefa.champions": "UEFA Champions League",
         "uefa.europa": "UEFA Europa League", "uefa.europa.conf": "UEFA Europa Conference League",
         "uefa.nations": "UEFA Nations League", "fifa.worldq.uefa": "World Cup Qualifying - Europe",  # 🆕 11/11
         "fifa.friendly": "International Friendlies"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def league_short(name):
    return {"Italian Serie A": "Serie A", "English Premier League": "Premier League", "Spanish La Liga": "LaLiga",
            "German Bundesliga": "Bundesliga", "French Ligue 1": "Ligue 1", "Italian Serie B": "Serie B",
            "English Championship": "Championship", "Dutch Eredivisie": "Eredivisie", "Portuguese Primeira Liga": "Primeira Liga",
            "Spanish Segunda Division": "LaLiga 2", "German 2. Bundesliga": "Bundesliga 2", "French Ligue 2": "Ligue 2",
            "Turkish Super Lig": "Süper Lig", "UEFA Champions League": "Champions League", "UEFA Europa League": "Europa League",
            "UEFA Europa Conference League": "Conference League", "UEFA Nations League": "Nations League",
            "World Cup Qualifying - Europe": "Qual. Mondiali UEFA", "International Friendlies": "Amichevoli"}.get(name, name)


IT_MAP = [("Goal", "⚽ Gol"), ("Penalty", "⚽ Rigore"), ("Own Goal", "⚽ Autogol"), ("Red Card", "🟥 Rosso"),
          ("Yellow Card", "🟨 Giallo"), ("Substitution", "🔁 Sostituzione"), ("VAR", "🖥️ VAR"), ("Offside", "🚩 Fuorigioco"),
          ("Corner", "🚩 Corner"), ("Shot", "💥 Tiro"), ("Save", "🧤 Parata"), ("Foul", "⚠️ Fallio"), ("Free Kick", "🆓 Punizione")]


def it_tr(txt):
    for en, it in IT_MAP:
        if txt.lower().startswith(en.lower()):
            return it + txt[len(en):]
    return txt


def stats_for(event_id):
    """Statistiche dal summary ESPN: possesso, tiri, xG, corner, falli + marcatori."""
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
        if txt and tid in ("70", "80", "75"):
            goals.append(f"{clock} {it_tr(txt)}")
    out["_goals"] = goals[:10]
    return out


def fetch_events(ds):
    """Tutti gli eventi ESPN delle nostre competizioni per la data ds (YYYYMMDD)."""
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
            hhmm = ev.get("date", "")[11:16]
            evs.append({"id": ev["id"], "lg": lg, "h": h["team"]["displayName"], "a": aw["team"]["displayName"],
                        "hs": h.get("score", "0"), "as": aw.get("score", "0"), "live": live,
                        "status": st["type"]["name"], "minute": minute, "ours": True,
                        "t": ev.get("date", ""), "hhmm": hhmm})
    evs.sort(key=lambda e: (not e["live"], e["lg"], e["t"]))
    return evs


LIVE_JS = """<script>
/* DIREtta stile diretta.it: lista per lega, render client-side da ESPN (gratis, CORS aperto).
   - ?d=YYYY-MM-DD seleziona la data (barra in alto: oggi-2 … oggi+7)
   - refresh live ogni 30s; clic su riga = dettaglio statistiche/gol (solo nostre leghe) */
(function(){
  var TODAY='__DATE__';
  var q=new URLSearchParams(location.search);
  var D=(q.get('d')||TODAY).replace(/-/g,'');
  var list=document.getElementById('lg-list');
  var sub=document.querySelector('header .sub');
  var openDet={};
  function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
  function badge(e){
    var tn=(e.status||'').toUpperCase();
    if(e.live)return '<span class="badge b-live"><i class="dot"></i>LIVE '+esc(e.minute||'')+'</span>';
    if(tn.indexOf('FULL')>=0||tn.indexOf('FINAL')>=0)return '<span class="badge b-ft">FT</span>';
    return '<span class="badge b-pre">'+esc(e.hhmm||'')+'</span>';
  }
  function row(e){
    var cls=e.live?'mrow live':((''+e.status).toUpperCase().indexOf('FULL')>=0?'mrow ft':'mrow');
    return '<div class="'+cls+'" data-eid="'+e.id+'" onclick="window.__tg(this)">'
      +'<span class="tm">'+esc(e.hhmm||'')+'</span>'
      +'<span class="h">'+esc(e.h)+'</span>'
      +'<span class="sc">'+esc(e.hs)+' - '+esc(e.as)+'</span>'
      +'<span class="a">'+esc(e.a)+'</span>'
      +badge(e)+'</div>'
      +'<div class="det" id="det-'+e.id+'" style="display:none"></div>';
  }
  function render(evs){
    var bylg={};
    evs.forEach(function(e){(bylg[e.lg]=bylg[e.lg]||[]).push(e);});
    var lgs=Object.keys(bylg).sort();
    var liveN=evs.filter(function(e){return e.live;}).length;
    var out='';
    lgs.forEach(function(lg){
      out+='<div class="lgh">'+esc(lg.replace(/^.*\\s/,'').length?lg:lg)+'</div>';
      bylg[lg].forEach(function(e){out+=row(e);});
    });
    list.innerHTML=out||'<p class="sub" style="padding:14px">Nessuna partita in programma per questa data.</p>';
    if(sub)sub.textContent=evs.length+' partite · '+liveN+' LIVE · aggiornate '+new Date().toLocaleTimeString('it-IT')+' · fonte ESPN';
    // riapplica dettagli aperti
    Object.keys(openDet).forEach(function(id){var d=document.getElementById('det-'+id);if(d&&openDet[id]){d.style.display='block';}});
  }
  window.__tg=function(el){
    var id=el.getAttribute('data-eid');
    var d=document.getElementById('det-'+id);
    if(!d)return;
    if(openDet[id]){openDet[id]=false;d.style.display='none';d.innerHTML='';return;}
    openDet[id]=true;d.style.display='block';d.innerHTML='<p class="sub" style="padding:6px 10px">caricamento…</p>';
    fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event='+id+'&lang=it&region=it')
      .then(function(r){return r.json();}).then(function(j){
        var goals=(j.keyEvents||[]).filter(function(k){return ['70','80','75'].indexOf(String(k.type&&k.type.id))>=0;})
          .map(function(k){return (k.clock&&k.clock.displayValue||'')+' '+esc(k.text||'');});
        var rows=[];
        (j.boxscore&&j.boxscore.teams||[]).forEach(function(t){
          (t.statistics||[]).forEach(function(s){
            var nm=s.name; if(['possession','shots','shotsOnTarget','expectedGoals','cornerKicks','foulsCommitted','offsides','yellowCards'].indexOf(nm)<0)return;
            rows.push('<tr><td>'+esc(nm)+'</td><td>'+esc(s.displayValue||'')+'</td></tr>');
          });
        });
        d.innerHTML=(goals.length?'<p class="stt">⚽ Marcatori</p><ul class="ev">'+goals.map(function(g){return '<li>'+g+'</li>';}).join('')+'</ul>':'')
          +(rows.length?'<table>'+rows.join('')+'</table>':'<p class="sub">statistiche non disponibili</p>')
          +'<p class="sub" style="font-size:11px">fonte dati: API pubblica ESPN — nessun reindirizzamento</p>';
      }).catch(function(){d.innerHTML='<p class="sub">dettaglio non disponibile</p>';});
  };
  function tick(){
    fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates='+D)
      .then(function(r){return r.json();})
      .then(function(j){
        var evs=(j.events||[]).map(function(ev){
          var c=ev.competitions[0];if(!c)return null;
          var cs=c.competitors||[];
          var h=cs.filter(function(x){return x.homeAway==='home';})[0]||cs[0];
          var a=cs.filter(function(x){return x.homeAway==='away';})[0]||cs[1];
          if(!h||!a)return null;
          var st=c.status||{type:{}};
          return {id:ev.id, lg:(ev.league&&ev.league.name)||'Altro', h:h.team.displayName, a:a.team.displayName,
                  hs:h.score||'0', as:a.score||'0', live:st.type.state==='in', status:st.type.name||'',
                  minute:st.displayClock||'', hhmm:(ev.date||'').substr(11,5)};
        }).filter(Boolean);
        evs.sort(function(x,y){return (x.live===y.live)?((x.lg<x.lg?-1:1)):(x.live?-1:1);});
        render(evs);
      })
      .catch(function(){});
  }
  // barra date: oggi-2 … oggi+7 (click delegato, niente onclick inline)
  function dstr(d){return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);}
  var bar=document.getElementById('daybar');
  if(bar){
    var dd0=new Date(D.slice(0,4), D.slice(4,6)-1, D.slice(6,8));
    var html='';
    for(var i=-2;i<=7;i++){
      var dd=new Date(dd0); dd.setDate(dd0.getDate()+i);
      var lab=(i===0?'Oggi ':(dd.getDate()+'/'+(dd.getMonth()+1)));
      html+='<button class="dbtn" data-d="'+dstr(dd)+'">'+lab+'</button>';
    }
    bar.innerHTML=html;
    bar.addEventListener('click',function(e){
      var b=e.target.closest('.dbtn'); if(b) location.search='?d='+b.getAttribute('data-d');
    });
  }
  tick();setInterval(tick,30000);
})();
</script>"""


def rows_html(evs):
    """Fallback server-side (no-JS): lista compatta per lega."""
    bylg = {}
    for e in evs:
        bylg.setdefault(e["lg"], []).append(e)
    out = []
    for lg in sorted(bylg):
        out.append(f'<div class="lgh">{html.escape(league_short(lg))} <span class="ours">★</span></div>')
        for e in bylg[lg]:
            cls = "mrow live" if e["live"] else ("mrow ft" if "FULL" in e["status"].upper() or "FINAL" in e["status"].upper() else "mrow")
            if e["live"]:
                b = f'<span class="badge b-live"><i class="dot"></i>LIVE {html.escape(e["minute"])}</span>'
            elif cls == "mrow ft":
                b = '<span class="badge b-ft">FT</span>'
            else:
                b = f'<span class="badge b-pre">{html.escape(e["hhmm"])}</span>'
            out.append(f'<div class="{cls}" data-eid="{e["id"]}">'
                       f'<span class="tm">{html.escape(e["hhmm"])}</span>'
                       f'<span class="h">{html.escape(e["h"])}</span>'
                       f'<span class="sc">{html.escape(str(e["hs"]))} - {html.escape(str(e["as"]))}</span>'
                       f'<span class="a">{html.escape(e["a"])}</span>{b}</div>')
    return "\n".join(out) if out else '<p class="sub" style="padding:14px">Nessuna partita in programma per questa data.</p>'


def daybar_html(today):
    btns = []
    for i in range(-2, 8):
        d = today + timedelta(days=i)
        lab = "Oggi" if i == 0 else f"{d.day}/{d.month}"
        btns.append(f'<button class="dbtn{" on" if i == 0 else ""}" data-d="{d.isoformat()}" onclick="location.search=\'?d={d.isoformat()}\'">{lab}</button>')
    return '<div id="daybar">' + "".join(btns) + "</div>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    ds = a.date.replace("-", "")
    today = date.fromisoformat(a.date)

    evs = fetch_events(ds)
    live_n = sum(1 for e in evs if e["live"])

    page = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<meta http-equiv="refresh" content="300">
<title>🔴 Diretta — Predictor</title>
<style>
:root{{--bg:#0b1220;--card:#111c33;--txt:#e2e8f0;--sub:#94a3b8;--acc:#2563eb;--red:#dc2626}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:rgba(11,18,32,.94);backdrop-filter:blur(6px);padding:10px 14px;border-bottom:1px solid #1e293b;z-index:5}}
header b{{font-size:18px}} header .sub{{color:var(--sub);font-size:12px;margin-left:8px}}
#daybar{{display:flex;gap:6px;overflow-x:auto;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b;position:sticky;top:49px;z-index:4}}
.dbtn{{flex:0 0 auto;background:#16233d;color:#cbd5e1;border:1px solid #1e293b;border-radius:8px;padding:5px 12px;font-size:12px;cursor:pointer}}
.dbtn.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:#16233d}}
nav a.on{{background:var(--acc);color:#fff}} nav a:hover{{background:#1e3a8a}}
main{{max-width:860px;margin:0 auto;padding:10px 12px}}
.lgh{{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#64748b;padding:12px 4px 4px;border-bottom:1px solid #1e293b;position:sticky;top:96px;background:var(--bg);z-index:3}}
.ours{{color:#fbbf24}}
.mrow{{display:grid;grid-template-columns:44px 1fr 64px 1fr auto;gap:8px;align-items:center;padding:7px 8px;border-bottom:1px solid #16233d;cursor:pointer;border-radius:6px}}
.mrow:hover{{background:#16233d}}
.mrow.live{{background:#2a1215;border-left:3px solid var(--red)}}
.tm{{color:var(--sub);font-size:12px;font-variant-numeric:tabular-nums}}
.h{{text-align:right;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.a{{text-align:left;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc{{text-align:center;font-weight:800;font-size:15px;background:#0b1220;border:1px solid #1e293b;border-radius:6px;padding:2px 0;font-variant-numeric:tabular-nums}}
.mrow.live .sc{{border-color:var(--red);color:#fecaca}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}}
.b-live{{background:var(--red);color:#fff}} .b-ft{{background:#334155;color:#cbd5e1}} .b-pre{{background:#14532d;color:#86efac}}
.dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:#fff;margin-right:4px;animation:blink 1s infinite}}
@keyframes blink{{50%{{opacity:.25}}}}
.det{{background:#0d1526;border:1px solid #1e293b;border-radius:8px;margin:2px 0 8px;padding:8px 10px;font-size:13px;color:var(--sub)}}
.stt{{margin:4px 0;color:#93c5fd;font-weight:700}} table{{width:100%;border-collapse:collapse;margin-top:4px}} td{{padding:3px 6px;border-bottom:1px solid #16233d;text-align:center;font-size:12px}} td:first-child{{text-align:left;color:var(--txt)}}
ul.ev{{margin:4px 0;padding-left:18px}} ul.ev li{{margin-bottom:2px}}
</style></head><body>
<header><b>🔴 Diretta {html.escape(a.date)}</b><span class="sub">{len(evs)} partite · {live_n} LIVE · fonte ESPN (API pubblica, nessun reindirizzamento)</span></header>
{daybar_html(today)}
<nav>
<a href="index.html">Home</a><a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a><a href="altre-leghe.html">Altre leghe</a><a href="giocata_multi.html">Giocate</a><a href="quote_giornata10.html">Quote</a><a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a><a class="on" href="diretta.html">🔴 Diretta</a>
</nav>
<main id="lg-list">
{rows_html(evs)}
</main>
<p style="text-align:center;color:#475569;font-size:12px;padding:14px">⚠️ Solo analisi, mai certezze · 18+ · ADM · autoesclusione.it · 800 558822</p>
</body>{LIVE_JS.replace('__DATE__', ds)}{footer("")}</html>"""
    SITE.mkdir(exist_ok=True)
    (SITE / "diretta.html").write_text(page, encoding="utf-8")
    print(f"🔴 site/diretta.html: {len(evs)} partite ({live_n} live) — {a.date}")


if __name__ == "__main__":
    main()
