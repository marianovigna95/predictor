#!/usr/bin/env python3
"""step29_squadra.py — 🔎 Pagina "Squadra" + fixtures.json statico.

- Genera site/fixtures.json: calendario completo (non giocate) da data/fixtures_leagues.csv
  + data/fixtures_intl.csv, da oggi in poi → [date, div, home, away, lega].
- Genera site/squadra.html: cerca squadra (alias IT→EN) → TUTTE le sue partite della stagione
  dal calendario; se la partita è nella finestra 7gg mostra quote best-price e 🚩 EV>0.

Uso: python3 src/step29_squadra.py
"""
import csv
import datetime
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

FOOTER = "⚠️ Solo analisi, mai certezze · 18+ · puntare SOLO su ADM · autoesclusione.it · 800 558822"
NAV = ('<nav><a href="index.html" onclick="if(history.length>1){{history.back();return false;}}" aria-label="torna indietro" title="indietro">‹</a><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a>'
       '<a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a>'
       '<a href="giocata_multi.html">Giocate</a><a href="ppa.html">⚡ PPA</a>'
       '<a href="surebets.html">⚖️ Surebets</a><a href="schedina.html">🧾 Schedina</a>'
       '<a href="bankroll.html">💰 Bankroll</a><a class="on" href="squadra.html">🔎 Squadra</a>'
       '<a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a></nav>')


def build_fixtures_json():
    today = datetime.date.today().isoformat()
    out = []
    seen = set()
    for f in ["fixtures_leagues.csv", "fixtures_intl.csv"]:
        p = DATA / f
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                d = (r.get("date") or "").strip()[:10]
                if not d or d < today or str(r.get("played", "")).strip() not in ("", "0", "False", "false"):
                    continue
                key = (d, r.get("home", ""), r.get("away", ""))
                if key in seen:
                    continue
                seen.add(key)
                out.append([d, r.get("div", ""), r.get("home", ""), r.get("away", ""), r.get("league", "")])
    out.sort()
    (SITE / "fixtures.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(out)


JS = r"""
var FIX=null; var QMAP=__QMAP__; var EVMAP=__EVMAP__;
var ALIAS={"psg":"paris saint","bayern":"bayern munchen","milan":"ac milan","inter":"inter","napoli":"napoli","juve":"juventus","roma":"as roma","lazio":"lazio","atalanta":"atalanta","fiorentina":"fiorentina","toro":"torino","bologna":"bologna","udinese":"udinese","monza":"monza","verona":"hellas","empoli":"empoli","parma":"parma","genoa":"genoa","cagliari":"cagliari","lecce":"lecce","venezia":"venezia","como":"como","barcellona":"barcelona","barca":"barcelona","atletico":"atletico madrid","betis":"betis","sevilla":"sevilla","valencia":"valencia","villareal":"villarreal","arsenal":"arsenal","chelsea":"chelsea","liverpool":"liverpool","city":"manchester city","united":"manchester united","spurs":"tottenham","newcastle":"newcastle","villa":"aston villa","wolves":"wolverhampton","everton":"everton","brighton":"brighton","palace":"crystal palace","fulham":"fulham","brentford":"brentford","dortmund":"dortmund","leverkusen":"leverkusen","leipzig":"leipzig","frankfurt":"frankfurt","stuttgart":"stuttgart","gladbach":"monchengladbach","monaco":"monaco","marsiglia":"marseille","lille":"lille","nice":"nice","rennes":"rennes","benfica":"benfica","porto":"porto","sporting":"sporting","ajax":"ajax","psv":"psv","feyenoord":"feyenoord","galata":"galatasaray","fener":"fenerbahce","besiktas":"besiktas","celtic":"celtic","rangers":"rangers"};
function norm(t){return (t||'').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();}
function matchQ(q,nn){var nq=norm(q);if(!nq)return false;if(nn.indexOf(nq)>=0||nq.indexOf(nn)>=0)return true;
  for(var k in ALIAS){if(nq.indexOf(k)>=0||k.indexOf(nq)>=0){if(nn.indexOf(ALIAS[k])>=0)return true;}}
  return false;}
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function qk(dk,h,a){var q=QMAP[dk+'|'+norm(h)+'|'+norm(a)];if(!q&&QMAP[dk+'|'+norm(a)+'|'+norm(h)]){var s2=QMAP[dk+'|'+norm(a)+'|'+norm(h)];q={h:s2.a,x:s2.x,a:s2.h};}return q;}
function evk(dk,h,a){var q=EVMAP[dk+'|'+norm(h)+'|'+norm(a)];if(!q&&EVMAP[dk+'|'+norm(a)+'|'+norm(h)]){var s2=EVMAP[dk+'|'+norm(a)+'|'+norm(h)];q={ev:s2.ev,pick:s2.pick==='1'?'2':(s2.pick==='2'?'1':'X'),odds:s2.odds};}return q;}
async function cerca(){
  var q=document.getElementById('q').value.trim();
  var out=document.getElementById('res');
  if(!FIX){out.innerHTML='<p class="sub">carico calendario…</p>';try{FIX=await (await fetch('fixtures.json')).json();}catch(e){out.innerHTML='<p class="sub">calendario non disponibile</p>';return;}}
  if(q.length<3){out.innerHTML='<p class="sub">Scrivi almeno 3 lettere (es. "inter", "psg", "bayern")…</p>';return;}
  var nq=norm(q);
  // trova squadre che matchano
  var teams={};
  FIX.forEach(function(f){[f[2],f[3]].forEach(function(t){var nn=norm(t); if(matchQ(q,nn))teams[nn]=(teams[nn]||{name:t,n:0}); teams[nn].n++;});});
  var tlist=Object.keys(teams).sort(function(a,b){return teams[b].n-teams[a].n;});
  if(!tlist.length){out.innerHTML='<p class="sub">Nessuna squadra trovata per "'+esc(q)+'".</p>';return;}
  out.innerHTML='<p class="sub">Squadre: '+tlist.slice(0,6).map(function(t){return '<b>'+esc(teams[t].name)+'</b> ('+teams[t].n+' partite)';}).join(' · ')+'</p>';
  // calendario completo della prima squadra (o di tutte le trovate, max 2)
  var html='';
  tlist.slice(0,2).forEach(function(tn){
    var matches=FIX.filter(function(f){return norm(f[2])===tn||norm(f[3])===tn;});
    matches.sort(function(a,b){return a[0]<b[0]?-1:1;});
    html+='<h3 style="margin:14px 0 6px">📅 '+esc(teams[tn].name)+' — '+matches.length+' partite dal calendario ('+esc(matches[0][4]||'')+')</h3>';
    html+='<div class="mrow head"><span class="tm">Data</span><span class="h">Casa</span><span class="sc">vs</span><span class="a">Trasferta</span><span class="od">Quote/🚩</span></div>';
    matches.forEach(function(f){
      var dk=f[0], h=f[2], a=f[3];
      var qq=qk(dk,h,a), vv=evk(dk,h,a);
      var extra=(qq&&qq.h?('1 '+qq.h+' · X '+(qq.x||'–')+' · 2 '+qq.a):'')+((vv&&vv.ev>0)?(' <span class="flag">🚩 EV+'+vv.ev+'% '+esc(vv.pick)+' @ '+esc(vv.odds)+'</span>'):'');
      if(!extra)extra='<span class="od">—</span>';
      var dstr=dk.slice(8,10)+'/'+dk.slice(5,7);
      html+='<div class="mrow"><span class="tm">'+dstr+'</span><span class="h">'+esc(h)+'</span><span class="sc">-</span><span class="a">'+esc(a)+'</span><span class="od">'+extra+'</span></div>';
    });
  });
  out.innerHTML+=html;
}
document.getElementById('q').addEventListener('keydown',function(e){if(e.key==='Enter')cerca();});
"""

PAGE = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="manifest" href="manifest.webmanifest"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>🔎 Squadra — Predictor</title>
<style>
body{{background:#0b1220;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0}}
.wrap{{max-width:900px;margin:0 auto;padding:16px}}
h1{{font-size:20px}} h3{{font-size:15px}} .sub{{color:#8ea3c8;font-size:12px}}
nav{{display:flex;flex-wrap:wrap;gap:6px;padding:8px 0;border-bottom:1px solid #1e293b;margin-bottom:12px}}
nav a{{color:#8ea3c8;text-decoration:none;font-size:12px;background:#16233d;padding:5px 9px;border-radius:12px}}
nav a.on{{background:#b91c1c;color:#fff}}
#q{{width:100%;background:#0f1a30;border:1px solid #22345a;color:#fff;border-radius:10px;padding:10px 12px;font-size:15px;margin:10px 0}}
.mrow{{display:grid;grid-template-columns:70px 1fr 40px 1fr 190px;gap:6px;align-items:center;padding:6px 8px;border-bottom:1px solid #16233d;border-radius:6px}}
.mrow.head{{color:#64748b;font-size:10.5px;text-transform:uppercase}}
.tm{{color:#8ea3c8;font-size:12px}} .sc{{text-align:center;color:#64748b}} .h,.a{{font-size:13px}}
.od{{font-size:10.5px;color:#8ea3c8}}
.flag{{font-size:10px;background:#3b2f0b;color:#fbbf24;border-radius:8px;padding:2px 5px}}
footer{{color:#475569;font-size:11px;text-align:center;padding:14px}}
</style></head><body><div class="wrap">
<h1>🔎 Cerca squadra — calendario completo</h1>
<p class="sub">Tutte le partite della stagione dal calendario (tutte le nostre leghe + nazionali), con quote e 🚩 EV&gt;0 quando la partita è nella finestra 7 giorni. Nomi italiani ok (psg, bayern, juve…).</p>
{NAV}
<input id="q" placeholder="Nome squadra (es. Inter, PSG, Bayern, Juve, Atletico…)" autofocus>
<div id="res"></div>
</div>
<footer>{FOOTER}</footer>
<script>{JS}</script>
</body></html>"""


def main():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from step19_diretta import build_qmap, build_evmap  # riusa le mappe della finestra
    n = build_fixtures_json()
    page = PAGE.replace("__QMAP__", json.dumps(build_qmap(), ensure_ascii=False)).replace("__EVMAP__", json.dumps(build_evmap(), ensure_ascii=False))
    (SITE / "squadra.html").write_text(page, encoding="utf-8")
    print(f"🔎 site/squadra.html + site/fixtures.json ({n} partite non giocate)")


if __name__ == "__main__":
    main()
