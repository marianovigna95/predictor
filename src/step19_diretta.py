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
import glob
import html
import os
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
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
            try:
                from zoneinfo import ZoneInfo
                _dt = datetime.fromisoformat(ev.get("date", "").replace("Z", "+00:00"))
                hhmm = _dt.astimezone(ZoneInfo("Europe/Rome")).strftime("%H:%M")
            except Exception:
                hhmm = ev.get("date", "")[11:16]
            evs.append({"id": ev["id"], "lg": lg, "h": h["team"]["displayName"], "a": aw["team"]["displayName"],
                        "hs": h.get("score", "0"), "as": aw.get("score", "0"), "live": live,
                        "status": st["type"]["name"], "minute": minute, "ours": True,
                        "t": ev.get("date", ""), "hhmm": hhmm})
    evs.sort(key=lambda e: (not e["live"], e["lg"], e["t"]))
    return evs


def _norm(t):
    import unicodedata, re
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()

def build_qmap():
    """Mappa data|home|away (nomi normalizzati) -> quote 1X2 best-price dal CSV finestra."""
    import csv, glob, os
    qmap = {}
    base = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(base, "..", "data", "odds_window_*.csv")))
    if not files:
        return qmap
    with open(files[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = (r.get("data") or "").strip()
            h, a = _norm(r.get("home") or ""), _norm(r.get("away") or "")
            if d and h and a and r.get("best_1"):
                qmap[f"{d}|{h}|{a}"] = {"h": r["best_1"], "x": r.get("best_X") or "", "a": r.get("best_2") or ""}
    return qmap

def build_evmap():
    """EV>0 dalla finestra: chiave data|home|away -> {ev, pick, prob, odds}. EV=p*(O-1)-(1-p)."""
    import csv, glob, os, datetime
    base = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(base, "..", "data", "forecast_multi.csv")))
    out = {}
    if not files:
        return out
    year = datetime.date.today().year
    with open(files[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                o = (r.get("orario") or "").strip()          # "13/11 20:30"
                dmy = o.split(" ")[0]
                dd, mm = dmy.split("/")
                d = f"{year}-{int(mm):02d}-{int(dd):02d}"
                part = (r.get("partita") or "")
                if " - " not in part:
                    continue
                h, a = part.split(" - ", 1)
                pick = (r.get("pronostico") or "").strip()
                pcol = {"1": "p1%", "X": "pX%", "2": "p2%"}.get(pick)
                if not pcol or not r.get(pcol) or not r.get("quota_best"):
                    continue
                p = float(r[pcol]) / 100.0
                O = float(r["quota_best"])
                ev = p * (O - 1) - (1 - p)
                if ev > 0:
                    out[f"{d}|{_norm(h)}|{_norm(a)}"] = {
                        "ev": round(ev * 100, 1), "pick": pick,
                        "prob": r[pcol], "odds": r["quota_best"]}
            except Exception:
                continue
    return out

def build_h2hmap():
    """H2H ultime 5 per le coppie della finestra (forecast_multi) usando kaggle_matches.csv.
    Chiave norm(home)|norm(away) -> [{d, vs, s, w, lg}] (w dal punto di vista della chiave)."""
    import csv, os
    base = os.path.dirname(os.path.abspath(__file__))
    tg = set()
    f = os.path.join(base, "..", "data", "forecast_multi.csv")
    if os.path.exists(f):
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                part = r.get("partita", "")
                if " - " in part:
                    h, a = part.split(" - ", 1)
                    tg.add((_norm(h), _norm(a)))
    out = {}
    if not tg:
        return out
    kg = os.path.join(base, "..", "data", "kaggle_matches.csv")
    if not os.path.exists(kg):
        return out
    rows = []
    with open(kg, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            h, a = _norm(r.get("home_team", "")), _norm(r.get("away_team", ""))
            if (h, a) in tg or (a, h) in tg:
                rows.append((r.get("kickoff_utc", "")[:10], h, a,
                             r.get("ft_home", ""), r.get("ft_away", ""), r.get("league_name", "")))
    rows.sort(reverse=True)
    cnt = {}
    for d, h, a, fh_, fa, lg in rows:
        key = f"{h}|{a}"
        if cnt.get(key, 0) >= 5:
            continue
        cnt[key] = cnt.get(key, 0) + 1
        try:
            w = "H" if int(fh_) > int(fa) else ("A" if int(fh_) < int(fa) else "D")
        except Exception:
            w = "?"
        out.setdefault(key, []).append({"d": d, "vs": a, "s": f"{fh_}-{fa}", "w": w, "lg": lg})
        wi = {"H": "A", "A": "H", "D": "D"}.get(w, "?")
        out.setdefault(f"{a}|{h}", []).append({"d": d, "vs": h, "s": f"{fh_}-{fa}", "w": wi, "lg": lg})
    return out

LIVE_JS = """<script>
/* DIREtta stile diretta.it: lista per lega, render client-side da ESPN (gratis, CORS aperto).
   - ?d=YYYY-MM-DD seleziona la data (barra in alto: oggi-2 … oggi+7)
   - refresh live ogni 30s; clic su riga = dettaglio statistiche/gol (solo nostre leghe) */
(function(){
  var TODAY='__DATE__';
  var SLUG2NAME=__SLUG2NAME__;  // slug ESPN -> nome nostra lega
  var QMAP=__QMAP__;               // data|home|away -> quote 1X2 best-price (nostra finestra)
  var EVMAP=__EVMAP__;               // data|home|away -> pronostico EV>0 (nostra finestra)
  var H2H=__H2H__;                   // norm(h)|norm(a) -> ultimi H2H (storico pubblico)
  var FAV=JSON.parse(localStorage.getItem('favt')||'[]');
  function isFav(t){return FAV.indexOf(norm(t))>=0;}
  window.__fav=function(el){
    var h=el.getAttribute('data-h'), a=el.getAttribute('data-a');
    [h,a].forEach(function(t){var n=norm(t), i=FAV.indexOf(n); if(i>=0)FAV.splice(i,1); else FAV.push(n);});
    localStorage.setItem('favt', JSON.stringify(FAV));
    render(window.__evs||[]);
  };
  var FILT={live:false, ev:false, fav:false, q:'', mode:'lega'};
  var OPENLG={};                     // slug lega -> aperto pannello classifica
  var q=new URLSearchParams(location.search);
  var D=(q.get('d')||TODAY).replace(/-/g,'');
  var list=document.getElementById('lg-list');
  var sub=document.getElementById('sub')||document.querySelector('header .sub');
  if(!document.getElementById('favsug')){var _s=document.createElement('div');_s.id='favsug';_s.style.display='none';_s.style.marginTop='4px';var _h=document.querySelector('header');if(_h)_h.appendChild(_s);}
  var openDet={};
  function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
  function cd(e){
    if(!e.ts||e.live)return '';
    var ms=e.ts-Date.now(); if(ms<0)return '';
    var m=Math.floor(ms/60000), h=Math.floor(m/60);
    return 'tra '+(h>0?(h+'h '+(m%60)+'m'):(m+'m'));
  }
  function badge(e){
    var tn=(e.status||'').toUpperCase();
    if(!e.live&&e.ts&&e.ts<Date.now())tn='FULL_TIME';
    if(tn.indexOf('CANCEL')>=0||tn.indexOf('POSTPONE')>=0)return '<span class="badge b-canc">❌ Annullata</span>';
    var fl=(e.ev&&e.ev.ev>0)?'<span class="flag" title="Pronostico EV+'+e.ev.ev+'% — '+esc(e.ev.pick)+' @ '+esc(e.ev.odds)+' (p '+esc(e.ev.prob)+'%)">🚩'+e.ev.ev+'%</span>':'';
    if(e.live)return '<span class="badge b-live"><i class="dot"></i>LIVE '+esc(e.minute||'')+'</span>'+fl;
    if(tn.indexOf('FULL')>=0||tn.indexOf('FINAL')>=0)return '<span class="badge b-ft">FT</span>'+fl;
    return fl||'<span class="badge b-pre">·</span>';
  }
  function row(e){
    var st2=(''+e.status).toUpperCase(); var cls=e.live?'mrow live':((st2.indexOf('CANCEL')>=0||st2.indexOf('POSTPONE')>=0)?'mrow canc':((st2.indexOf('FULL')>=0||(e.ts&&e.ts<Date.now()))?'mrow ft':'mrow'));
    return '<div class="'+cls+'" data-eid="'+e.id+'" onclick="window.__tg(this)">'
      +'<span class="star'+(isFav(e.h)||isFav(e.a)?' on':'')+'" data-h="'+esc(e.h)+'" data-a="'+esc(e.a)+'" onclick="event.stopPropagation();window.__fav(this)" aria-label="preferito">★</span>'
      +'<span class="tm">'+esc(e.hhmm||'')+(cd(e)?' <small>'+cd(e)+'</small>':'')+'</span>'
      +'<span class="h"><img class="lg" alt="" loading="lazy" src="'+e.hl+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.h)+'</span>'
      +'<span class="sc">'+esc(e.hs)+' - '+esc(e.as)+'</span>'
      +'<span class="a"><img class="lg" alt="" loading="lazy" src="'+e.al+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.a)+'</span>'
      +'<span class="od">'+(function(){var q=qkey(e);return q&&q.h?('1 '+q.h+' · X '+(q.x||'–')+' · 2 '+q.a):'';})()+'</span>'
      +badge(e)+'</div>'
      +'<div class="det" id="det-'+e.id+'" style="display:none"></div>';
  }
  function heroCard(e){
    var badge=e.live?'<span class="badge b-live"><i class="dot"></i>LIVE '+esc(e.minute||'')+'</span>'
      :((''+e.status).toUpperCase().indexOf('FULL')>=0?'<span class="badge b-ft">FT</span>':'<span class="badge b-pre">'+esc(e.hhmm||'')+'</span>');
    var fl=(e.ev&&e.ev.ev>0)?'<span class="flag">🚩 EV+'+e.ev.ev+'% — '+esc(e.ev.pick)+' @ '+esc(e.ev.odds)+'</span>':(isFav(e.h)||isFav(e.a)?'<span class="flag">⭐ preferita</span>':'');
    var q=qkey(e);
    return '<div class="hero" data-eid="'+e.id+'" onclick="window.__tg(this)">'
      +'<div class="ht"><span>'+esc(e.lg)+' · '+esc(e.hhmm||'')+'</span>'+badge+'</div>'
      +'<div class="hm"><span class="htn"><img class="lg big" alt="" src="'+e.hl+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.h)+'</span>'
      +'<span class="hsc">'+esc(e.hs)+' - '+esc(e.as)+'</span>'
      +'<span class="htn"><img class="lg big" alt="" src="'+e.al+'" onerror="this.style.display=&quot;none&quot;">'+esc(e.a)+'</span></div>'
      +'<div class="hb">'+fl+(q&&q.h?'<span class="od">1 '+q.h+' · X '+(q.x||'–')+' · 2 '+q.a+'</span>':'')+'</div>'
      +'</div><div class="det" id="det-'+e.id+'" style="display:none"></div>';
  }
  function render(evs){
    window.__evs=evs;
    evs.forEach(function(e){e.ev=evkey(e);});
    var f=evs.filter(function(e){
      if(FILT.live&&!e.live)return false;
      if(FILT.ev&&!(e.ev&&e.ev.ev>0))return false;
      if(FILT.fav&&!(isFav(e.h)||isFav(e.a)))return false;
      if(FILT.q){var q=norm(FILT.q); var hay=norm(e.h+' '+e.a+' '+e.lg); if(hay.indexOf(q)<0 && !(matchQ(FILT.q,norm(e.h))||matchQ(FILT.q,norm(e.a))))return false;}
      return true;
    });
    var liveN=evs.filter(function(e){return e.live;}).length;
  // 🆕 13/11 suggerimento filtro ⭐ se ci sono preferite e il filtro non è attivo
  var favN0=evs.filter(function(e){return isFav(e.h)||isFav(e.a);}).length;
  var sug=document.getElementById('favsug');
  if(sug){sug.style.display=(favN0>0&&!FILT.fav)?'block':'none';sug.innerHTML='<a href="#" id="favsug-a" style="color:#fbbf24;font-size:12px">⭐ hai <b>'+favN0+'</b> partite preferite — filtra solo ⭐</a>';}
    var evN=evs.filter(function(e){return e.ev&&e.ev.ev>0;}).length;
    var favN=evs.filter(function(e){return isFav(e.h)||isFav(e.a);}).length;
    fbar.querySelectorAll('button[data-f]').forEach(function(b){
      var k=b.getAttribute('data-f'), n=k==='live'?liveN:(k==='ev'?evN:(k==='fav'?favN:0));
      if(n>0){var sp=b.querySelector('i.n'); if(!sp){sp=document.createElement('i');sp.className='n';sp.style.cssText='font-style:normal;background:rgba(255,255,255,.25);border-radius:8px;padding:0 5px;margin-left:4px;font-size:10px';b.appendChild(sp);} sp.textContent=n;}
    });
    var out='';
    if(FILT.mode==='lega'){
      // 🏆 hero: partita in evidenza (max EV>0, altrimenti prima ⭐)
      var hero=evs.filter(function(e){return e.ev&&e.ev.ev>0;}).sort(function(a,b){return b.ev.ev-a.ev.ev;})[0]
            || evs.filter(function(e){return isFav(e.h)||isFav(e.a);})[0];
      if(hero) out+=heroCard(hero);
    }
    if(FILT.mode==='orario'){
      f.sort(function(x,y){return (x.live===y.live)?(x.ts-y.ts):(x.live?-1:1);});
      f.forEach(function(e){out+=row(e);});
    }else{
      var bylg={};
      f.forEach(function(e){(bylg[e.lg]=bylg[e.lg]||[]).push(e);});
      Object.keys(bylg).sort().forEach(function(lg){
        var slg='';
        for(var k in SLUG2NAME){if(SLUG2NAME[k]===lg){slg=k;break;}}
        out+='<div class="lgh'+(slg?' lgc':'')+'"'+(slg?' data-slg="'+slg+'" onclick="window.__tl(this)"':'')+'>'
          +'<span>'+esc(lg)+'</span>'+(slg?'<span class="chev">'+(OPENLG[slg]?'▾':'▸')+' classifica</span>':'')+'</div>';
        bylg[lg].forEach(function(e){out+=row(e);});
        if(slg&&OPENLG[slg]) out+='<div class="lgdet" id="lgd-'+slg+'"><p class="sub" style="padding:8px">caricamento classifica…</p></div>';
      });
    }
    list.innerHTML=out||'<p class="sub" style="padding:14px">Nessuna partita corrisponde ai filtri.</p>';
    if(sub)sub.textContent=f.length+' partite · '+liveN+' LIVE · 🚩 '+evN+' con pronostico EV>0 · aggiornate '+new Date().toLocaleTimeString('it-IT')+' · dati live da fonti pubbliche gratuite';
    // riapplica dettagli aperti (con html già caricato)
    Object.keys(openDet).forEach(function(id){var d=document.getElementById('det-'+id);if(d&&openDet[id]){d.style.display='block';d.innerHTML=openDet[id];}});
  }
  window.__tg=function(el){
    var id=el.getAttribute('data-eid');
    var ev=((window.__evs||[]).filter(function(e){return e.id===id;})[0])||{};
    var d=document.getElementById('det-'+id);
    if(!d)return;
    if(openDet[id]){openDet[id]=false;d.style.display='none';return;}
    d.style.display='block';d.innerHTML='<p class="sub" style="padding:6px 10px">caricamento…</p>';
    fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event='+id+'&lang=it&region=it')
      .then(function(r){return r.json();}).then(function(j){
        function iconFor(t){t=(t||'').toLowerCase();if(/goal/.test(t))return'⚽';if(/red card/.test(t))return'🟥';if(/yellow/.test(t))return'🟨';if(/substitut/.test(t))return'🔁';if(/var|video/.test(t))return'🎥';if(/penalt/.test(t))return'🅿️';return'•';}
        var evs2=(j.keyEvents||[]).slice().sort(function(a,b){var ca=parseFloat((a.clock&&a.clock.value)||0),cb=parseFloat((b.clock&&b.clock.value)||0);return cb-ca;});
        var goals=evs2.slice(0,20).map(function(k){return esc((k.clock&&k.clock.displayValue)||'')+' '+iconFor(k.text)+' '+esc(k.text||'');});
        var W=['expectedGoals','possessionPct','totalShots','shotsOnTarget','bigChances','wonCorners','foulsCommitted','offsides','yellowCards','redCards','saves','accuratePasses','totalPasses','passPct'];
        var teams=(j.boxscore&&j.boxscore.teams)||[];
        var map={};
        teams.forEach(function(t,i){(t.statistics||[]).forEach(function(st){(map[st.name]=map[st.name]||[null,null])[i]=st.displayValue;});});
        // 📊 barre comparative stile diretta.it
        function bar(lab,v0,v1,raw){
          v0=parseFloat(v0)||0; v1=parseFloat(v1)||0;
          var p0,p1;
          if(raw){p0=v0; p1=v1;} else {var m=Math.max(v0,v1,0.001); p0=v0/m*100; p1=v1/m*100;}
          return '<div class="bst"><span class="bl">'+lab+'</span><div class="bt"><i class="bh" style="width:'+Math.min(100,p0)+'%"></i><i class="ba" style="width:'+Math.min(100,p1)+'%"></i></div><span class="bv">'+esc(v0)+' · '+esc(v1)+'</span></div>';
        }
        var bars='';
        if(map['expectedGoals']) bars+=bar('xG',map['expectedGoals'][0],map['expectedGoals'][1]);
        if(map['possessionPct']) bars+=bar('Possesso %',map['possessionPct'][0],map['possessionPct'][1],true);
        if(map['totalShots']) bars+=bar('Tiri',map['totalShots'][0],map['totalShots'][1]);
        if(map['shotsOnTarget']) bars+=bar('Tiri in porta',map['shotsOnTarget'][0],map['shotsOnTarget'][1]);
        if(map['bigChances']) bars+=bar('Pal. grosse',map['bigChances'][0],map['bigChances'][1]);
        if(bars) bars='<p class="stt">📊 Live — '+h0+' vs '+h1+'</p><div class="bars2">'+bars+'</div>';
        var h0=teams[0]&&teams[0].team?esc(teams[0].team.displayName):'';
        var h1=teams[1]&&teams[1].team?esc(teams[1].team.displayName):'';
        var WGRP=[['📊 Panoramica',['expectedGoals','possessionPct','totalShots','shotsOnTarget','bigChances','saves']],['⚽ Gioco',['wonCorners','foulsCommitted','offsides','accuratePasses','totalPasses','passPct']],['🟨 Cartellini',['yellowCards','redCards']]];
        var rows='';
        W.forEach(function(nm){var v=map[nm]; if(v&&(v[0]||v[1])) rows+='<tr><td>'+esc(nm)+'</td><td>'+esc(v[0]||'')+'</td><td>'+esc(v[1]||'')+'</td></tr>';});
        var tabsHtml='';
        if(rows){
          tabsHtml='<div class="tabs">'+WGRP.map(function(g,i){return '<button class="tab'+(i===0?' on':'')+'" data-t="'+i+'">'+g[0]+'</button>';}).join('')+'</div><div class="tpanes">';
          WGRP.forEach(function(g,i){
            var rr='';
            g[1].forEach(function(nm){var v=map[nm]; if(v&&(v[0]||v[1])) rr+='<tr><td>'+esc(nm)+'</td><td>'+esc(v[0]||'')+'</td><td>'+esc(v[1]||'')+'</td></tr>';});
            tabsHtml+='<div class="tpane" data-p="'+i+'" style="'+(i===0?'':'display:none')+'">'+(rr?'<table><tr><th>'+esc(h0)+'</th><th></th><th>'+esc(h1)+'</th></tr>'+rr+'</table>':'<p class="sub">nessun dato</p>')+'</div>';
          });
          tabsHtml+='</div>';
        }
        // QUOTE 1X2 (dagli odds dello scoreboard ESPN)
        var qq=qkey(ev);
        var q=(qq&&qq.h?'<p class="stt">Quote 1X2 (miglior prezzo finestra)</p><div class="q3"><span>1<b>'+qq.h+'</b></span><span>X<b>'+(qq.x||'–')+'</b></span><span>2<b>'+qq.a+'</b></span></div>':'');
        // FORMA ultime 5 (lastFiveGames ESPN)
        function forma(t){
          var evs=(t.events||[]).slice(0,10);
          if(!evs.length)return '';
          var tid=(t.team&&t.team.id)||null;
          var dot=evs.map(function(g){
            var r=g.gameResult||'';
            var c=r==='W'?'g':(r==='D'?'y':'r');
            return '<i class="'+c+'" title="'+(g.score||'')+' vs '+esc((g.opponent&&g.opponent.abbreviation)||'')+'">'+r+'</i>';
          }).join('');
          var bars=evs.map(function(g){
            var gf=0;
            try{ gf=(tid&&String(g.homeTeamId)===String(tid))?(parseInt(g.homeTeamScore)||0):(parseInt(g.awayTeamScore)||0); }catch(e){}
            var r=g.gameResult||'';
            var c=r==='W'?'#34d399':(r==='D'?'#fbbf24':'#f87171');
            var h=Math.min(28,6+gf*6);
            return '<i class="bar" title="gol fatti: '+gf+' ('+(g.score||'')+')" style="height:'+h+'px;background:'+c+'"></i>';
          }).join('');
          return '<div class="frm"><b>'+esc((t.team&&t.team.abbreviation)||'')+'</b> '+dot+'</div><div class="bars">'+bars+'</div>';
        }
        var lfg=j.lastFiveGames||[];
        var fhtml=(lfg.length?'<p class="stt">Forma — ultime '+(lfg[0].events||[]).length+'</p>'+lfg.map(forma).join(''):'<p class="sub">forma non disponibile</p>');
        // 🤝 H2H (kaggle)
        var hk=norm(ev.h)+'|'+norm(ev.a);
        var hh=H2H[hk]||H2H[norm(ev.a)+'|'+norm(ev.h)];
        var h2hhtml='';
        if(hh&&hh.length){
          h2hhtml='<p class="stt">🤝 Ultimi H2H</p><table><tr><th>Data</th><th>Avversario</th><th>Ris</th><th>Esito</th></tr>';
          hh.slice(0,5).forEach(function(g){
            var es=g.w==='H'?'V':(g.w==='A'?'P':'N');
            var c=g.w==='H'?'g':(g.w==='A'?'r':'y');
            h2hhtml+='<tr><td>'+esc(g.d)+'</td><td>'+esc(g.vs)+'</td><td><b>'+esc(g.s)+'</b></td><td><i class="'+c+'" style="font-style:normal;width:16px;height:16px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:#04101f">'+es+'</i></td></tr>';
          });
          h2hhtml+='</table>';
        }
        // ⚽ formazioni + titolari (ESPN rosters, gratis)
        var lin='';
        var ros=j.rosters||[];
        if(ros.length===2){
          function lineup(t){
            var st=(t.roster||[]).filter(function(a){return a.starter;});
            var h='<div class="lin"><b>'+esc((t.team.shortDisplayName||t.team.displayName||''))+'</b> <span class="fmt">'+esc(t.formation||'')+'</span><ul>';
            st.forEach(function(a){
              var nm=(a.athlete&&(a.athlete.shortName||a.athlete.displayName))||'';
              h+='<li><i>'+esc(a.jersey||'')+'</i> '+esc(nm)+' <em>'+esc((a.position&&a.position.abbreviation)||'')+'</em></li>';
            });
            return h+'</ul></div>';
          }
          lin='<p class="stt">⚽ Formazioni</p><div class="lins">'+lineup(ros[0])+lineup(ros[1])+'</div>';
        }
        // 🆕 13/11 🔴 EV live Over 2.5: xG live ESPN + Poisson sui minuti rimanenti
        function poisCDF(k,lam){var s=0,p=Math.exp(-lam);for(var i=0;i<=k;i++){s+=p;p*=lam/(i+1);}return s;}
        var liveev='';
        try{
          if(ev.live){
            var min=parseFloat(String(ev.minute||'').replace(/[^0-9.]/g,''))||0;
            var gol=(parseInt(ev.hs||0)+parseInt(ev.as||0));
            var xgt=0; (map['expectedGoals']||[]).forEach(function(v){xgt+=parseFloat(v)||0;});
            if(min>=30&&min<90){
              var lamRem=xgt>0?xgt*(90-min)/Math.max(min,1):0;
              var need=3-gol;
              var pOver=need<=0?1:1-poisCDF(need-1,lamRem);
              var oq=null;
              (ev.odds||[]).forEach(function(o){var lbl=String(o.name||'')+' '+String(o.label||'');if(/2\.5|over|under/i.test(lbl)){(o.outcomes||[]).forEach(function(oc){if(/over/i.test(String(oc.name||oc.description||'')))oq=parseFloat(oc.price||oc.odds)||oq;});}});
              // 🆕 13/11 proiezione live 1X2 da xG live (Poisson sui gol attesi finali)
              var xgh=parseFloat((map['expectedGoals']||[])[0])||0, xga=parseFloat((map['expectedGoals']||[])[1])||0;
              var lamH=gol>0?(parseInt(ev.hs||0)+xgh*(90-min)/Math.max(min,1)):xgh, lamA=(parseInt(ev.as||0))+xga*(90-min)/Math.max(min,1);
              function pois(k,l){var p=Math.exp(-l),s=0;for(var i=0;i<=k;i++){s+=p;p*=l/(i+1);}return s;}
              var PH=0,PD=0,PA=0;
              for(var i=0;i<=8;i++){for(var j=0;j<=8;j++){var pr=pois(i,lamH)*pois(j,lamA);if(i>j)PH+=pr;else if(i<j)PA+=pr;else PD+=pr;}}
              liveev='<p class="stt">🔴 Proiezione live 1X2 (min '+Math.round(min)+') — da xG live '+xgt.toFixed(2)+' + gol '+gol+'</p><p class="sub"><b>1 '+(PH*100).toFixed(0)+'% · X '+(PD*100).toFixed(0)+'% · 2 '+(PA*100).toFixed(0)+'%</b> · EV live Over 2.5: λ residuo '+lamRem.toFixed(2)+' → <b>p '+(pOver*100).toFixed(1)+'%</b>';
              if(oq&&oq>1.01){var evv=(pOver*(oq-1)-(1-pOver))*100;liveev+=' · quota live O2.5 '+oq.toFixed(2)+' → <b>EV '+(evv>=0?'+':'')+evv.toFixed(1)+'%</b>'+(evv>2?' 🚩':'');}
              // 🆕 13/11 EV live su 1X2: pick con p live max vs quota live moneyline ESPN
              var q12={};(ev.odds||[]).forEach(function(o){var lbl=String(o.name||'')+' '+String(o.label||'');if(/moneyline|1x2|match result|h2h/i.test(lbl)||(o.outcomes&&o.outcomes.length===3)){(o.outcomes||[]).forEach(function(oc){var nm=String(oc.name||oc.description||'');var pr=parseFloat(oc.price||oc.odds)||0;if(/home|casa|1\b/i.test(nm))q12.h=pr;else if(/away|trasferta|2\b/i.test(nm))q12.a=pr;else if(/draw|pareggio|x\b/i.test(nm))q12.x=pr;});}});
              var pl=[[PH,q12.h],[PD,q12.x],[PA,q12.a]], pk=pl[0];
              pl.forEach(function(z){if(z[0]>pk[0])pk=z;});
              if(pk[1]&&pk[1]>1.01){var ev12=(pk[0]*(pk[1]-1)-(1-pk[0]))*100;liveev+=' · 1X2 live <b>'+['1','X','2'][pl.indexOf(pk)]+'</b> p '+(pk[0]*100).toFixed(0)+'% @ '+pk[1].toFixed(2)+' → <b>EV '+(ev12>=0?'+':'')+ev12.toFixed(1)+'%</b>'+(ev12>2?' 🚩':'');}
              // 🆕 13/11 💬 perché in parole semplici (xG live + margine quota)
              var pwhy='';
              if(xgt>0.05){
                var teamLead=xgh>xga?ev.h:ev.a, other=xgh>xga?ev.a:ev.h;
                var lead=xgh>xga?(xgh-xga):(xga-xgh);
                if(lead>=0.5)pwhy='💬 Perché: xG live a favore di <b>'+esc(teamLead)+'</b> ('+xgt.toFixed(1)+' contro '+(xgh>xga?(xga).toFixed(1):(xgh).toFixed(1))+' di '+esc(other)+') — il modello vede più gioco offensivo di chi conduce.';
                else pwhy='💬 Perché: xG live quasi pari ('+xgh.toFixed(1)+' - '+xga.toFixed(1)+'), partita ancora aperta.';
              }
              if(pk&&pk[1]>1.01&&pk[0]>0.5){var impl=(100/pk[1]).toFixed(0);pwhy+=' La quota live '+pk[1].toFixed(2)+' paga come se valesse '+impl+'%, il modello dà '+(pk[0]*100).toFixed(0)+'%'+(pk[0]*100-parseFloat(impl)>=2?': c’è margine.':'.');}
              else if(oq&&oq>1.01&&pOver>0.5){var implO=(100/oq).toFixed(0);pwhy+=' Over 2.5: restano ~'+Math.max(0,3-gol)+' gol da fare, quota '+oq.toFixed(2)+' (mercato '+implO+'%) vs modello '+(pOver*100).toFixed(0)+'%'+(pOver*100-parseFloat(implO)>=2?': c’è margine.':'.');}
              if(pwhy)liveev+='<p class="perche">'+pwhy+'</p>';
              liveev+='</p><p class="sub" style="font-size:10px">stima da xG live (ESPN) + Poisson minuti rimanenti — solo analisi, puntare SOLO su ADM · 18+ · autoesclusione.it · 800 558822</p>';
            }
          }
        }catch(e){}
        var html=q+fhtml+h2hhtml+lin+bars+liveev+(goals.length?'<p class="stt">🕐 Timeline (eventi recenti in cima)</p><ul class="ev">'+goals.map(function(g){return '<li>'+g+'</li>';}).join('')+'</ul>':'')
          +(rows.length?tabsHtml
            :(ev.live||/FULL|FINAL|POST/i.test(ev.status||'')
              ?'<p class="sub">Statistiche live in aggiornamento — ESPN le pubblica a intervalli durante la gara e complete a fine partita.</p>'
              :'<p class="sub">Partita non ancora iniziata: le statistiche escono dal fischio di inizio.</p>'))
          +'<p class="sub" style="font-size:11px">dati da fonti pubbliche gratuite · nessun reindirizzamento</p>';
        // 📊 confronto stagionale (standings della lega) + 🔗 share
        var slg=''; for(var k in SLUG2NAME){if(SLUG2NAME[k]===ev.lg){slg=k;break;}}
        var extra='';
        if(slg&&(ev.hid||ev.aid)){
          fetch('https://site.web.api.espn.com/apis/v2/sports/soccer/'+slg+'/standings?season='+new Date().getFullYear())
            .then(function(r){return r.json();}).then(function(st){
              var rows='',found=0;
              (st.children||[]).forEach(function(ch){
                (ch.standings.entries||[]).forEach(function(en){
                  if(String(en.team.id)!==String(ev.hid)&&String(en.team.id)!==String(ev.aid))return;
                  var m={};(en.stats||[]).forEach(function(x){m[x.name]=x.displayValue!=null?x.displayValue:x.value;});
                  rows+='<tr><td>'+esc(en.team.shortDisplayName||en.team.displayName)+'</td><td>'+esc(m.rank||'')+'</td><td>'+esc(m.gamesPlayed||'')+'</td><td>'+esc(m.wins||'')+'-'+esc(m.ties||'')+'-'+esc(m.losses||'')+'</td><td>'+esc(m.pointsFor||'')+':'+esc(m.pointsAgainst||'')+'</td><td><b>'+esc(m.points||'')+'</b></td></tr>';
                  found++;
                });
              });
              if(found){
                extra='<p class="stt">📊 Stagione in corso ('+esc(ev.lg)+')</p><table><tr><th>Squadra</th><th>#</th><th>G</th><th>V-N-P</th><th>Gol</th><th>Pt</th></tr>'+rows+'</table>';
                d.innerHTML=html+extra;
              }
            }).catch(function(){});
        }
        extra='<p class="sub" style="margin-top:8px"><a href="#" data-share="'+id+'" style="color:#93c5fd">🔗 copia link partita</a></p>';
        openDet[id]=html+extra;
        d.innerHTML=html+extra;
      }).catch(function(){d.innerHTML='<p class="sub">dettaglio non disponibile</p>';});
  };
  function norm(t){return (t||'').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();}
var ALIAS={"psg":"paris saint","bayern":"bayern munchen","milan":"ac milan","inter":"inter","napoli":"napoli","juve":"juventus","roma":"as roma","lazio":"ss lazio","atalanta":"atalanta","fiorentina":"fiorentina","toro":"torino","bologna":"bologna","sassuolo":"sassuolo","udinese":"udinese","monza":"monza","verona":"hellas verona","empoli":"empoli","parma":"parma","genoa":"genoa","cagliari":"cagliari","lecce":"lecce","venezia":"venezia","cremonese":"cremonese","como":"como","barcellona":"barcelona","barca":"barcelona","atletico":"atletico madrid","real sociedad":"real sociedad","betis":"real betis","sevilla":"sevilla","valencia":"valencia","villareal":"villarreal","girona":"girona","arsenal":"arsenal","chelsea":"chelsea","liverpool":"liverpool","city":"manchester city","united":"manchester united","spurs":"tottenham","newcastle":"newcastle","villa":"aston villa","west ham":"west ham","wolves":"wolverhampton","everton":"everton","brighton":"brighton","palace":"crystal palace","fulham":"fulham","brentford":"brentford","bayern":"bayern","dortmund":"borussia dortmund","leverkusen":"bayer leverkusen","leipzig":"rb leipzig","frankfurt":"eintracht frankfurt","stuttgart":"stuttgart","wolfsburg":"wolfsburg","gladbach":"borussia monchengladbach","psg":"paris saint","monaco":"as monaco","lyon":"lyon","marsiglia":"marseille","lille":"lille","nice":"nice","rennes":"rennes","strasburgo":"strasbourg","benfica":"benfica","porto":"fc porto","sporting":"sporting","ajax":"ajax","psv":"psv","feyenoord":"feyenoord","galata":"galatasaray","fener":"fenerbahce","besiktas":"besiktas","olympiakos":"olympiacos","panathinaikos":"panathinaikos","celtic":"celtic","rangers":"rangers"};
function matchQ(q,nn){var nq=norm(q);if(!nq)return false;if(nn.indexOf(nq)>=0||nq.indexOf(nn)>=0)return true;
  for(var k in ALIAS){if(nq.indexOf(k)>=0||k.indexOf(nq)>=0){if(nn.indexOf(ALIAS[k])>=0)return true;}}
  return false;}
  function qkey(e){
    var dk=D.substr(0,4)+'-'+D.substr(4,2)+'-'+D.substr(6,2);
    var h=norm(e.h), a=norm(e.a);
    var q=QMAP[dk+'|'+h+'|'+a];
    if(!q && QMAP[dk+'|'+a+'|'+h]){var s2=QMAP[dk+'|'+a+'|'+h]; q={h:s2.a, x:s2.x, a:s2.h};}
    if(!q){
      // fuzzy: stessa data, nomi simili
      var pre=dk+'|';
      for(var k in QMAP){ if(k.indexOf(pre)!==0) continue;
        var p=k.slice(pre.length).split('|');
        if((p[0].indexOf(h)>=0||h.indexOf(p[0])>=0)&&(p[1].indexOf(a)>=0||a.indexOf(p[1])>=0)){q=QMAP[k];break;}
      }
    }
    return q;
  }
  function evkey(e){
    var dk=D.substr(0,4)+'-'+D.substr(4,2)+'-'+D.substr(6,2);
    var h=norm(e.h), a=norm(e.a);
    var q=EVMAP[dk+'|'+h+'|'+a];
    if(!q && EVMAP[dk+'|'+a+'|'+h]){var s2=EVMAP[dk+'|'+a+'|'+h]; q={ev:s2.ev, pick:s2.pick==='1'?'2':(s2.pick==='2'?'1':s2.pick), prob:s2.prob, odds:s2.odds};}
    if(!q){
      var pre=dk+'|';
      for(var k in EVMAP){ if(k.indexOf(pre)!==0) continue;
        var p=k.slice(pre.length).split('|');
        if((p[0].indexOf(h)>=0||h.indexOf(p[0])>=0)&&(p[1].indexOf(a)>=0||a.indexOf(p[1])>=0)){q=EVMAP[k];break;}
      }
    }
    return q;
  }
  function evOf(ev, lg){
    var c=ev.competitions[0];if(!c)return null;
    var cs=c.competitors||[];
    var h=cs.filter(function(x){return x.homeAway==='home';})[0]||cs[0];
    var a=cs.filter(function(x){return x.homeAway==='away';})[0]||cs[1];
    if(!h||!a)return null;
    var st=c.status||{type:{}};
    function am(m){if(m==null)return null; m=+m; return m>0?(1+m/100):(1+100/(-m));}
    var od=null;
    (c.odds||[]).forEach(function(o){
      if(od||!o)return;
      var h=am(o.homeTeamOdds&&o.homeTeamOdds.moneyLine), x=am(o.drawOdds&&o.drawOdds.moneyLine), a=am(o.awayTeamOdds&&o.awayTeamOdds.moneyLine);
      if(h&&x&&a) od={h:h.toFixed(2), x:x.toFixed(2), a:a.toFixed(2)};
    });
    return {id:ev.id, lg:lg, h:h.team.displayName, a:a.team.displayName,
            hid:h.team.id||'', aid:a.team.id||'',
            hl:'https://a.espncdn.com/i/teamlogos/soccer/500/'+(h.team.id||'')+'.png',
            al:'https://a.espncdn.com/i/teamlogos/soccer/500/'+(a.team.id||'')+'.png',
            hs:h.score||'0', as:a.score||'0', live:st.type.state==='in', status:st.type.name||'',
            minute:st.displayClock||'', hhmm:new Date(ev.date||0).toLocaleTimeString('it-IT',{timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit'}), odds:od, ts:Date.parse(ev.date||'')};
  }
  function tick(){
    // scoreboard PER SLUG delle nostre leghe (l'endpoint 'all' non porta lo slug sull'evento)
    var slugs=Object.keys(SLUG2NAME);
    Promise.all(slugs.map(function(slg){
      return fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/'+slg+'/scoreboard?dates='+D)
        .then(function(r){return r.json();})
        .then(function(j){return (j.events||[]).map(function(ev){return evOf(ev, SLUG2NAME[slg]);}).filter(Boolean);})
        .catch(function(){return [];});
    })).then(function(groups){
      var evs=[]; groups.forEach(function(g){evs=evs.concat(g);});
      if(!evs.length){ tryFix(); return; }   // 🚨 ESPN giù → fallback calendario nostro
      evs.sort(function(x,y){if(x.live!==y.live)return x.live?-1:1; if(x.lg!==y.lg)return x.lg<x.lg?-1:1; return (x.hhmm<x.hhmm?-1:1);});
      render(evs);
    });
  }
  var FIX=null;
  function tryFix(){
    fetch('fixtures.json').then(function(r){return r.json();}).then(function(fx){
      FIX=fx;
      var dk=D.substr(0,4)+'-'+D.substr(4,2)+'-'+D.substr(6,2);
      var evs=fx.filter(function(f){return f[0]===dk;}).map(function(f,i){
        return {id:'fix-'+i, lg:f[4]||'Altro', h:f[2], a:f[3], hid:'', aid:'', hl:'', al:'',
                hs:'', as:'', live:false, status:'', minute:'', hhmm:'', odds:null, ts:Date.parse(f[0]+'T12:00:00Z')};
      });
      render(evs);
      if(sub)sub.textContent='⚠️ ESPN non risponde — calendario da fixtures.json (aggiorna tra 30s) · '+evs.length+' partite';
    }).catch(function(){render([]);});
  }
  // barra date: oggi-2 … oggi+7 (click delegato, niente onclick inline)
  function dstr(d){return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);}
  var bar=document.getElementById('daybar');
  if(bar){
    var now=new Date();           // OGGI reale (browser in Italia) — la barra non slitta mai
    var todayStr=dstr(now);
    var html='';
    for(var i=-2;i<=7;i++){
      var dd=new Date(now); dd.setDate(now.getDate()+i);
      var lab=(dstr(dd)===todayStr?'Oggi ':(dd.getDate()+'/'+(dd.getMonth()+1)));
      html+='<button class="dbtn'+(dstr(dd)===D?' on':'')+'" data-d="'+dstr(dd)+'">'+lab+'</button>';
    }
    bar.innerHTML=html;
    bar.addEventListener('click',function(e){
      var b=e.target.closest('.dbtn'); if(b) location.search='?d='+b.getAttribute('data-d');
    });
  }
  // 🆕 13/11 tab statistiche nel dettaglio (delegato)
  document.addEventListener('click',function(e){
    var t=e.target.closest?e.target.closest('.tab'):null;
    if(!t)return;
    var tabs=t.parentElement.querySelectorAll('.tab');
    tabs.forEach(function(x){x.classList.toggle('on',x===t);});
    var panes=t.parentElement.parentElement.querySelectorAll('.tpane');
    panes.forEach(function(p){p.style.display=(p.getAttribute('data-p')===t.getAttribute('data-t'))?'':'none';});
  });
  // 🆕 13/11 click sul suggerimento ⭐ -> attiva filtro fav
  document.addEventListener('click',function(e){if(e.target&&e.target.id==='favsug-a'){e.preventDefault();var b=document.querySelector('button[data-f=fav]');if(b)b.click();}});
  // ---- barra filtri ----
  var fbar=document.getElementById('fbar');
  if(fbar){
    fbar.addEventListener('click',function(e){
      var b=e.target.closest('button'); if(!b)return;
      if(b.getAttribute('data-f')){
        var fv=b.getAttribute('data-f'); FILT.live=fv==='live'; FILT.ev=fv==='ev'; FILT.fav=fv==='fav';
        fbar.querySelectorAll('button[data-f]').forEach(function(x){x.classList.toggle('on',x===b);});
      }else{
        FILT.mode=b.getAttribute('data-m');
        fbar.querySelectorAll('button[data-m]').forEach(function(x){x.classList.toggle('on',x===b);});
      }
      render(window.__evs||[]);
    });
    var fq=document.getElementById('fq');
    if(fq) fq.addEventListener('input',function(){FILT.q=fq.value; render(window.__evs||[]);});
  }
  // ---- classifica + capocannonieri per lega ----
  window.__tl=function(el){
    var slg=el.getAttribute('data-slg'); if(!slg)return;
    var d=document.getElementById('lgd-'+slg);
    if(OPENLG[slg]){OPENLG[slg]=false; render(window.__evs||[]); return;}
    OPENLG[slg]=true; render(window.__evs||[]);
    d=document.getElementById('lgd-'+slg); if(!d)return;
    var yr=new Date().getFullYear();
    var st=fetch('https://site.web.api.espn.com/apis/v2/sports/soccer/'+slg+'/standings?season='+yr)
      .then(function(r){return r.json();}).catch(function(){return null;});
    var ld=fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/'+slg+'/statistics?season='+yr)
      .then(function(r){return r.json();}).catch(function(){return null;});
    Promise.all([st,ld]).then(function(res){
      var html='';
      var s=res[0];
      if(s&&s.children){
        s.children.forEach(function(ch){
          if(s.children.length>1) html+='<p class="stt">'+esc(ch.name||'Girone')+'</p>';
          html+='<table><tr><th>#</th><th style="text-align:left">Squadra</th><th>G</th><th>V</th><th>N</th><th>P</th><th>GF</th><th>GS</th><th>Pt</th><th>Serie</th></tr>';
          (ch.standings.entries||[]).forEach(function(en){
            var m={}; (en.stats||[]).forEach(function(x){m[x.name]=x.displayValue!=null?x.displayValue:x.value;});
            html+='<tr><td>'+esc(m.rank||'')+'</td><td>'+esc((en.team.shortDisplayName||en.team.displayName||''))+'</td><td>'+esc(m.gamesPlayed||'')+'</td><td>'+esc(m.wins||'')+'</td><td>'+esc(m.ties||'')+'</td><td>'+esc(m.losses||'')+'</td><td>'+esc(m.pointsFor||'')+'</td><td>'+esc(m.pointsAgainst||'')+'</td><td><b>'+esc(m.points||'')+'</b></td><td>'+esc(m.overall||'')+'</td></tr>';
          });
          html+='</table>';
        });
      }
      var l=res[1], goals=null;
      if(l&&l.stats){ (l.stats||[]).forEach(function(c){ if(c.name==='goalsLeaders') goals=c; }); }
      if(goals&&goals.leaders&&goals.leaders.length){
        html+='<p class="stt">🥅 Capocannonieri</p><table><tr><th>#</th><th style="text-align:left">Giocatore</th><th>G</th><th>Partite</th></tr>';
        goals.leaders.slice(0,5).forEach(function(g,i){
          var dv=g.displayValue||''; var gm=(dv.match(/Matches:\s*(\d+)/)||[])[1]||''; var gg=(dv.match(/Goals:\s*(\d+)/)||[])[1]||g.displayValue;
          html+='<tr><td>'+(i+1)+'</td><td>'+esc((g.athlete&&g.athlete.displayName)||'')+'</td><td><b>'+esc(gg)+'</b></td><td>'+esc(gm)+'</td></tr>';
        });
        html+='</table>';
      }
      d.innerHTML=html||'<p class="sub" style="padding:8px">Classifica non disponibile per questa lega.</p>';
    });
  };
  window.__share=function(id){
    var url=location.origin+location.pathname+'?d='+D+'#'+id;
    if(navigator.share){navigator.share({title:document.title,url:url}).catch(function(){});}
    else if(navigator.clipboard){navigator.clipboard.writeText(url).then(function(){alert('Link copiato: '+url);});}
  };
  // apri dettaglio da hash (#eventId)
  if(location.hash.length>1){
    var hid2=location.hash.slice(1);
    setTimeout(function(){var el=document.querySelector('[data-eid="'+hid2+'"]'); if(el)window.__tg(el);},1500);
  }
  document.addEventListener('click',function(e){
    var a=e.target.closest?e.target.closest('[data-share]'):null;
    if(a){e.preventDefault(); window.__share(a.getAttribute('data-share'));}
  });
  // ☀️ tema chiaro/scuro (salvato)
  var th=document.getElementById('th');
  function setTheme(t){document.documentElement.setAttribute('data-theme',t);localStorage.setItem('theme',t);th.textContent=t==='light'?'🌙':'☀️';}
  setTheme(localStorage.getItem('theme')||'dark');
  if(th)th.addEventListener('click',function(){setTheme(document.documentElement.getAttribute('data-theme')==='light'?'dark':'light');});
  var fz=document.getElementById('fsz');
  if(localStorage.getItem('bigfont')==='1')document.documentElement.classList.add('big');
  if(fz)fz.addEventListener('click',function(){
    var on=document.documentElement.classList.toggle('big');
    localStorage.setItem('bigfont',on?'1':'0'); fz.textContent=on?'A−':'A+';
  });
  if(localStorage.getItem('bigfont')==='1'&&fz)fz.textContent='A−';
  // 📲 installa PWA
  var dp=null,ib=document.getElementById('inst');
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();dp=e;if(ib)ib.style.display='inline-block';});
  if(ib)ib.addEventListener('click',function(){if(dp)dp.prompt();});
  window.__F=FILT; window.__R=render;
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
:root{{--bg:#0b1220;--card:#101a30;--txt:#e2e8f0;--sub:#94a3b8;--acc:#3b82f6;--red:#ef4444;--gr1:#1d4ed8;--gr2:#7c3aed}}
.mrow.live{{background:linear-gradient(90deg,rgba(239,68,68,.14),transparent 60%);border-left:3px solid var(--red)}}
.mrow:hover{{background:var(--card2)}}
.mrow.live:hover{{background:linear-gradient(90deg,rgba(239,68,68,.2),var(--card2) 70%)}}
.sc{{font-weight:800;font-size:15px}}
.dot{{animation:pulse 1.2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.hero{{background:linear-gradient(135deg,var(--gr1),var(--gr2));border-radius:14px}}
.ev li{{border-left:3px solid var(--acc);padding-left:8px;margin-left:4px}}
.tabs{{display:flex;gap:6px;margin:6px 0;flex-wrap:wrap}}
.tab{{background:var(--row);color:var(--sub);border:1px solid var(--line2);border-radius:10px;padding:3px 10px;font-size:12px;cursor:pointer}}
.tab.on{{background:var(--acc);color:#fff;border-color:var(--acc)}}
.tpane table{{width:100%}}
#fbar button.on{{background:linear-gradient(135deg,var(--red),#f97316);color:#fff;border-color:transparent;box-shadow:0 2px 8px rgba(239,68,68,.35)}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{position:sticky;top:0;background:rgba(11,18,32,.94);backdrop-filter:blur(6px);padding:10px 14px;border-bottom:1px solid var(--line);z-index:5}}
header b{{font-size:18px}} header .sub{{color:var(--sub);font-size:12px;margin-left:8px}}
#daybar{{display:flex;gap:6px;overflow-x:auto;padding:8px 14px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:49px;z-index:4}}
.dbtn{{flex:0 0 auto;background:var(--row);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:5px 12px;font-size:12px;cursor:pointer}}
.dbtn.on{{background:var(--acc);color:var(--txt);border-color:var(--acc)}}
nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:var(--card);border-bottom:1px solid var(--line)}}
nav a{{color:var(--txt);text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:var(--row)}}
nav a.on{{background:var(--acc);color:var(--txt)}} nav a:hover{{background:#1e3a8a}}
main{{max-width:860px;margin:0 auto;padding:10px 12px}}
.lgh{{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);padding:12px 4px 4px;border-bottom:1px solid var(--line);position:sticky;top:96px;background:var(--bg);z-index:3}}
.ours{{color:#fbbf24}}
.mrow{{display:grid;grid-template-columns:18px 44px 1fr 52px 1fr 120px auto;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid var(--row);cursor:pointer;border-radius:10px;margin:2px 4px;transition:background .15s}}
.mrow:hover{{background:var(--row)}}
.mrow.live{{background:#2a1215;border-left:3px solid var(--red)}}
.tm{{color:var(--sub);font-size:12px;font-variant-numeric:tabular-nums}}
.h{{text-align:right;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.a{{text-align:left;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc{{text-align:center;font-weight:800;font-size:15px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:2px 0;font-variant-numeric:tabular-nums}}
.mrow.live .sc{{border-color:var(--red);color:#fecaca}}
.od{{font-size:10.5px;color:var(--sub);white-space:nowrap}}
.q3{{display:flex;gap:8px}}
.q3 span{{flex:1;background:var(--card3);border:1px solid var(--line2);border-radius:6px;padding:6px;text-align:center;font-size:11px;color:var(--sub)}}
.q3 b{{display:block;color:var(--txt);font-size:15px}}
.frm{{display:flex;align-items:center;gap:5px;margin:3px 0;font-size:12px}}
.frm i{{font-style:normal;width:16px;height:16px;border-radius:50%;font-size:9px;display:inline-flex;align-items:center;justify-content:center;color:#04101f;font-weight:700}}
.frm i.g{{background:#34d399}}.frm i.y{{background:#fbbf24}}.frm i.r{{background:#f87171}}
.bars{{display:flex;gap:3px;align-items:flex-end;height:30px;margin:2px 0 6px 26px}}
.bars .bar{{display:block;width:10px;border-radius:2px 2px 0 0}}
.bars2{{margin:4px 0 8px}}
.bst{{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:11px}}
.bl{{width:76px;color:var(--sub);text-align:right}}
.bt{{flex:1;display:flex;flex-direction:column;gap:2px}}
.bt i{{display:block;height:6px;border-radius:3px}}
.bh{{background:#3b82f6}} .ba{{background:#f59e0b}}
.bv{{width:64px;color:var(--txt);font-size:10.5px}}
.lins{{display:flex;gap:10px;flex-wrap:wrap}}
.lin{{flex:1;min-width:180px;background:var(--bg);border:1px solid var(--row);border-radius:8px;padding:6px 8px}}
.lin b{{font-size:12px}} .fmt{{color:var(--sub);font-size:11px;margin-left:6px}}
.lin ul{{list-style:none;margin:6px 0 0;padding:0;columns:1}}
.lin li{{font-size:11.5px;padding:1.5px 0;color:var(--txt)}}
.lin li i{{font-style:normal;color:var(--mut);display:inline-block;width:18px}}
.lin li em{{font-style:normal;color:var(--mut);font-size:10px}}
.perche{{color:#7dd3fc;font-weight:600;font-size:12.5px;background:rgba(56,189,248,.08);border-radius:6px;padding:6px 8px;margin:6px 0}}
.stt{{margin:10px 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--sub)}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}}
.b-live{{background:var(--red);color:var(--txt)}} .b-canc{{background:#3f3f46;color:#e4e4e7}} .mrow.canc{{opacity:.55}} .b-ft{{background:#334155;color:var(--txt)}} .b-pre{{background:#14532d;color:#86efac}}
.dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--txt);margin-right:4px;animation:blink 1s infinite}}
@keyframes blink{{50%{{opacity:.25}}}}
.det{{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:2px 0 8px;padding:8px 10px;font-size:13px;color:var(--sub)}}
.stt{{margin:4px 0;color:var(--acc);font-weight:700}}
#fbar{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:7px 14px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:96px;z-index:3}}
#fbar button{{background:var(--row);color:var(--sub);border:1px solid var(--line2);border-radius:14px;padding:4px 10px;font-size:12px;cursor:pointer}}
#fbar button.on{{background:var(--red);color:var(--txt);border-color:var(--red)}}
#fbar input{{background:var(--card3);border:1px solid var(--line2);color:var(--txt);border-radius:14px;padding:4px 10px;font-size:12px;width:150px}}
.lgh{{display:flex;justify-content:space-between;align-items:center}}
.lgc{{cursor:pointer}}
.chev{{font-size:10.5px;color:var(--mut);font-weight:400}}
.lgdet{{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:2px 8px 8px;padding:8px 10px;font-size:12px;color:var(--sub)}}
.star{{color:#334155;cursor:pointer;font-size:13px;text-align:center}}
.lg{{width:16px;height:16px;vertical-align:-3px;margin-right:5px;border-radius:50%}}
.lg.big{{width:34px;height:34px}}
.h a,.a{{display:flex;align-items:center;gap:2px}}
.hero{{background:linear-gradient(135deg,var(--line),var(--card3));border:1px solid #b91c1c;border-radius:12px;padding:12px 14px;margin:10px 0;cursor:pointer}}
.hero:hover{{border-color:#ef4444}}
.ht{{display:flex;justify-content:space-between;font-size:11px;color:var(--sub);margin-bottom:6px}}
.hm{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.htn{{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;flex:1}}
.htn:last-child{{justify-content:flex-end}}
.hsc{{font-size:22px;font-weight:800;color:var(--txt);background:var(--bg);border:1px solid var(--line2);border-radius:8px;padding:4px 12px}}
.hb{{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}}
.star.on{{color:#fbbf24}}
.flag{{font-size:10px;background:#3b2f0b;color:#fbbf24;border-radius:8px;padding:2px 5px;margin-left:4px;white-space:nowrap}}
.badge small{{color:var(--mut);font-size:9.5px}}
.b-pre{{line-height:1.1}}
.tm small{{color:var(--mut);font-size:9.5px}} table{{width:100%;border-collapse:collapse;margin-top:4px}} td{{padding:3px 6px;border-bottom:1px solid var(--row);text-align:center;font-size:12px}} td:first-child{{text-align:left;color:var(--txt)}}
ul.ev{{margin:4px 0;padding-left:18px}} ul.ev li{{margin-bottom:2px}}
:root{{--bg:#0b1220;--card:#111c33;--card2:#16233d;--card3:#0f1a30;--line:#1e293b;--line2:#243b5e;--row:#16233d;--txt:#e2e8f0;--sub:#94a3b8;--mut:#7b8794;--acc:#3b82f6;--red:#ef4444}}
[data-theme="light"]{{--bg:#f4f6f9;--card:var(--txt)fff;--card2:#eef2f7;--card3:#e6ebf1;--line:#d8dee6;--line2:#c3ccd6;--row:#e6ebf1;--txt:#182230;--sub:#4a5a70;--mut:#7b8794;--acc:#0284c7;--red:#b91c1c}}
html.big{{font-size:118%}}

[data-theme="light"] nav a.on{{color:#fff}}
[data-theme="light"] #inst{{color:#fff}}
[data-theme="light"] #fbar button.on{{color:#fff}}
[data-theme="light"] .b-live{{color:#fff}}
[data-theme="light"] .hero .hsc{{color:var(--txt)}}
[data-theme="light"] .flag{{color:#92400e}}
[data-theme="light"] .star{{color:#94a3b8}}
</style></head><body>
<header><a href="index.html" onclick="if(history.length>1){{history.back();return false;}}" style="color:#93c5fd;text-decoration:none;margin-right:8px" aria-label="torna indietro">‹ Indietro</a><button id="th" title="tema chiaro/scuro" style="background:none;border:1px solid #22345a;color:#8ea3c8;border-radius:8px;padding:2px 8px;cursor:pointer;margin-right:6px">☀️</button><button id="inst" style="display:none;background:#b91c1c;color:#fff;border:0;border-radius:8px;padding:3px 9px;cursor:pointer;font-size:12px">📲 Installa app</button><button id="fsz" aria-label="font grande" title="font grande" style="background:none;border:1px solid #22345a;color:#8ea3c8;border-radius:8px;padding:2px 8px;cursor:pointer;margin-left:6px">A+</button><b>🔴 Diretta {html.escape(a.date)}</b><span class="sub">{len(evs)} partite · {live_n} LIVE · dati da fonti pubbliche gratuite</span></header>
{daybar_html(today)}
<div id="fbar"><button data-f="all" class="on">Tutte</button><button data-f="live">🔴 LIVE</button><button data-f="ev">🚩 EV&gt;0</button><button data-f="fav">⭐ mie</button><input id="fq" type="search" placeholder="cerca squadra o lega…"><button data-m="lega" class="on">per lega</button><button data-m="orario">per orario</button></div>
<span id="sub" class="sub" style="display:block;padding:4px 14px"></span>
<nav>
<a href="index.html">Home</a><a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a><a href="altre-leghe.html">Altre leghe</a><a href="giocata_multi.html">Giocate</a><a href="schedina.html">🧾 Schedina</a><a href="bankroll.html">💰 Bankroll</a><a href="squadra.html">🔎 Squadra</a><a href="quote_giornata10.html">Quote</a><a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a><a class="on" href="diretta.html">🔴 Diretta</a>
</nav>
<main id="lg-list">
{rows_html(evs)}
</main>
<p style="text-align:center;color:#475569;font-size:12px;padding:14px">⚠️ Solo analisi, mai certezze · 18+ · ADM · autoesclusione.it · 800 558822</p>
</body>{LIVE_JS.replace('__DATE__', ds).replace('__SLUG2NAME__', json.dumps(SLUGS, ensure_ascii=False)).replace('__QMAP__', json.dumps(build_qmap(), ensure_ascii=False)).replace('__EVMAP__', json.dumps(build_evmap(), ensure_ascii=False)).replace('__H2H__', json.dumps(build_h2hmap(), ensure_ascii=False))}{footer("")}</html>"""
    SITE.mkdir(exist_ok=True)
    (SITE / "diretta.html").write_text(page, encoding="utf-8")
    print(f"🔴 site/diretta.html: {len(evs)} partite ({live_n} live) — {a.date}")


if __name__ == "__main__":
    main()
