#!/usr/bin/env python3
"""step28_bankroll.py — 💰 Tracker bankroll personale (pagina statica bankroll.html).

La pagina salva le giocate in localStorage del browser, calcola ROI/winrate/drawdown,
permette verifica automatica degli esiti via ESPN (gratis, client-side) ed export/import CSV.
Nessun dato esce dal browser (analysis-only).

Uso: python3 src/step28_bankroll.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

FOOTER = "⚠️ Solo analisi, mai certezze · 18+ · puntare SOLO su ADM · autoesclusione.it · 800 558822"
NAV = ('<nav><a href="index.html" onclick="if(history.length>1){history.back();return false;}" aria-label="torna indietro" title="indietro">‹</a><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a>'
       '<a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a>'
       '<a href="giocata_multi.html">Giocate</a><a href="ppa.html">⚡ PPA</a>'
       '<a href="surebets.html">⚖️ Surebets</a><a href="schedina.html">🧾 Schedina</a>'
       '<a class="on" href="bankroll.html">💰 Bankroll</a><a href="archivio.html">Archivio+CLV</a>'
       '<a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a></nav>')

JS = r"""
var B=JSON.parse(localStorage.getItem('bankroll')||'[]');
function save(){localStorage.setItem('bankroll',JSON.stringify(B));}
function norm(t){return (t||'').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();}
function addBet(){
  var g=function(id){return document.getElementById(id).value.trim();};
  var b={data:g('f-data')||new Date().toISOString().slice(0,10),partita:g('f-partita'),mercato:g('f-mercato'),
         quota:parseFloat(g('f-quota'))||0,stake:parseFloat(g('f-stake'))||0,esito:g('f-esito')||'in corso',nota:g('f-nota')};
  if(!b.partita||!b.quota||!b.stake)return alert('Compila partita, quota e stake.');
  B.push(b);save();render();
  ['f-partita','f-quota','f-stake','f-nota'].forEach(function(id){document.getElementById(id).value='';});
}
function delBet(i){B.splice(i,1);save();render();}
function esitoVal(b){ if(b.esito==='vinta')return b.stake*(b.quota-1); if(b.esito==='persa')return -b.stake; return 0; }
function render(){
  var rows='',profitto=0,staked=0,win=0,settled=0,maxdd=0,peak=-1e9;
  B.forEach(function(b,i){
    var v=esitoVal(b);
    if(b.esito!=='in corso'){settled++;staked+=b.stake;if(b.esito==='vinta')win++;}
    profitto+=v; peak=Math.max(peak,profitto); maxdd=Math.min(maxdd,profitto-peak);
    var cls=b.esito==='vinta'?'ok':(b.esito==='persa'?'ko':'pend');
    rows+='<tr class="'+cls+'"><td>'+b.data+'</td><td>'+esc(b.partita)+'</td><td>'+esc(b.mercato)+'</td><td>'+b.quota.toFixed(2)+'</td><td>'+b.stake.toFixed(2)+'</td><td>'+b.esito+'</td><td>'+(v>=0?'+':'')+v.toFixed(2)+'</td><td><button onclick="delBet('+i+')">✕</button></td></tr>';
  });
  document.getElementById('tb').innerHTML=rows||'<tr><td colspan="8" class="sub">Nessuna giocata. Aggiungine una sopra.</td></tr>';
  var roi=staked>0?(profitto/staked*100):0;
  document.getElementById('k-roi').textContent=roi.toFixed(1)+'%';
  document.getElementById('k-wr').textContent=settled>0?(win/settled*100).toFixed(0)+'% ('+win+'/'+settled+')':'—';
  document.getElementById('k-pnl').textContent=(profitto>=0?'+':'')+profitto.toFixed(2)+' u';
  document.getElementById('k-dd').textContent=maxdd.toFixed(2)+' u';
  drawChart();
}
function drawChart(){
  var c=document.getElementById('chart'),p=0,pts=[];
  B.forEach(function(b){p+=esitoVal(b);pts.push(p);});
  if(!pts.length){c.innerHTML='<p class="sub">Nessun dato.</p>';return;}
  var w=560,h=120,min=Math.min(0,...pts),max=Math.max(0,...pts),rng=(max-min)||1;
  var step=w/(pts.length-1||1);
  var d=pts.map(function(v,i){return (i?'L':'M')+(i*step).toFixed(1)+','+(h-((v-min)/rng)*(h-10)-5).toFixed(1);}).join(' ');
  c.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" style="width:100%;max-width:560px"><line x1="0" y1="'+(h-((0-min)/rng)*(h-10)-5)+'" x2="'+w+'" y2="'+(h-((0-min)/rng)*(h-10)-5)+'" stroke="#22345a"/><path d="'+d+'" fill="none" stroke="#34d399" stroke-width="2"/></svg>';
}
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function exportCSV(){
  var h='data,partita,mercato,quota,stake,esito,nota\n';
  var csv=h+B.map(function(b){return [b.data,b.partita,b.mercato,b.quota,b.stake,b.esito,b.nota].map(function(x){return '"'+String(x).replace(/"/g,'""')+'"';}).join(',');}).join('\n');
  var a=document.createElement('a');a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);a.download='bankroll.csv';a.click();
}
function importCSV(inp){
  var f=inp.files[0];if(!f)return;
  var r=new FileReader();r.onload=function(){var lines=r.result.split('\n').slice(1);
    lines.forEach(function(l){if(!l.trim())return;var c=l.split(',');if(c.length<6)return;
      B.push({data:c[0].replace(/"/g,''),partita:c[1].replace(/"/g,''),mercato:c[2].replace(/"/g,''),quota:parseFloat(c[3])||0,stake:parseFloat(c[4])||0,esito:c[5].replace(/"/g,'')||'in corso',nota:(c[6]||'').replace(/"/g,'')});});
    save();render();};r.readAsText(f);
}
// verifica esiti via ESPN (gratis, client-side): mette vinta/persa alle 'in corso' con data passata
async function verifica(){
  var btn=document.getElementById('btn-verifica');btn.textContent='verifica in corso…';
  var byDate={};
  B.forEach(function(b){if(b.esito==='in corso'){(byDate[b.data]=byDate[b.data]||[]).push(b);}});
  var n=0;
  for(var d in byDate){
    var ds=d.replace(/-/g,'');
    try{
      var j=await (await fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates='+ds)).json();
      (j.events||[]).forEach(function(ev){
        var c=(ev.competitions||[])[0];if(!c)return;
        var st=(c.status||{}).type||{};
        if(st.state!=='post'&&!(st.name||'').match(/FULL|FINAL|POST/i))return;
        var cs=c.competitors||[];
        var h=cs.filter(function(x){return x.homeAway==='home';})[0]||{};
        var a=cs.filter(function(x){return x.homeAway==='away';})[0]||{};
        var name=norm(h.team&&h.team.displayName)+' - '+norm(a.team&&a.team.displayName);
        byDate[d].forEach(function(b){
          var bn=norm(b.partita);
          if(bn.indexOf(norm(h.team&&h.team.displayName))<0&&bn.indexOf(norm(a.team&&a.team.displayName))<0)return;
          if(name!==bn&&bn!==norm(a.team&&a.team.displayName)+' - '+norm(h.team&&h.team.displayName))return;
          var hs=+h.score||0,as=+a.score||0;
          var m=b.mercato||'';
          var res=null;
          if(/^1$|^casa/i.test(m))res=hs>as?'vinta':'persa';
          else if(/^2$|^trasferta/i.test(m))res=as>hs?'vinta':'persa';
          else if(/^X|pareggio/i.test(m))res=hs===as?'vinta':'persa';
          else if(/over/i.test(m)){var t=parseFloat(m.replace(/[^0-9.]/g,''))||2.5;res=(hs+as)>t?'vinta':'persa';}
          else if(/under/i.test(m)){var t2=parseFloat(m.replace(/[^0-9.]/g,''))||2.5;res=(hs+as)<t2?'vinta':'persa';}
          else if(/gg|btts/i.test(m))res=(hs>0&&as>0)?'vinta':'persa';
          else if(/ng/i.test(m))res=(hs===0||as===0)?'vinta':'persa';
          if(res){b.esito=res;n++;}
        });
      });
    }catch(e){console.log('verifica',d,e);}
  }
  save();render();btn.textContent='✅ verificati '+n+' esiti (fonte ESPN)';
  setTimeout(function(){btn.textContent='🔍 Verifica esiti ESPN';},4000);
}
render();
"""

PAGE = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="manifest" href="manifest.webmanifest"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>💰 Bankroll — Predictor</title>
<style>
body{{background:#0b1220;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0}}
.wrap{{max-width:900px;margin:0 auto;padding:16px}}
h1{{font-size:20px}} .sub{{color:#8ea3c8;font-size:12px}}
nav{{display:flex;flex-wrap:wrap;gap:6px;padding:8px 0;border-bottom:1px solid #1e293b;margin-bottom:12px}}
nav a{{color:#8ea3c8;text-decoration:none;font-size:12px;background:#16233d;padding:5px 9px;border-radius:12px}}
nav a.on{{background:#b91c1c;color:#fff}}
.kpis{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}
.k{{flex:1;min-width:110px;background:#101b33;border:1px solid #22345a;border-radius:10px;padding:10px;text-align:center}}
.k b{{display:block;font-size:17px;color:#93c5fd}} .k span{{font-size:10px;color:#8ea3c8;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}} th{{color:#8ea3c8;text-align:left;font-size:10.5px;text-transform:uppercase;padding:4px 6px;border-bottom:1px solid #22345a}}
td{{padding:5px 6px;border-bottom:1px solid #16233d}} tr.ok td{{color:#a7f3d0}} tr.ko td{{color:#fecaca}} tr.pend td{{color:#e2e8f0}}
form{{display:flex;flex-wrap:wrap;gap:6px;background:#101b33;border:1px solid #22345a;border-radius:10px;padding:10px;margin:12px 0}}
input,select{{background:#0b1220;color:#e2e8f0;border:1px solid #22345a;border-radius:8px;padding:7px 9px;font-size:12.5px}}
button{{background:#b91c1c;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-size:12.5px;cursor:pointer}}
button.ghost{{background:#16233d;border:1px solid #22345a}}
footer{{color:#475569;font-size:11px;text-align:center;padding:14px}}
</style></head><body><div class="wrap">
<h1>💰 Bankroll personale</h1>
<p class="sub">Le giocate restano solo nel TUO browser (localStorage) — analysis-only. Verifica esiti automatica via API pubblica ESPN. Stake consigliato: ¼ Kelly, solo EV&gt;+2%.</p>
{NAV}
<div class="kpis">
 <div class="k"><b id="k-pnl">0</b><span>profitto (u)</span></div>
 <div class="k"><b id="k-roi">—</b><span>ROI</span></div>
 <div class="k"><b id="k-wr">—</b><span>winrate</span></div>
 <div class="k"><b id="k-dd">—</b><span>max drawdown</span></div>
</div>
<div id="chart"></div>
<form onsubmit="event.preventDefault();addBet();">
 <input id="f-data" type="date" required>
 <input id="f-partita" placeholder="Partita (es. Italy - France)" style="flex:2" required>
 <input id="f-mercato" placeholder="Mercato (1/X/2/O2.5/GG…)" required>
 <input id="f-quota" type="number" step="0.01" placeholder="Quota" required>
 <input id="f-stake" type="number" step="0.01" placeholder="Stake (u)" required>
 <select id="f-esito"><option>in corso</option><option>vinta</option><option>persa</option><option>void</option></select>
 <input id="f-nota" placeholder="Nota">
 <button type="submit">+ Aggiungi</button>
</form>
<p>
 <button class="ghost" id="btn-verifica" onclick="verifica()">🔍 Verifica esiti ESPN</button>
 <button class="ghost" onclick="exportCSV()">📤 Esporta CSV</button>
 <label class="ghost" style="display:inline-block;background:#16233d;border:1px solid #22345a;border-radius:8px;padding:7px 12px;font-size:12.5px;cursor:pointer">📥 Importa CSV<input type="file" accept=".csv" style="display:none" onchange="importCSV(this)"></label>
</p>
<table><thead><tr><th>Data</th><th>Partita</th><th>Mercato</th><th>Quota</th><th>Stake</th><th>Esito</th><th>±u</th><th></th></tr></thead>
<tbody id="tb"></tbody></table>
</div>
<footer>{FOOTER}</footer>
<script>{JS}</script>
</body></html>"""

(SITE / "bankroll.html").write_text(PAGE, encoding="utf-8")
print("💰 site/bankroll.html scritto")
