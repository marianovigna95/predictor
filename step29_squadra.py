#!/usr/bin/env python3
"""step29_squadra.py — 🔎 Pagina "Squadra": cerca una squadra e vedi le sue partite
nella finestra oggi→+7 (quote best-price, 🚩 EV>0, dettaglio ESPN) — tutto client-side, gratis.

Uso: python3 src/step29_squadra.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

FOOTER = "⚠️ Solo analisi, mai certezze · 18+ · puntare SOLO su ADM · autoesclusione.it · 800 558822"
NAV = ('<nav><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a>'
       '<a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a>'
       '<a href="giocata_multi.html">Giocate</a><a href="ppa.html">⚡ PPA</a>'
       '<a href="surebets.html">⚖️ Surebets</a><a href="schedina.html">🧾 Schedina</a>'
       '<a href="bankroll.html">💰 Bankroll</a><a class="on" href="squadra.html">🔎 Squadra</a>'
       '<a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a></nav>')

JS = r"""
var SLUGS={"ita.1":"Serie A","ita.2":"Serie B","eng.1":"Premier League","eng.2":"Championship","esp.1":"La Liga","esp.2":"La Liga 2","ger.1":"Bundesliga","ger.2":"2. Bundesliga","fra.1":"Ligue 1","fra.2":"Ligue 2","ned.1":"Eredivisie","por.1":"Primeira Liga","tur.1":"Süper Lig","uefa.champions":"Champions League","uefa.europa":"Europa League","uefa.europa.conf":"Conference League","uefa.nations":"Nations League","fifa.worldq.uefa":"Qual. Mondiali UEFA","fifa.friendly":"Amichevoli"};
var QMAP=__QMAP__; var EVMAP=__EVMAP__;
function norm(t){return (t||'').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();}
function dstr(d){return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);}
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function qk(dk,h,a){var q=QMAP[dk+'|'+norm(h)+'|'+norm(a)];if(!q&&QMAP[dk+'|'+norm(a)+'|'+norm(h)]){var s2=QMAP[dk+'|'+norm(a)+'|'+norm(h)];q={h:s2.a,x:s2.x,a:s2.h};}return q;}
function evk(dk,h,a){var q=EVMAP[dk+'|'+norm(h)+'|'+norm(a)];if(!q&&EVMAP[dk+'|'+norm(a)+'|'+norm(h)]){var s2=EVMAP[dk+'|'+norm(a)+'|'+norm(h)];q={ev:s2.ev,pick:s2.pick==='1'?'2':(s2.pick==='2'?'1':'X'),odds:s2.odds};}return q;}
async function cerca(){
  var q=norm(document.getElementById('q').value);
  var out=document.getElementById('res');
  if(q.length<3){out.innerHTML='<p class="sub">Scrivi almeno 3 lettere (es. "inter", "napoli", "bayern")…</p>';return;}
  out.innerHTML='<p class="sub">Cerco nella finestra oggi→+7…</p>';
  var now=new Date(); var all=[];
  for(var i=0;i<=7;i++){
    var d=new Date(now); d.setDate(now.getDate()+i); var ds=dstr(d).replace(/-/g,''); var dk=dstr(d);
    for(var slg in SLUGS){
      try{
        var j=await (await fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/'+slg+'/scoreboard?dates='+ds)).json();
        (j.events||[]).forEach(function(ev){
          var c=(ev.competitions||[])[0]; if(!c)return;
          var cs=c.competitors||[];
          var h=cs.filter(function(x){return x.homeAway==='home';})[0]||cs[0];
          var a=cs.filter(function(x){return x.homeAway==='away';})[0]||cs[1];
          if(!h||!a)return;
          if(norm(h.team.displayName).indexOf(q)>=0||norm(a.team.displayName).indexOf(q)>=0){
            all.push({id:ev.id,ds:ds,dk:dk,lg:SLUGS[slg],h:h.team.displayName,a:a.team.displayName,
              hid:h.team.id,aid:a.team.id,hl:'https://a.espncdn.com/i/teamlogos/soccer/500/'+(h.team.id||'')+'.png',
              al:'https://a.espncdn.com/i/teamlogos/soccer/500/'+(a.team.id||'')+'.png',
              hs:h.score||'0',as:a.score||'0',live:((c.status||{}).type||{}).state==='in',
              hhmm:new Date(ev.date||0).toLocaleTimeString('it-IT',{timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit'})});
          }
        });
      }catch(e){}
    }
  }
  if(!all.length){out.innerHTML='<p class="sub">Nessuna partita trovata per "'+esc(q)+'" nella finestra 7 giorni (solo le nostre leghe).</p>';return;}
  all.sort(function(x,y){return x.ds===y.ds?(x.hhmm<y.hhmm?-1:1):(x.ds<y.ds?-1:1);});
  var teams={}; all.forEach(function(e){[e.h,e.a].forEach(function(t){teams[norm(t)]=(teams[norm(t)]||0)+1;});});
  var tlist=Object.keys(teams).sort(function(a,b){return teams[b]-teams[a];});
  var th='<p class="sub">Squadre trovate: '+tlist.slice(0,8).map(function(t){return '<b>'+esc(t)+'</b> ('+teams[t]+')';}).join(' · ')+'</p>';
  var rows=all.slice(0,40).map(function(e){
    var qq=qk(e.dk,e.h,e.a), vv=evk(e.dk,e.h,e.a);
    var fl=vv&&vv.ev>0?'<span class="flag">🚩 EV+'+vv.ev+'% '+esc(vv.pick)+' @ '+esc(vv.odds)+'</span>':'';
    var od=qq&&qq.h?'<span class="od">1 '+qq.h+' · X '+(qq.x||'–')+' · 2 '+qq.a+'</span>':'<span class="od">—</span>';
    return '<div class="mrow" data-eid="'+e.id+'"><span class="tm">'+e.dk.slice(8,10)+'/'+e.dk.slice(5,7)+' '+e.hhmm+(e.live?' <b style="color:#ef4444">LIVE</b>':'')+'</span>'
      +'<span class="h"><img class="lg" src="'+e.hl+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.h)+'</span>'
      +'<span class="sc">'+esc(e.hs)+' - '+esc(e.as)+'</span>'
      +'<span class="a"><img class="lg" src="'+e.al+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.a)+'</span>'
      +od+fl+'</div><div class="det" id="det-'+e.id+'" style="display:none"></div>';
  }).join('');
  out.innerHTML=th+'<p class="sub">'+all.length+' partite — clicca per il dettaglio:</p>'+rows;
  out.querySelectorAll('.mrow').forEach(function(el){el.addEventListener('click',function(){window.__tg2(el.getAttribute('data-eid'),el);});});
}
// dettaglio semplificato (summary ESPN) — stesso stile della diretta
var OPEN={};
window.__tg2=function(id,row){
  var d=document.getElementById('det-'+id);
  if(OPEN[id]){OPEN[id]=false;d.style.display='none';return;}
  OPEN[id]=true; d.style.display='block'; d.innerHTML='<p class="sub" style="padding:6px 10px">caricamento…</p>';
  fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event='+id+'&lang=it&region=it')
    .then(function(r){return r.json();}).then(function(j){
      var evs=(j.keyEvents||[]).slice().sort(function(a,b){return parseFloat((b.clock&&b.clock.value)||0)-parseFloat((a.clock&&a.clock.value)||0);});
      function iconFor(t){t=(t||'').toLowerCase();if(/goal/.test(t))return'⚽';if(/red card/.test(t))return'🟥';if(/yellow/.test(t))return'🟨';if(/substitut/.test(t))return'🔁';return'•';}
      var tl=evs.slice(0,15).map(function(k){return '<li>'+esc((k.clock&&k.clock.displayValue)||'')+' '+iconFor(k.text)+' '+esc(k.text||'')+'</li>';}).join('');
      var W=['expectedGoals','possessionPct','totalShots','shotsOnTarget','wonCorners','foulsCommitted','yellowCards'];
      var teams=(j.boxscore&&j.boxscore.teams)||[]; var map={};
      teams.forEach(function(t,i){(t.statistics||[]).forEach(function(st){(map[st.name]=map[st.name]||[null,null])[i]=st.displayValue;});});
      var rows=''; W.forEach(function(nm){var v=map[nm];if(v&&(v[0]||v[1]))rows+='<tr><td>'+esc(nm)+'</td><td>'+esc(v[0]||'')+'</td><td>'+esc(v[1]||'')+'</td></tr>';});
      var ros=j.rosters||[]; var lin='';
      if(ros.length===2){function lu(t){var st=(t.roster||[]).filter(function(a){return a.starter;});var h='<div class="lin"><b>'+esc(t.team.shortDisplayName||'')+'</b> <span class="fmt">'+esc(t.formation||'')+'</span><ul>';st.forEach(function(a){h+='<li><i>'+esc(a.jersey||'')+'</i> '+esc((a.athlete&&(a.athlete.shortName||a.athlete.displayName))||'')+' <em>'+esc((a.position&&a.position.abbreviation)||'')+'</em></li>';});return h+'</ul></div>';}
        lin='<p class="stt">⚽ Formazioni</p><div class="lins">'+lu(ros[0])+lu(ros[1])+'</div>';}
      d.innerHTML=(tl?'<p class="stt">🕐 Timeline</p><ul class="ev">'+tl+'</ul>':'')
        +lin+(rows?'<table>'+rows+'</table>':'<p class="sub">statistiche non ancora disponibili</p>')
        +'<p class="sub" style="font-size:11px">fonte: API pubblica ESPN — nessun reindirizzamento</p>';
    }).catch(function(){d.innerHTML='<p class="sub">dettaglio non disponibile</p>';});
};
document.getElementById('q').addEventListener('keydown',function(e){if(e.key==='Enter')cerca();});
"""

PAGE = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="manifest" href="manifest.webmanifest"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>🔎 Squadra — Predictor</title>
<style>
body{{background:#0b1220;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0}}
.wrap{{max-width:900px;margin:0 auto;padding:16px}}
h1{{font-size:20px}} .sub{{color:#8ea3c8;font-size:12px}}
nav{{display:flex;flex-wrap:wrap;gap:6px;padding:8px 0;border-bottom:1px solid #1e293b;margin-bottom:12px}}
nav a{{color:#8ea3c8;text-decoration:none;font-size:12px;background:#16233d;padding:5px 9px;border-radius:12px}}
nav a.on{{background:#b91c1c;color:#fff}}
#q{{width:100%;background:#0f1a30;border:1px solid #22345a;color:#fff;border-radius:10px;padding:10px 12px;font-size:15px;margin:10px 0}}
.mrow{{display:grid;grid-template-columns:86px 1fr 56px 1fr 128px auto;gap:6px;align-items:center;padding:7px 8px;border-bottom:1px solid #16233d;cursor:pointer;border-radius:6px}}
.mrow:hover{{background:#16233d}}
.tm{{color:#8ea3c8;font-size:12px}} .sc{{text-align:center;font-weight:700;background:#0f1a30;border:1px solid #22345a;border-radius:6px;padding:2px}}
.lg{{width:16px;height:16px;vertical-align:-3px;margin-right:5px;border-radius:50%}}
.h,.a{{display:flex;align-items:center}} .od{{font-size:10.5px;color:#8ea3c8;white-space:nowrap}}
.flag{{font-size:10px;background:#3b2f0b;color:#fbbf24;border-radius:8px;padding:2px 5px;white-space:nowrap}}
.det{{background:#0d1526;border:1px solid #1e293b;border-radius:8px;margin:2px 0 8px;padding:8px 10px;font-size:13px;color:#cbd5e1}}
.stt{{margin:8px 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#8ea3c8}}
table{{width:100%;border-collapse:collapse}} td{{padding:3px 6px;border-bottom:1px solid #16233d;text-align:center;font-size:12px}} td:first-child{{text-align:left}}
ul.ev{{margin:4px 0;padding-left:18px}} .lins{{display:flex;gap:10px;flex-wrap:wrap}} .lin{{flex:1;min-width:180px;background:#0b1220;border:1px solid #16233d;border-radius:8px;padding:6px 8px}} .lin ul{{list-style:none;margin:6px 0 0;padding:0}} .lin li{{font-size:11.5px;padding:1.5px 0}} .lin li i{{font-style:normal;color:#64748b;display:inline-block;width:18px}} .lin li em{{font-style:normal;color:#64748b;font-size:10px}} .fmt{{color:#8ea3c8;font-size:11px}}
footer{{color:#475569;font-size:11px;text-align:center;padding:14px}}
</style></head><body><div class="wrap">
<h1>🔎 Cerca squadra</h1>
<p class="sub">Tutte le partite della squadra nella finestra oggi→+7 giorni (solo le nostre leghe), con quote best-price e 🚩 EV&gt;0. Fonte: ESPN + nostra finestra.</p>
{NAV}
<input id="q" placeholder="Nome squadra (es. Inter, Bayern, Napoli)…" autofocus>
<div id="res"></div>
</div>
<footer>{FOOTER}</footer>
<script>{JS.replace('__QMAP__', '__QMAP__').replace('__EVMAP__','__EVMAP__')}</script>
</body></html>"""


def main():
    import json, sys
    sys.path.insert(0, str(ROOT / "src"))
    from step19_diretta import build_qmap, build_evmap, SLUGS  # riusa le mappe
    page = PAGE.replace("__QMAP__", json.dumps(build_qmap(), ensure_ascii=False)).replace("__EVMAP__", json.dumps(build_evmap(), ensure_ascii=False))
    (SITE / "squadra.html").write_text(page, encoding="utf-8")
    print("🔎 site/squadra.html scritto")


if __name__ == "__main__":
    main()
