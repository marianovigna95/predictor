#!/usr/bin/env python3
"""make_site.py — costruisce il sito statico in site/ dal progetto.

Uso: python3 src/make_site.py
Genera:
  site/index.html            — home: scoreboard pubblico + archivio report e quote per giornata
  site/metodo.html           — pagina metodo/trasparenza
  site/glossario.html        — glossario educativo + red flags dei siti di pronostici
  site/quote_giornataN.html  — tabella best-price quote (da data/odds_giornataN_bestprice.csv)
  site/report_giornataN.html — copia dei report esistenti
Tutto self-contained (CSS inline, link relativi). Footer 18+/ADM/autoesclusione su ogni pagina.
"""
import csv, glob, os, shutil
from datetime import date, datetime
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(ROOT, "data")

TABS = [("index.html", "⌂", "HOME", "home"),
        ("multi-lega.html", "🌍", "TOP 5", "top5"),
        ("giocata_multi.html", "🎯", "GIOCATE", "giocate"),
        ("ppa.html", "⚡", "PPA", "ppa"),
        ("surebets.html", "⚖️", "SUREBETS", "surebets"),
        ("archivio.html", "🗂", "ARCHIVIO", "archivio"),
        ("benchmark.html", "🏆", "BENCHMARK", "benchmark"),
        ("guida.html", "📖", "GUIDA", "guida")]


THEME_JS = """
<script>
(function(){var b=document.getElementById('themeBtn');if(!b)return;
function set(t){document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('theme',t);}catch(e){}b.textContent=(t==='light')?'🌙':'☀️';}
b.onclick=function(){var c=document.documentElement.getAttribute('data-theme')||'dark';set(c==='light'?'dark':'light');};
var t='dark';try{t=localStorage.getItem('theme')||'dark';}catch(e){}set(t);})();
</script>"""


def footer(active=""):
    """Tabbar fissa in basso (5 tab, attiva = pagina corrente) + footer legale."""
    bar = "".join(
        f'<a href="{h}" class="{"on" if key == active else ""}"><span class="ic">{ic}</span>{lb}</a>'
        for h, ic, lb, key in TABS)
    return f"""<div class="tabbar">{bar}</div>
<footer class="legal">
  ➕ <a href="altre-leghe.html">Altre leghe</a> · 📖 <a href="metodo.html">Metodo</a> · 📚 <a href="glossario.html">Glossario</a> · <a href="diretta.html">🔴 Diretta</a> · <a href="squadra.html">🔎 Squadra</a> · <a href="schedina.html">🧾 Schedina</a> · <a href="bankroll.html">💰 Bankroll</a> · <a href="ppa.html">⚡ PPA</a> · <a href="surebets.html">⚖️ Surebets</a> · 📅 <a href="verifica.html">Verifica</a> · 📊 <a href="report-weekend.html">Report weekend</a><br>
  ⚠️ <b>18+</b> — Il gioco d'azzardo è vietato ai minori di 18 anni e può causare dipendenza patologica.
  Gioca responsabilmente e solo presso operatori con <b>licenza ADM</b>.
  Autoesclusione: <b>autoesclusione.it</b> · Numero Verde 800 558822.<br>
  Questo sito pubblica <b>analisi statistiche a scopo informativo</b>: ogni pronostico è una stima con incertezza,
  mai una certezza o una garanzia. I risultati passati non garantiscono risultati futuri.
</footer>""" + THEME_JS


CSS = """
:root { --bg:#0b0f14; --card:#12171e; --line:#242c37; --txt:#e8ecf1; --mut:#8b96a5; --acc:#38bdf8;
  --btnbg:#171e27; --rowline:#1b222b; --track:#1c232c; --codebg:#1a212b; --termbg:#0a0e13; --scr:#2a333f; --tabon:#141b24; }
html[data-theme="light"] { --bg:#f4f6f9; --card:#ffffff; --line:#d8dee6; --txt:#182230; --mut:#5c6878; --acc:#0284c7;
  --btnbg:#edf1f6; --rowline:#e6ebf1; --track:#e6ebf1; --codebg:#edf1f6; --termbg:#edf1f6; --scr:#c3ccd6; --tabon:#e3f2fd; }
* { box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif; background:var(--bg);
  color:var(--txt); margin:0; padding:14px 14px 96px; line-height:1.45; font-size:14px; }
::selection { background:rgba(56,189,248,.28); }
::-webkit-scrollbar { width:10px; height:10px; } ::-webkit-scrollbar-thumb { background:var(--scr); border-radius:5px; }
::-webkit-scrollbar-track { background:transparent; }
.wrap { max-width:980px; margin:auto; }
h1 { font-size:21px; margin:0 0 6px; font-weight:700; }
h1 .g, .g { color:var(--acc); }
h2 { font-size:15px; margin:0 0 10px; font-weight:700; }
h2.day { border-bottom:1px solid var(--line); padding-bottom:6px; }
p { margin:6px 0; }
a { color:var(--acc); text-decoration:none; } a:hover { text-decoration:underline; }
code { background:var(--codebg); border:1px solid var(--line); border-radius:4px; padding:1px 5px; font-size:12px; }
.sub { color:var(--mut); font-size:12.5px; }
.mut { color:var(--mut); }

/* topbar + tabbar piatte */
.topbar { position:sticky; top:0; z-index:50; background:var(--bg); border-bottom:1px solid var(--line);
  margin:-14px -14px 14px; padding:8px 14px; display:flex; align-items:center; gap:10px; }
.brand { font-weight:700; font-size:15px; color:var(--txt); } .brand:hover { text-decoration:none; }
.backbtn { color:var(--mut); font-size:13px; } .backbtn:hover { color:var(--txt); text-decoration:none; }
.tabbar { position:fixed; bottom:0; left:0; right:0; z-index:50; background:var(--bg);
  border-top:1px solid var(--line); display:flex; overflow-x:auto; }
.tabbar a { flex:1; text-align:center; padding:10px 4px; color:var(--mut); font-size:12px; font-weight:600;
  border-right:1px solid var(--line); } .tabbar a:last-child { border-right:none; }
.tabbar a.on { color:var(--acc); background:var(--tabon); box-shadow:inset 0 2px 0 var(--acc); }
.tabbar a:hover { text-decoration:none; color:var(--txt); } .tabbar a.on:hover { color:var(--acc); }

/* card piatte e compatte */
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:12px; }
.quicklinks { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:4px 0 14px; }
.ql { display:flex; flex-direction:column; align-items:center; gap:2px; background:var(--card); border:1px solid var(--line);
  border-radius:12px; padding:12px 6px; text-decoration:none; color:var(--txt); }
.ql .ic { font-size:20px; } .ql b { font-size:12.5px; } .ql small { color:var(--mut); font-size:10px; }
.hero { padding:14px 0 10px; } .hero h1 { font-size:24px; } .hero p { color:var(--mut); max-width:640px; }
.cta { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.btn { display:inline-block; border:1px solid var(--line); background:var(--btnbg); color:var(--txt); border-radius:8px;
  padding:7px 13px; font-size:13px; font-weight:600; } .btn:hover { border-color:var(--acc); color:var(--acc); text-decoration:none; }
.btn.on { border-color:var(--acc); color:var(--acc); background:var(--tabon); }
.btn.ghost { background:transparent; color:var(--mut); }

/* tabelle dense */
.tablewrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th { text-align:left; color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.4px;
  padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
td { padding:6px 8px; border-bottom:1px solid var(--rowline); vertical-align:top; }
tr:last-child td { border-bottom:none; }
tr.mrow td { color:var(--mut); font-size:12px; padding:2px 8px 10px; background:transparent; }
.tb { font-weight:600; } .tb-r { text-align:right; }

/* pill piatte */
.pill { display:inline-block; border-radius:999px; padding:1px 9px; font-size:11px; font-weight:700;
  border:1px solid var(--line); background:var(--btnbg); color:var(--txt); white-space:nowrap; }
.pill.ev-pos { background:rgba(34,197,94,.12); color:#4ade80; border-color:rgba(34,197,94,.35); }
.pill.ev-neg { background:rgba(248,113,113,.10); color:#f87171; border-color:rgba(248,113,113,.35); }
.t-singola { background:rgba(251,191,36,.12); color:#fbbf24; border-color:rgba(251,191,36,.4); }
.t-raddoppio { background:rgba(56,189,248,.12); color:#38bdf8; border-color:rgba(56,189,248,.4); }
.t-nessuna { background:var(--btnbg); color:var(--mut); }
.chip { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:1px 9px;
  font-size:11px; color:var(--mut); background:var(--btnbg); }

/* barra confidenza piatta */
.cbar { height:5px; background:var(--track); border-radius:3px; overflow:hidden; margin-top:6px; }
.cbar i { display:block; height:100%; background:var(--acc); border-radius:3px; }

/* match card compatte */
.mc-grid { display:grid; grid-template-columns:1fr; gap:10px; } /* 🆕 06/11: una card per riga, niente affiancate */
.mc { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.mc-h { font-size:11px; color:var(--mut); margin-bottom:4px; display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; }
.mc-row { display:flex; justify-content:space-between; align-items:center; gap:8px; font-size:13px; flex-wrap:wrap; } .mc-row > * { min-width:0; }
.mc-row b { font-weight:600; }
.mc-mot { color:var(--mut); font-size:11.5px; margin-top:6px; }
details { margin-top:4px; font-size:11.5px; color:var(--mut); }

/* stats, verdetto, avvisi, footer */
.grid { display:flex; flex-wrap:wrap; gap:10px; }
.stat { border:1px solid var(--line); border-radius:8px; padding:8px 12px; background:var(--card); min-width:110px; }
.stl { font-size:10.5px; color:var(--mut); text-transform:uppercase; letter-spacing:.4px; }
.stv { font-size:17px; font-weight:700; }
.ms { font-size:12px; color:var(--mut); }
.verdetto { font-weight:600; font-size:12.5px; }
.v-go  { background:rgba(34,197,94,.10);  color:#4ade80; border:1px solid rgba(34,197,94,.35);  border-radius:8px; padding:6px 10px; margin:6px 0 0; }
.v-ok  { background:rgba(163,230,53,.09);  color:#bef264; border:1px solid rgba(163,230,53,.35); border-radius:8px; padding:6px 10px; margin:6px 0 0; }
.v-bor { background:rgba(251,191,36,.10);  color:#fbbf24; border:1px solid rgba(251,191,36,.4);  border-radius:8px; padding:6px 10px; margin:6px 0 0; }
.v-no  { background:rgba(248,113,113,.09); color:#f87171; border:1px solid rgba(248,113,113,.35);border-radius:8px; padding:6px 10px; margin:6px 0 0; }
.warn { border:1px solid rgba(251,191,36,.4); background:rgba(251,191,36,.08); color:#fbbf24;
  border-radius:8px; padding:8px 12px; font-size:12.5px; margin:10px 0; }
.okbox { border:1px solid rgba(34,197,94,.35); background:rgba(34,197,94,.08); color:#4ade80;
  border-radius:8px; padding:8px 12px; font-size:12.5px; margin:10px 0; }
.legal { font-size:11.5px; color:var(--mut); }
.term { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11.5px; background:var(--termbg);
  border:1px solid var(--line); border-radius:8px; padding:8px 10px; white-space:pre-wrap; }
.ic { font-style:normal; }
.l, .n { font-size:12.5px; }

@media (max-width:720px) {
  body { padding:10px 10px 92px; font-size:13.5px; }
  .topbar { margin:-10px -10px 10px; padding:7px 10px; }
  .card { padding:11px 12px; }
  .hero h1 { font-size:20px; }
  .tabbar a { font-size:11px; padding:9px 2px; }
  .quicklinks { grid-template-columns:repeat(2,1fr); }
  .tabbar a { flex:0 0 auto; padding:9px 12px; }
  /* 🛠 08/11 mobile compatto: tabelle -> card impilate, niente scroll orizzontale */
  .tablewrap { overflow:visible !important; }
  table { display:block; font-size:12.5px; }
  thead, table tr th { display:none !important; }
  table tr { display:block; border:1px solid var(--line); border-radius:10px; margin:0 0 10px; padding:6px 9px; background:var(--card2, var(--card)); }
  table td { display:flex; justify-content:space-between; align-items:baseline; gap:10px; border:0 !important; padding:3px 2px !important; font-size:12.5px; text-align:right; }
  table td::before { content:attr(data-label); color:var(--mut); font-size:10px; text-transform:uppercase; letter-spacing:.04em; text-align:left; }
  table td[colspan] { display:block; text-align:left; }
  table td[colspan]::before { content:none; }
  .mrow td { font-size:11.5px; line-height:1.45; }
}
"""


def st(label, valore):
    """Statistica impilata in colonna: etichetta sopra (piccola), valore sotto (grande)."""
    return f'<span class="stl">{label}</span><span class="stv">{valore}</span>'

def wrap_tables(html):
    return html.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")


def topbar(back=True):
    b = ''
    if back:
        b = '<a class="backbtn" href="index.html" onclick="if(history.length>1){history.back();return false;}else{location.href=\'index.html\';return false;}">← Indietro</a>'
    return ('<header class="topbar"><div class="wrap tb"><a class="brand" href="index.html">⚽ <span>Predictor</span></a>'
            '<div class="tb-r">' + b + '<button id="themeBtn" class="btn ghost" style="cursor:pointer" title="Cambia tema">☀️</button>'
            '<a class="btn ghost" href="index.html">⌂ Home</a></div></div></header>')

NAV = topbar(True)
NAV_HOME = topbar(False)

TOP5 = ["Serie A", "Premier League", "LaLiga", "Bundesliga", "Ligue 1"]
CUPS = ["Champions League", "Europa League", "Conference League"]
EXTRA = ["Serie B", "Championship", "Eredivisie", "Primeira Liga", "Süper Lig", "Bundesliga 2", "LaLiga 2", "Ligue 2"]  # 🆕 04/11
INTL = ["Nations League", "WC Qual. UEFA", "Friendlies"]  # 🆕 10/11 nazionali (sosta FIFA)

def slug(l):
    return l.lower().replace(" ", "-")


def gj_num(path):
    tail = os.path.basename(path).split("giornata")[1]
    return "".join(ch for ch in tail if ch.isdigit())


def scoreboard_rows():
    p = os.path.join(DATA, "scoreboard.csv")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return list(csv.DictReader(f))


def perf_chart(rows):
    """📈 SVG cumulativo: acc% modello e RPS modello per giornata (da scoreboard.csv)."""
    pts_acc, pts_rps = [], []
    for r in rows:
        try:
            if r.get("acc%"): pts_acc.append(float(r["acc%"]))
            if r.get("RPS modello"): pts_rps.append(float(r["RPS modello"]))
        except Exception:
            pass
    def svg(pts, color, lab, ref50=False):
        if not pts:
            return ""
        w, h = 560, 110
        mn, mx = min(pts + ([50] if ref50 else [])), max(pts + ([50] if ref50 else []))
        rng = (mx - mn) or 1
        step = w / (len(pts) - 1) if len(pts) > 1 else w
        d = " ".join(f"{'M' if i==0 else 'L'}{(i*step):.1f},{(h-8-((v-mn)/rng)*(h-16)):.1f}" for i, v in enumerate(pts))
        line50 = f'<line x1="0" y1="{h-8-((50-mn)/rng)*(h-16):.1f}" x2="{w}" y2="{h-8-((50-mn)/rng)*(h-16):.1f}" stroke="#334155" stroke-dasharray="3 3"/><text x="4" y="12" fill="#64748b" font-size="10">50%</text>' if ref50 else ""
        return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;max-width:560px" role="img" aria-label="{lab}">{line50}'
                f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/></svg><p class="sub" style="margin:2px 0 10px">{lab}</p>')
    return svg(pts_acc, "#34d399", "📈 Accuratezza modello per giornata (%) — linea tratteggiata = 50%", True) + svg(pts_rps, "#38bdf8", "📉 RPS modello per giornata (più basso = meglio)")


def bestprice_files():
    return sorted(glob.glob(os.path.join(DATA, "odds_giornata*_bestprice.csv")), key=gj_num)


def giocata_oggi_html(today_iso):
    """Card GIOCATE DI OGGI in cima alla home: Singola + Raddoppio del giorno corrente."""
    gj_p = os.path.join(DATA, "giocata_multi.csv")
    if not os.path.exists(gj_p):
        return ""
    with open(gj_p) as f:
        grows = list(csv.DictReader(f))
    rows = [r for r in grows if (r.get("data") or "") == today_iso]
    if not rows:
        # oggi non c'è più nel file (finestra già slittata): mostra la prima giornata disponibile
        first = min((r.get("data") or "") for r in grows)
        rows = [r for r in grows if (r.get("data") or "") == first]
        today_iso = first
    if not rows:
        return ""
    label = today_iso[8:] + "/" + today_iso[5:7] + "/" + today_iso[:4]
    tr = ""
    for r in rows:
        mot = (r.get("motivo") or "—").replace("<", "&lt;")
        evv = str(r.get("EV%") or "")
        try:
            evc = "ev-pos" if float(evv) > 0 else "ev-neg"
        except ValueError:
            evc = "mut"
        vd = (r.get("verdetto") or "").replace("<", "&lt;")
        vc = "v-no" if vd.startswith("⛔") else ("v-bor" if vd.startswith("⚠️") else ("v-go" if vd.startswith("✅") else "v-ok"))
        tr += (f"<tr><td data-label='Tipo'><span class='pill t-{r['tipo'].lower()}'>{r['tipo']}</span></td>"
               f"<td data-label='Lega'>{r['lega']}</td><td data-label='Partita'>{r['partita']}</td>"
               f"<td data-label='Mercato'>{r.get('mercato')}</td><td data-label='Esito'><b>{r.get('esito')}</b></td>"
               f"<td data-label='p modello'>{r.get('p_modello%')}%</td><td data-label='Quota'>{r.get('quota_best')}</td>"
               f"<td data-label='EV'><span class='pill {evc}'>{r.get('EV%')}%</span></td></tr>"
               f"<tr class='mrow'><td colspan='8' data-label='Motivo'>{mot}</td></tr>"
               f"<tr class='mrow'><td colspan='8'><div class='verdetto {vc}'>🧑‍⚖️ Verdetto: {vd}</div></td></tr>")
    return (f"<div class='card' style='border-color:#0ea5e9'><h2>🎯 Giocate — {label}</h2>"
            f"<div class='tablewrap'><table><tr><th>Tipo</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Esito</th><th>p modello</th><th>Quota best</th><th>EV</th></tr>{tr}</table></div>"
            f"<p class='sub' style='margin:8px 0 0'>Regola EV&gt;0-only: se nessuna giocata ha EV positiva esce la riga ⛔ NESSUNA (stake 0). "
            f"<a href='giocata_multi.html'>Tutte le giocate della finestra →</a></p></div>")


def leghe_buttons_html(frows):
    """Bottoni campionato in home: ogni lega punta alla sua sezione (ancora) nella pagina di riferimento."""
    groups = [("🌍 Top 5", "multi-lega.html", TOP5),
              ("🏆 Coppe europee", "coppe.html", CUPS),
              ("➕ Altre leghe", "altre-leghe.html", EXTRA)]
    parts = []
    for label, pg, leagues in groups:
        btns = " ".join(f'<a class="btn" href="{pg}#{slug(l)}">{l}</a>'
                        for l in leagues if any(r["lega"] == l for r in frows))
        if btns:
            parts.append(f"<p style='margin:6px 0'><b>{label}:</b> {btns}</p>")
    if not parts:
        return ""
    return ("<div class='card'><h2>🌍 Scegli il campionato</h2>"
            "<p class='sub'>Clicca sul campionato per sfogliare pronostici, valutazioni e motivi di quella lega:</p>"
            + "".join(parts) + "</div>")


def pronostici_finestra_html(frows, today_dm):
    """Tabella pronostici dell'INTERA finestra con filtri JS per giorno e gruppo di leghe."""
    if not frows:
        return ""
    def cat(l):
        if l in TOP5: return "top5"
        if l in CUPS: return "coppe"
        if l in INTL: return "intl"
        return "extra"
    days = sorted({(r.get("orario") or "").split(" ")[0] for r in frows if (r.get("orario") or "").strip()},
                  key=lambda d: (d[3:5], d[0:2]))
    dbtns = "".join(f"<button class='btn' data-day='{d}' onclick='setDay(this)'>{d}</button>" for d in days if d != today_dm)
    daybar = (f"<p class='sub' id='daybtns' style='margin:4px 0'><b>Giorno:</b> "
              f"<button class='btn on' data-day='{today_dm}' onclick='setDay(this)'>{today_dm} (oggi)</button>{dbtns}"
              f"<button class='btn' data-day='all' onclick='setDay(this)'>tutti</button></p>")
    catbar = ("<p class='sub' id='catbtns' style='margin:4px 0'><b>Gruppo:</b> "
              "<button class='btn on' data-cat='all' onclick='setCat(this)'>Tutti</button>"
              "<button class='btn' data-cat='top5' onclick='setCat(this)'>🌍 Top 5</button>"
              "<button class='btn' data-cat='coppe' onclick='setCat(this)'>🏆 Coppe</button>"
              "<button class='btn' data-cat='intl' onclick='setCat(this)'>🚩 Nazionali</button>"
              "<button class='btn' data-cat='extra' onclick='setCat(this)'>➕ Altre leghe</button></p>")
    tr = ""
    for r in sorted(frows, key=lambda x: x.get("orario") or ""):
        day = (r.get("orario") or "").split(" ")[0]
        c = cat(r.get("lega") or "")
        try:
            p = float(r.get("conf%") or 0) / 100.0
            q = float(r.get("quota_best"))
            ev = (p * (q - 1) - (1 - p)) * 100
            if ev > 50:  # 🚨 quota anomala (dato sporco): non mostrare un EV irrealistico
                evc, evs = "ev-neg", "⚠️ anomala"
            else:
                evc = "ev-pos" if ev > 0 else "ev-neg"
                evs = f"{ev:+.1f}%"
        except (ValueError, TypeError):
            evc, evs = "mut", "—"
        mot = (r.get("motivo_verbale") or "").replace("<", "&lt;")
        tr += (f"<tr data-day='{day}' data-cat='{c}'><td data-label='Ora' class='tb-r'>{r.get('orario','')}</td>"
               f"<td data-label='Lega' class='sub'>{r.get('lega')}</td>"
               f"<td data-label='Partita'><b>{r.get('partita')}</b></td>"
               f"<td data-label='Pron.'><span class='pill'>{r.get('pronostico')}</span> {r.get('conf%')}%</td>"
               f"<td data-label='O2.5'>{r.get('Over2.5%')}%</td><td data-label='GG'>{r.get('BTTS%')}%</td>"
               f"<td data-label='Quota best'>{r.get('quota_best')}</td>"
               f"<td data-label='EV'><span class='pill {evc}'>{evs}</span></td></tr>"
               f"<tr class='mrow' data-day='{day}' data-cat='{c}'><td colspan='8'><details><summary>motivo</summary>{mot}</details></td></tr>")
    n_today = sum(1 for r in frows if (r.get("orario") or "").split(" ")[0] == today_dm)
    js = ("<script>var curDay='" + today_dm + "',curCat='all';"
          "function setDay(b){curDay=b.dataset.day;document.querySelectorAll('#daybtns .btn').forEach(function(x){x.classList.toggle('on',x===b);});applyF();}"
          "function setCat(b){curCat=b.dataset.cat;document.querySelectorAll('#catbtns .btn').forEach(function(x){x.classList.toggle('on',x===b);});applyF();}"
          "function applyF(){document.querySelectorAll('#ptable tr[data-day]').forEach(function(r){"
          "r.style.display=((curDay==='all'||r.dataset.day===curDay)&&(curCat==='all'||r.dataset.cat===curCat))?'':'none';});}"
          "</script>")
    from datetime import datetime as _dt, timedelta as _td  # 🆕 10/11 etichetta finestra mobile oggi→+7
    _d0 = _dt.strptime(today_dm + "/2026", "%d/%m/%Y")
    _w0, _w1 = _d0.strftime("%d/%m"), (_d0 + _td(days=7)).strftime("%d/%m")
    return (f"<div class='card'><h2>📋 Pronostici finestra mobile ({_w0}–{_w1}/2026, {len(frows)} partite — {n_today} oggi {today_dm})</h2>"
            f"{daybar}{catbar}"
            f"<table id='ptable'><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Pron.</th><th>O2.5</th><th>GG</th><th>Quota</th><th>EV</th></tr>{tr}</table>"
            f"<p class='sub' style='margin:8px 0 0'>EV calcolato sul pronostico 1X2 (conf% × quota best). Dettaglio per lega: "
            f"<a href='multi-lega.html'>Top 5</a> · <a href='coppe.html'>Coppe</a> · <a href='altre-leghe.html'>Altre leghe</a>. Stime con incertezza, mai certezze.</p>{js}</div>")


def build_index():
    """HOME v4 cruscotto: 1) giocate di oggi  2) bottoni campionati  3) tutti i pronostici di oggi + scoreboard."""
    today = date.today().isoformat()
    today_dm = today[8:] + "/" + today[5:7]
    rows = scoreboard_rows()
    tot_m = tot_c = 0
    rps_list = []
    for r in rows:
        try:
            tot_m += int(r["partite"]); tot_c += int(r["modello corretti"])
            if r.get("RPS modello"):
                rps_list.append(float(r["RPS modello"]))
        except Exception:
            pass
    acc = 100.0 * tot_c / tot_m if tot_m else 0
    rps_avg = sum(rps_list) / len(rps_list) if rps_list else 0
    fc_p = os.path.join(DATA, "forecast_multi.csv")
    frows = []
    if os.path.exists(fc_p):
        with open(fc_p) as f:
            frows = list(csv.DictReader(f))
    riepilogo = (f"Scoreboard pubblico: {tot_m} partite analizzate, accuratezza 1X2 modello {acc:.1f}%, "
                 f"RPS medio {rps_avg:.4f} — <a href='archivio.html'>archivio completo →</a>")
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Predictor — giocate di oggi e pronostici</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV_HOME}
<div class="quicklinks">
  <a class="ql" href="ppa.html"><span class="ic">⚡</span><b>PPA</b><small>Pronostici % alta</small></a>
  <a class="ql" href="giocata_multi.html"><span class="ic">🎯</span><b>Giocate EV</b><small>Singola+Raddoppio</small></a>
  <a class="ql" href="diretta.html"><span class="ic">🔴</span><b>Diretta</b><small>Live oggi</small></a>
  <a class="ql" href="surebets.html"><span class="ic">⚖️</span><b>Surebets</b><small>Best-price</small></a>
</div>
<div class="hero">
  <h1>⚽ Predictor <span class="g">— oggi {today_dm}/2026</span></h1>
  <p class="sub">Analisi statistiche calcio 2026/27 (16 leghe: Top 5 + 8 extra + coppe UEFA). Ogni pronostico è una <b>stima con incertezza</b>, mai una certezza.</p>
  <p class="sub">{riepilogo}</p>
  <p style="margin-top:10px"><a href="diretta.html" style="display:inline-block;background:#dc2626;color:#fff;font-weight:800;font-size:17px;padding:12px 26px;border-radius:12px;text-decoration:none;box-shadow:0 6px 18px rgba(220,38,38,.5)">🔴 VAI ALLA DIRETTA (score live)</a></p>
  <div class="warn" style="margin-top:10px">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente ·
  Autoesclusione <b>autoesclusione.it</b> · 800 558822 · Sito solo informativo: non raccogliamo scommesse né gestiamo denaro.</div>
</div>
{giocata_oggi_html(today)}
{leghe_buttons_html(frows)}
{pronostici_finestra_html(frows, today_dm)}
{footer("home")}
</div></body></html>"""
    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write(wrap_tables(html))


def build_guida():
    """📖 GUIDA/FAQ: onboarding — cosa sono EV/RPS/CLV/Kelly, come leggere le pagine, regole e limiti."""
    body = """<div class="card">
  <h2>👋 Benvenuto — come si usa questo sito</h2>
  <p class="sub">Questo sito pubblica <b>analisi statistiche</b> su partite di calcio: nulla è una certezza, nulla è un consiglio di gioco.
  Si gioca (se si decide di farlo) <b>solo su bookmaker ADM autorizzati, 18+</b>. 18+ · ADM · autoesclusione.it · 800 558822.</p>
</div>
<div class="card">
  <h2>🧭 Le pagine</h2>
  <table>
  <tr><th>Pagina</th><th>Cosa trovi</th><th>Quando usarla</th></tr>
  <tr><td>⌂ <b>Home</b></td><td>finestra mobile 7 giorni: partite, quote best-price, pronostici EV&gt;0</td><td>panoramica del giorno</td></tr>
  <tr><td>🔴 <b>Diretta</b></td><td>live ogni 30s: score, quote live, xG, timeline, formazioni, proiezione 1X2 live ed EV live (min≥30)</td><td>durante le partite</td></tr>
  <tr><td>🎯 <b>Giocate</b></td><td>per ogni giorno: Singola + Raddoppio (quota≈2.00) solo se EV&gt;0, con p, quota, EV%, stake ¼ Kelly</td><td>la schedina del giorno</td></tr>
  <tr><td>⚡ <b>PPA</b></td><td>pronostici con p modello ≥ 60%, per giorno (clicca le date in cima), con esito ✅/❌ quando verificati</td><td>idee ad alta probabilità</td></tr>
  <tr><td>🧾 <b>Schedina</b></td><td>la schedina di oggi (stampabile/PDF)</td><td>riepilogo rapido</td></tr>
  <tr><td>💰 <b>Bankroll</b></td><td>traccia le tue puntate nel browser: ROI, winrate, drawdown, equity curve, confronto flat-stake vs ¼ Kelly, export CSV</td><td>se tieni il conto</td></tr>
  <tr><td>🗂 <b>Archivio</b></td><td>scoreboard pubblico per giornata (acc%, RPS modello vs mercato), verifica giocate con CLV, export JSON/CSV</td><td>trasparenza: vinti E persi</td></tr>
  <tr><td>🏆 <b>Benchmark</b></td><td>RPS del modello vs mercato per lega (walk-forward), sempre aggiornato</td><td>quanto vale davvero il modello</td></tr>
  <tr><td>🔎 <b>Squadra</b></td><td>cerca una squadra: calendario 8 giorni, EV, dettaglio</td><td>follow di una squadra</td></tr>
  <tr><td>📖 <b>Metodo / Glossario</b></td><td>regole, formule (EV, Kelly, CLV, RPS), definizioni</td><td>capire il metodo</td></tr>
  </table>
</div>
<div class="card">
  <h2>🧮 Le 4 cose da sapere</h2>
  <table>
  <tr><th>Concetto</th><th>Significato</th></tr>
  <tr><td><b>EV (valore atteso)</b></td><td>EV = p·quota − 1. Se &gt; 0 il prezzo "vale" la nostra probabilità. Si pubblica/gioca solo EV&gt;0; stake solo se EV&gt;+2%</td></tr>
  <tr><td><b>RPS</b></td><td>metrica di errore delle probabilità (0=perfetto). benchmark.html confronta modello vs mercato</td></tr>
  <tr><td><b>CLV</b></td><td>quota giocata vs quota di chiusura del mercato: CLV&gt;0 = battuto il mercato a fine giornata</td></tr>
  <tr><td><b>¼ Kelly</b></td><td>stake =¼ della Kelly frazionaria, con margine di incertezza su p: mai puntare più di quanto si può perdere</td></tr>
  </table>
</div>
<div class="card">
  <h2>⚠️ Regole e limiti (leggere prima)</h2>
  <p class="sub">✅ max <b>1 SINGOLA + 1 RADDOPPIO al giorno</b> · ✅ stake solo EV&gt;+2% · ✅ pubblichiamo vinti e persi ·
  ❌ niente multiple/schedine lunghe · ❌ niente "sicuri" · ❌ niente siti tips/affiliate (🚩) · ❌ niente book non-ADM.
  Tetto realistico ~53-56% acc. 1X2: la varianza è alta, anche il modello migliore perde journées intere.
  Se il gioco rischia di sfuggire: <b>autoesclusione.it</b> · <b>800 558822</b> (gratis).</p>
</div>"""
    html = page("Guida", '📖 <span class="g">Guida</span>', "Come si usa il sito: pagine, EV/RPS/CLV/Kelly, regole e limiti. Onboarding in 2 minuti.", body, active="guida")
    with open(os.path.join(SITE, "guida.html"), "w", encoding="utf-8") as f:
        f.write(wrap_tables(html))


def build_benchmark():
    """🏆 BENCHMARK: RPS modello vs mercato per lega (walk-forward g6-g10, da data/validation_multi.csv)."""
    import json
    vf = os.path.join(DATA, "validation_multi.csv")
    rows = ""
    if os.path.exists(vf):
        with open(vf) as f:
            rd = list(csv.DictReader(f))
        for r in rd:
            try:
                rm = float(r.get("RPS_modello") or 0); rk = float(r.get("RPS_mercato") or 0)
                edge = rk - rm
                cls = "ev-pos" if edge > 0 else ("ev-neg" if edge < 0 else "sub")
                rows += (f"<tr><td data-label='Lega'><b>{r['lega']}</b></td><td data-label='Partite'>{r['partite']}</td>"
                         f"<td data-label='Acc modello'>{r['acc_modello']}%</td><td data-label='Acc mercato'>{r['acc_mercato']}%</td>"
                         f"<td data-label='RPS modello'>{rm:.3f}</td><td data-label='RPS mercato'>{rk:.3f}</td>"
                         f"<td data-label='Edge' class='{cls}'>{edge:+.3f}</td></tr>")
            except Exception:
                pass
    if not rows:
        rows = "<tr><td colspan=7>Validazione non ancora eseguita (data/validation_multi.csv mancante).</td></tr>"
    # export giocate (JSON+CSV) — idea presa da gambeta/scoregpt: storico pubblico scaricabile
    gj = []
    gjf = os.path.join(DATA, "giocata_multi.csv")
    if os.path.exists(gjf):
        with open(gjf) as f:
            gj = list(csv.DictReader(f))
    ver = []
    for vfile in sorted(glob.glob(os.path.join(DATA, "verifica_*.csv"))):
        with open(vfile) as f:
            for r in csv.DictReader(f):
                ver.append(r)
    export = {"giocate": gj, "verifiche": ver,
              "nota": "Storico pubblico del predictor: giocate (EV>0) e verifiche con esito reale + CLV. Dati aperti, verificabili esternamente. Analisi-only, 18+, solo ADM, autoesclusione.it, 800 558822."}
    with open(os.path.join(SITE, "archivio_giocate.json"), "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=1)
    with open(os.path.join(SITE, "archivio_giocate.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sezione", "data", "tipo", "lega", "partita", "mercato", "esito", "p_modello%", "quota_best", "EV%", "stake%", "risultato", "vinto"])
        for r in gj:
            w.writerow(["giocata", r.get("data",""), r.get("tipo",""), r.get("lega",""), r.get("partita",""),
                        r.get("mercato",""), r.get("esito",""), r.get("p_modello%",""), r.get("quota_best",""),
                        r.get("EV%",""), r.get("stake%",""), "", ""])
        for r in ver:
            w.writerow(["verifica", r.get("data",""), r.get("tipo",""), r.get("lega",""), r.get("partita",""),
                        r.get("mercato",""), r.get("esito",""), r.get("p_modello%",""), r.get("quota_best",""),
                        "", "", r.get("risultato",""), r.get("vinto","")])
    # 🆕 13/11 ROI reale della schedina storica (da verifica_*.csv): Singola/Raddoppio archiviati, flat 1u
    roi_rows = ""
    agg = {}
    for r in ver:
        t = r.get("tipo", "")
        if t not in ("SINGOLA", "RADDOPPIO"):
            continue
        q = float(r.get("quota_best") or 0); v = str(r.get("vinto") or "")
        a = agg.setdefault(t, {"n": 0, "win": 0, "roi": 0.0})
        if not q or q <= 1:
            continue
        a["n"] += 1
        win = "✅" in v
        a["win"] += int(win)
        a["roi"] += (q - 1) if win else -1.0
    if agg:
        for t, a in agg.items():
            if a["n"]:
                roi_rows += (f"<tr><td data-label='Tipo'><b>{t}</b></td><td data-label='Giocate'>{a['n']}</td>"
                             f"<td data-label='Win%'>{100*a['win']/a['n']:.1f}%</td>"
                             f"<td data-label='ROI (flat 1u)' class='{'ev-pos' if a['roi']>=0 else 'ev-neg'}>{100*a['roi']/a['n']:+.1f}%</td></tr>")
    roi_card = ('<div class="card"><h2>🧾 ROI reale della schedina (archiviata)</h2>'
                '<p class="sub">Singola+Raddoppio dei giorni passati, verificati con esito reale, a flat 1 unità: win% e ROI. Campione piccolo → tendance, non garanties.</p>'
                f"<table><tr><th>Tipo</th><th>Giocate</th><th>Win%</th><th>ROI (flat 1u)</th></tr>{roi_rows or '<tr><td colspan=4>ancora nessuna giocata verificata</td></tr>'}</table></div>") if roi_rows else ""
    body = f"""<div class="card">
  <h2>🏆 Benchmark: modello vs mercato (walk-forward)</h2>
  <p class="sub">Validazione g6-g10 2026/27: ogni partita prevista usando SOLO dati precedenti (no leakage).
  <b>RPS</b> (0 = perfetto, più basso = meglio): edge positivo = il nostro modello ha RPS più basso del mercato (quote di chiusura).
  Il mercato resta il benchmark reale; l'obiettivo onesto non è "batterlo sempre" ma trovare i pochi casi con EV&gt;0 su ADM.</p>
  <table><tr><th>Lega</th><th>Partite</th><th>Acc modello</th><th>Acc mercato</th><th>RPS modello</th><th>RPS mercato</th><th>Edge (mkt−modello)</th></tr>{rows}</table>
  <p class="sub">🧠 Stacker v7 (LOO su 535 match g6-g38): RPS 1X2 <b>0.1918</b> vs mercato <b>0.1963</b> — sotto il mercato in RPS grezzo,
  oltre ai segnali extra (forma-xG, H2H, arbitro, meteo, assenze) che la media mercato non pesa.</p>
</div>
{roi_card}
<div class="card">
  <h2>📂 Storico pubblico scaricabile (dati aperti)</h2>
  <p class="sub">Come il principio di trasparenza di gambeta/scoregpt: tutto lo storico delle nostre giocate e verifiche è esportabile e verificabile esternamente.</p>
  <p><a class="btn" href="archivio_giocate.json" download>⬇ archivio_giocate.json</a>
     <a class="btn" href="archivio_giocate.csv" download>⬇ archivio_giocate.csv</a></p>
  <p class="sub">Contenuto: giocate (Singola/Raddoppio con p, quota, EV%, stake%) + verifiche con esito reale e CLV. Analisi-only: mai certezze, 18+, puntare SOLO su ADM, autoesclusione.it · 800 558822.</p>
</div>"""
    html = page("Benchmark", '🏆 <span class="g">Benchmark</span>',
                "Confronto onesto modello vs mercato (RPS walk-forward per lega) + storico pubblico scaricabile in JSON/CSV.",
                body, active="benchmark")
    with open(os.path.join(SITE, "benchmark.html"), "w", encoding="utf-8") as f:
        f.write(wrap_tables(html))


def build_fonti():
    """📚 FONTI: pagina unica con tutte le fonti dati + siti valutati/non usati (spostato da metodo/glossario)."""
    siti = ""
    gf = os.path.join(ROOT, "REVIEW_SITI.md")
    if os.path.exists(gf):
        with open(gf, encoding="utf-8") as f:
            md = f.read()
        siti = "<pre style='white-space:pre-wrap;font-size:12px;background:var(--card);padding:10px;border-radius:10px'>" + md.replace("&","&amp;").replace("<","&lt;") + "</pre>"
    body = f"""<div class="card">
  <h2>📚 Fonti dati (dettaglio completo)</h2>
  <p class="sub">Ogni dato entra nel modello da una fonte pubblica e verificabile; i file locali sono nel workspace (<code>data/</code>).
  Nessuna API a pagamento (ESPN pubblica gratis, CORS *). Siti tips/affiliate = 🚩.</p>
  <table>
  <tr><th>Fonte</th><th>Cosa fornisce</th><th>URL / file locale</th></tr>
  <tr><td data-label='Fonte'><b>football-data.co.uk</b> — storico résultats Top 5 2022/23→2026/27</td>
      <td data-label='Cosa'>gol, tiri, cartellini, quote medie/max (Avg/Max, B365, PS), xG per partita, chiusure per CLV</td>
      <td data-label='URL' class='sub' style='font-size:11px'>https://www.football-data.co.uk/mmz4281/2627/I1.csv · E0.csv · SP1.csv · D1.csv · F1.csv (stagioni precedenti: 2526, 2425, …) → <code>data/{{I1,E0,SP1,D1,F1}}_*.csv</code> → <code>data/matches.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>football-data.co.uk</b> — fixtures e quote del weekend corrente</td>
      <td data-label='Cosa'>calendario partite non giocate + quote di chiusura per la finestra</td>
      <td data-label='URL' class='sub' style='font-size:11px'>https://www.football-data.co.uk/fixtures.csv → <code>data/fixtures_all_2627.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>ESPN API pubblica</b> (CORS *, gratis, no key) — diretta live + verifica esiti</td>
      <td data-label='Cosa'>scoreboard (stato, score, minuto, quote live), summary (boxscore xG/tiri/possesso, keyEvents timeline, formazioni), standings, loghi squadre</td>
      <td data-label='URL' class='sub' style='font-size:11px'>site.api.espn.com/apis/site/v2/sports/soccer/{{slug}}/scoreboard?dates=YYYYMMDD · .../summary?event={{id}} · site.web.api.espn.com .../standings · loghi: a.espncdn.com/i/teamlogos/soccer/500/{{teamId}}.png</td></tr>
  <tr><td data-label='Fonte'><b>FotMob</b> — calendario TUTTE le leghe + coppe, risultati, xG giocatori</td>
      <td data-label='Cosa'>fixtures per lega (id 55 Serie A, 47 PL, 87 LaLiga, 54 Bundesliga, 53 Ligue 1, 42 UCL, 73 UEL, 10216 UECL), risultati già giocati, SoT/90</td>
      <td data-label='URL' class='sub' style='font-size:11px'>fotmob.com/leagues/{{id}}/fixtures → <code>data/fixtures_leagues.csv</code>, <code>data/xg_fotmob_2627.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>Understat</b> — xG storici leghe nazionali 2022→2026</td>
      <td data-label='Cosa'>xG per partita (API getLeagueData), nomi mappati su football-data</td>
      <td data-label='URL' class='sub' style='font-size:11px'>understat.com → <code>data/understat_xg.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>Wincomparator</b> — best-price per partita della finestra</td>
      <td data-label='Cosa'>migliore quota 1X2, O/U 2.5, GG/NG, angoli O/U 9.5</td>
      <td data-label='URL' class='sub' style='font-size:11px'>wincomparator.com/predictions/football/... → <code>data/odds_window_*_bestprice.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>Fantacalcio-online</b> — probabili formazioni Serie A</td>
      <td data-label='Cosa'>modulo, XI probable, indisponibili per giornata (penalità Elo/xG)</td>
      <td data-label='URL' class='sub' style='font-size:11px'>fantacalcio-online.com → <code>data/lineups_giornata*.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>Open-Meteo</b> (gratis, no key) + <b>Nominatim/OSM</b> — meteo e coordinate</td>
      <td data-label='Cosa'>pioggia/vento/temperatura per città (storico + forecast 15gg) → fattore gol; coordinate squadre (da ESPN venue) → derby, distanza trasferta</td>
      <td data-label='URL' class='sub' style='font-size:11px'>api.open-meteo.com / archive-api.open-meteo.com · nominatim.openstreetmap.org → <code>data/weather_*.csv</code>, <code>data/team_coords.csv</code> (src/step30_weather.py)</td></tr>
  <tr><td data-label='Fonte'><b>Kaggle</b> — H2H internazionali (nazionali 🚩)</td>
      <td data-label='Cosa'>storico partite nazionali per H2H ed Elo seed</td>
      <td data-label='URL' class='sub' style='font-size:11px'>kaggle → <code>data/kaggle_matches.csv</code>, <code>data/fixtures_intl.csv</code></td></tr>
  <tr><td data-label='Fonte'><b>TheStatsAPI</b> — API a pagamento (da 50 $/mese): <b>valutata e NON adottata</b></td>
      <td data-label='Cosa'>le nostre 8 leghe sono già coperte dalle fonti gratis; link affiliazione (<code>via=</code>/<code>affonso_id=</code>) mai usati</td>
      <td data-label='URL' class='sub' style='font-size:11px'>thestatsapi.com (valutazione 04/11/2026)</td></tr>
  </table>
  <h2>Espandere con le fonti gratis attuali</h2>
  <p class="sub"><b>Altri campionati:</b> football-data pubblica CSV storici gratis per molte altre leghe (già aggiunte: Serie B, Championship, Eredivisie, Süper Lig, ecc.).
  <b>Altri mercati:</b> i CSV includono tiri, angoli, cartellini, arbitro → angoli/cartellini/tiri sono già nel modello (O/U angoli 9.5 in schedina).
  Quello che le fonti gratis <b>non</b> danno: quote live in-play sharp e linea di chiusura Pinnacle utili per CLV avanzato.</p>
  <p class="sub">Nota onesta: il collo di bottiglia non è la quantità di dati ma la <b>linea di chiusura del mercato</b> (benchmark.html lo misura: modello ≈ mercato, RPS ~0.19).</p>
  <h2>Aggiornamento fonti e cosa non copriamo</h2>
  <p class="sub">Fonti gratis aggiornate fino all'ultima giornata completata; le partite in corso/odierne possono essere in ritardo di qualche ora (le verifichiamo a mano da più fonti: FotMob + ESPN + diretta.it manuale).</p>
</div>
<div class="card">
  <h2>🧪 Siti valutati e NON usati (report completo)</h2>
  <p class="sub">REVIEW_SITI.md — tutti i siti analizzati con verdetto 🚩/⚠️/✔ e motivi.</p>
  {siti}
</div>"""
    html = page("Fonti dati", '📚 <span class="g">Fonti</span>',
                "Tutte le fonti dati (gratis, verificabili) in un posto solo + report siti valutati e non usati.",
                body, active="fonti")
    with open(os.path.join(SITE, "fonti.html"), "w", encoding="utf-8") as f:
        f.write(wrap_tables(html))


def build_archivio():
    """ARCHIVIO: scoreboard pubblico + report/quote/giocata per giornata + report weekend, man mano archiviati."""
    rows = scoreboard_rows()
    reports = sorted(glob.glob(os.path.join(ROOT, "report_giornata*.html")), key=gj_num)
    tot_m = tot_c = 0
    rps_list = []
    for r in rows:
        try:
            tot_m += int(r["partite"]); tot_c += int(r["modello corretti"])
            if r.get("RPS modello"):
                rps_list.append(float(r["RPS modello"]))
        except Exception:
            pass
    acc = 100.0 * tot_c / tot_m if tot_m else 0
    rps_avg = sum(rps_list) / len(rps_list) if rps_list else 0
    sb_rows = "".join(
        f"<tr><td data-label='Giornata'><b>Giornata {r['giornata']}</b></td><td data-label='Partite'>{r['partite']}</td>"
        f"<td data-label='Modello'>{r['acc%']}% ({r['modello corretti']}/{r['partite']})</td>"
        f"<td data-label='RPS modello'>{r['RPS modello'] or '—'}</td><td data-label='RPS mercato'>{r.get('RPS mercato') or '—'}</td></tr>"
        for r in rows) or "<tr><td colspan=5>Nessuna giornata giocata ancora.</td></tr>"
    arch = ""
    if os.path.exists(os.path.join(SITE, "report-weekend.html")):
        arch += ("<tr><td data-label='Weekend'><b>31/10-02/11</b></td>"
                 "<td data-label='Report'><a class='btn' href='report-weekend.html'>📊 Report weekend 5 leghe →</a></td>"
                 "<td data-label='Quote'>—</td><td data-label='Giocata'>—</td></tr>")
    for rp in reports:
        g = gj_num(rp)
        arch += (f"<tr><td data-label='Giornata'><b>Giornata {g}</b></td>"
                 f"<td data-label='Report'><a class='btn' href='{os.path.basename(rp)}'>Report →</a></td>"
                 f"<td data-label='Quote'><a class='btn' href='quote_giornata{g}.html'>Quote best-price →</a></td>"
                 f"<td data-label='Giocata'><a class='btn' href='giocata_giornata{g}.html'>🎯 Singola+Raddoppio →</a></td></tr>")
    if not arch:
        arch = "<tr><td colspan=4>Nessun report ancora archiviato.</td></tr>"
    # ✅ verifica giocate per giorno (giocate passate con esito reale) — da data/verifica_*.csv
    vfiles = sorted(glob.glob(os.path.join(DATA, "verifica_*.csv")))
    # 🆕 06/11 CLV: quota pick vs chiusura (step11_clv.py)
    clv_map = {}
    clv_file = os.path.join(DATA, "clv_report.csv")
    _nn = lambda t: "".join(ch for ch in str(t).lower() if ch.isalnum())
    if os.path.exists(clv_file):
        with open(clv_file) as f:
            for c in csv.DictReader(f):
                clv_map[(_nn(c["data"])[:10], _nn(c["partita"]))] = c["CLV"]
    vcard = ""
    if vfiles:
        vtr = ""
        for vf in vfiles:
            with open(vf) as f:
                for r in csv.DictReader(f):
                    vtr += (f"<tr><td data-label='Data'>{r['data']}</td><td data-label='Tipo'><b>{r['tipo']}</b></td>"
                            f"<td data-label='Partita'>{r['partita']}</td><td data-label='Mercato'>{r['mercato']} {r['esito']}</td>"
                            f"<td data-label='p'>{r['p_modello%']}%</td><td data-label='Quota'>{r['quota_best']}</td>"
                            + (lambda cv: f"<td data-label='CLV' class='{'ev-pos' if float(cv) > 0 else 'ev-neg'}'>{float(cv):+.3f}</td>" if cv not in ('', None) else "<td data-label='CLV' class='sub'>—</td>")(clv_map.get((_nn(r['data'])[:10], _nn(str(r['partita']).split('[')[0].strip().lstrip('+').strip()))))
                            + f"<td data-label='Risultato' class='sub' style='font-size:11px'>{r['risultato']}</td>"
                            f"<td data-label='Esito'><span class='pill {'ev-pos' if '✅' in r['vinto'] else 'ev-neg'}'>{r['vinto']}</span></td></tr>")
        vcard = f"""<div class="card"><h2>✅ Verifica giocate per giorno (archiviate con l'esito reale)</h2>
<p class="sub">Ogni Singola/Raddoppio del giorno, confrontata con il risultato reale una volta giocata. Serve a misurare il modello nel tempo:
una singola vincita non prova nulla, servono serie lunghe con RPS/ROI. Stime con incertezza, mai certezze.</p>
<table><tr><th>Data</th><th>Tipo</th><th>Partita</th><th>Mercato</th><th>p</th><th>Quota</th><th>CLV</th><th>Risultato</th><th>Esito</th></tr>{vtr}</table>
<p class="sub">🆕 CLV = quota della giocata − quota di chiusura media: <b>CLV&gt;0 = battuto il mercato di chiusura</b> (metrica più onesta dell'esito singolo). Coppe senza chiusure football-data → CLV solo leghe nazionali.</p></div>"""
    body = f"""<div class="card">
  <h2>📊 Scoreboard pubblico</h2>
  <p class="sub">Accuracy 1X2 del modello + RPS (Ranked Probability Score: 0 = perfetto, più basso = meglio), confrontato col mercato (quote di chiusura).
  Complessivo: {tot_m} partite, accuratezza {acc:.1f}%, RPS medio {rps_avg:.4f}.
  Win% da sola non basta mai: serve sempre con RPS/ROI e quota.</p>
  <table><tr><th>Giornata</th><th>Partite</th><th>Modello</th><th>RPS modello</th><th>RPS mercato</th></tr>{sb_rows}</table>
  <p class="sub" style="margin-top:10px">⚠️ Nessun modello a dati gratis batte sistematicamente la linea di chiusura
  (tetto realistico ~53-56% acc. 1X2). Chi promette il contrario non è verificabile.</p>
</div>
<div class="card" id="archivio-giornate">
  <h2>🗂 Archivio per giornata (man mano che le giornate si chiudono)</h2>
  <table><tr><th>Giornata</th><th>Report</th><th>Quote</th><th>Giocata</th></tr>{arch}</table>
</div>
<p><button onclick="exportArchivio()">📤 Esporta scoreboard come CSV</button>
  <a class="btn" href="archivio_giocate.json" download>⬇ storico giocate JSON</a>
  <a class="btn" href="archivio_giocate.csv" download>⬇ storico giocate CSV</a>
  <a class="btn" href="benchmark.html">🏆 Benchmark modello vs mercato →</a></p>
<script>
function exportArchivio(){{
  var t=document.querySelector('.card table'); if(!t)return;
  var rows=Array.from(t.querySelectorAll('tr')).map(function(tr){{
    return Array.from(tr.querySelectorAll('th,td')).map(function(c){{return '"'+c.textContent.replace(/"/g,'""')+'"';}}).join(',');
  }}).join('\n');
  var a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(rows);
  a.download='archivio_scoreboard.csv'; a.click();
}}
</script>
{perf_chart(rows)}{vcard}"""
    html = page("Archivio", '🗂 <span class="g">Archivio</span>',
                "Scoreboard pubblico e tutto ciò che viene archiviato man mano: report, quote best-price e giocate delle giornate chiuse. Stime con incertezza, mai certezze.",
                body, active="archivio")
    with open(os.path.join(SITE, "archivio.html"), "w") as f:
        f.write(wrap_tables(html))


def build_metodo():
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Metodo &amp; trasparenza — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card">
  <h1>📖 Metodo &amp; <span class="g">trasparenza</span></h1>
  <h2>Il modello (v7)</h2>
  <p class="sub">Ensemble pesato <b>Elo 0.50 + Dixon-Coles 0.30 + mercato 0.20</b> (pesi ri-tunati il 13/11 su 535 match g6-g38).
  Il DC usa <b>xG per partita</b> (HxG/AxG football-data) come gol, con proxy tiri calibrato dove manca.
  <b>Home advantage stimato per lega</b> dai dati (share vittorie casa, convertita in punti Elo, clip 15-110) invece che fisso.
  <b>Stacking con meta-learner</b>: regressione logistica sui 3 membri (Elo, DC, mercato) fittata walk-forward sulle ultime 60 partite
  (stato a -45gg, no leakage) — <b>RPS 0.1918</b> vs 0.2008 pesi fissi e 0.1963 del mercato (LOO su 535 match g6-g38).
  <b>Calibrazione isotonic</b> sopra lo stacking (0.1988 su pesi fissi).
  A queste: <b>motivazione/classifica</b>, <b>congestione calendario</b>, <b>forma pesata per Elo avversario</b>,
  <b>H2H</b>, <b>bias arbitro</b>, <b>assenze</b> con impatto xG (FotMob 45gg + Understat stagione).</p>
  <h2>Validazione walk-forward</h2>
  <p class="sub">Backtest g6-g38 (535 match, train solo su dati precedenti, no leakage).
  Metriche: <b>RPS, log-loss, Brier, ECE</b>. V7 stacker: RPS <b>0.1918</b> (LOO 535 match) — meglio del mercato (0.1963);
  v6: 0.2008 grezzo → 0.1988 calibrato. Il mercato resta il benchmark (~RPS 0.19-0.20): il nostro edge non è "battere il mercato"
  in RPS, ma le <b>quote ADM specifiche</b> + segnali extra (forma, H2H, arbitro, assenze-xG) che il mercato medio non pesa.</p>
  <h2>📚 Fonti dati</h2>
  <p class="sub">Tutti i dati arrivano da <b>fonti pubbliche e gratuite</b>, senza API a pagamento e senza affiliazioni a bookmaker:
  il codice e i file sono nel repository pubblico. Siti di tips/affiliate non vengono mai usati (🚩).</p>
  <h2>Le nostre regole</h2>
  <p class="sub">✅ tutti i pronostici pubblicati con esito (vinti e persi) · ✅ win% sempre con RPS/ROI ·
  ✅ probabilità con incertezza, mai "sicuro" · ✅ max <b>1 SINGOLA + 1 RADDOPPIO al giorno</b>, stake solo se <b>EV &gt; +2%</b>, dimensionato <b>¼ Kelly con margine di incertezza</b> (p − IC 68%) ·
  ✅ 18+/ADM/autoesclusione.it ovunque · ❌ niente multiple/schedine · ❌ niente % in vetrina senza contesto ·
  ❌ niente black-box: il codice è nel workspace.</p>
  <h2>🧮 Le formule (quelle che usiamo davvero)</h2>
  <table>
  <tr><th>Concetto</th><th>Formula</th><th>Uso</th></tr>
  <tr><td data-label='Concetto'><b>EV (valore atteso)</b></td><td data-label='Formula'><code>EV = p·(O−1) − (1−p)</code> = <code>p·O − 1</code></td><td data-label='Uso'>si pubblica/gioca solo se EV &gt; 0; lo stake parte solo se EV &gt; +2%</td></tr>
  <tr><td data-label='Concetto'><b>Kelly frazionario</b></td><td data-label='Formula'><code>f* = (p·O−1)/(O−1)</code>, stake = <code>f*/4</code> (¼ Kelly)</td><td data-label='Uso'>% del bankroll da puntare su Singola/Raddoppio</td></tr>
  <tr><td data-label='Concetto'><b>CLV</b></td><td data-label='Formula'>quota giocata vs quota di chiusura mercato (Avg football-data)</td><td data-label='Uso'>misura se la nostra lettura ha battuto il mercato (archivio+CLV)</td></tr>
  <tr><td data-label='Concetto'><b>RPS</b></td><td data-label='Formula'>ranked probability score vs esito reale</td><td data-label='Uso'>metrica principale di validazione (benchmark mercato ~0.19)</td></tr>
  </table>
  <h2>🗺️ Mappa del sito (cosa c'è ora)</h2>
  <table>
  <tr><th>Pagina</th><th>Cosa fa</th></tr>
  <tr><td data-label='Pagina'>🏠 <b>Home / finestra mobile</b></td><td>partite oggi→+7 giorni, 🚩 Nazionali, quote best-price, pronostici EV&gt;0</td></tr>
  <tr><td data-label='Pagina'>🔴 <b>Diretta</b></td><td>live 30s (ESPN): loghi, hero card, quote 1X2, ⭐ preferiti, filtri LIVE/EV/⭐, barra date, dettaglio con timeline, barre xG/possesso, formazioni, H2H, confronto stagionale, classifica+capocannonieri, copia link</td></tr>
  <tr><td data-label='Pagina'>🧾 <b>Schedina del giorno</b></td><td>Singola+Raddoppio con EV&gt;+2%, stake ¼ Kelly — stampabile/PDF</td></tr>
  <tr><td data-label='Pagina'>💰 <b>Bankroll</b></td><td>tracker personale (salvato solo nel tuo browser): ROI, winrate, drawdown, verifica esiti ESPN automatica, export CSV</td></tr>
  <tr><td data-label='Pagina'>🎯 <b>Giocate</b> · ⚡ <b>PPA</b> · ⚖️ <b>Surebets</b></td><td>giocate EV&gt;0 della finestra · PPA p≥60% (html+PDF) · surebet best-price ≥+1%</td></tr>
  <tr><td data-label='Pagina'>📅 <b>Verifica</b> · 🗂 <b>Archivio+CLV</b> · 📊 <b>Report weekend</b></td><td>esiti verificati (FotMob+ESPN incrociati), CLV, report</td></tr>
  <tr><td data-label='Pagina'>🏆 <b>Benchmark</b></td><td>RPS modello vs mercato per lega (walk-forward) + <b>storico pubblico scaricabile JSON/CSV</b> (archivio_giocate) — dati aperti verificabili esternamente</td></tr>
  <tr><td data-label='Pagina'>🤖 <b>Telegram</b></td><td>digest giornaliero sul canale (giocate EV&gt;0, verifica, top PPA) + alert in privado: surebet, 🔴 LIVE di partite 🚩/⭐, 📉 quota in calo (CLV)</td></tr>
  </table>
  <h2>📅 Ultimo aggiornamento &amp; storico versioni</h2>
  <p class="sub">Pagina aggiornata il <b>{date.today().isoformat()}</b>. Pipeline automatica 4×/giorno (07:30 / 13:30 / 19:30 / 23:00 IT) su GitHub Actions gratis.</p>
  <table>
  <tr><th>Versione</th><th>Novità</th><th>Metriche (walk-forward)</th></tr>
  <tr><td data-label='Versione'>v4</td><td>ensemble Elo+DC180+mercato+xG</td><td>RPS 0.1898 · 53.3% acc. (g8-g10)</td></tr>
  <tr><td data-label='Versione'>v5 (dal 10/11/2026)</td><td>finestra mobile 7gg, Nazionali 🚩, diretta live ESPN, PPA, schedina, bankroll, Telegram</td><td>in validazione continua (archivio+CLV)</td></tr>
  <tr><td data-label='Versione'>v6 (dal 13/11/2026)</td><td>🏟️ HFA stimato per lega · 📊 xG nel DC · 🎯 calibrazione isotonic walk-forward · ⚖️ pesi ri-tunati su 535 match (g6-g38)</td><td>RPS 0.2008 → <b>0.1988 calibrato</b> (LOO); pesi 0.50/0.30/0.20 confermati</td></tr>
  <tr><td data-label='Versione'>v7 (dal 13/11/2026)</td><td>🧠 <b>stacking meta-learner</b> (logistic sui 3 membri) · 🔗 <b>correlazione raddoppio</b> (rho −0.26 stimato dai dati, EV più onesto) · 🎲 <b>¼ Kelly con incertezza</b> (IC 68% su p) · 📈 <b>forma-xG ultime 5</b> tutte le leghe · 🌦️ <b>meteo</b> (open-meteo) + <b>derby</b> (coordinate) come contesto · ✈️ <b>trasferta &gt;1000 km</b> (fatigue) · 🧊 <b>ensemble temporale</b> (media 0.65/0.35 con run precedente) · 📊 <b>stacker O/U 2.5 e GG/NG</b> · 🔴 <b>EV live O2.5</b> da xG live (min≥30) in diretta</td><td>Stacker RPS <b>0.1918</b> LOO (mercato 0.1963). Onesto: meteo/derby/GBM testati, non migliorano RPS (GBM off); stacker O/U 0.4871 vs 0.4889; 1X2 stacker 0.1918</td></tr>
  </table>
  <h2>Limiti onesti</h2>
  <p class="sub">Tetto ~53-56% acc. 1X2 per modelli a dati gratis (vedi 🏆 benchmark.html: RPS modello ~0.19 vs mercato ~0.19-0.20;
  stacker v7 su 535 match LOO g6-g38: <b>RPS 0.1918 vs mercato 0.1963</b>). La varianza del calcio è alta: anche il modello
  migliore perde journées intere (campioni piccoli: un weekend = 5-9 partite). Testati e <b>scartati</b> per nessun guadagno misurabile:
  GBM come 4° membro, meteo/derby sul RPS, consensus di LLM generici. Non disponibili gratis: linea di chiusura sharp (Pinnacle),
  quote in-play di qualità, indisponibili-xG per tutte le leghe. Per questo pubblichiamo le sconfitte e il CLV, e lo stake resta ¼ Kelly solo su EV&gt;+2%.</p>
  <h2>Aggiornamento fonti e cosa non copriamo</h2>
  <p class="sub">Fonti gratis aggiornate fino all'ultima giornata completata (lunedì mattina); le partite in corso/odierne
  possono essere in ritardo di qualche ora (le verifichiamo a mano da più fonti prima di segnare il risultato).
  Valutiamo le <b>assenze</b> in automatico (penalità Elo dagli xG dei giocatori out, Serie A), ma le <b>probabili formazioni</b>
  e la tattica le leggiamo solo via news sulle partite chiave della giocata: non è un parsing automatico.
  Il codice è veloce ma <b>deterministico e riproducibile</b>: gli errori vengono da dati/parametri, non dalla velocità;
  li intercettiamo con validazione walk-forward (no leakage), metriche RPS/log-loss/Brier e controllo incrociato dei risultati.</p>
</div>
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · 800 558822</div>
{footer("")}
</div></body></html>"""
    with open(os.path.join(SITE, "metodo.html"), "w") as f:
        f.write(wrap_tables(html))


GLOSSARIO = [
    ("Quota (odds)", "Quanto paga il bookmaker: quota 2.00 = 1€ puntato ne rende 2 (1 di vincita + 1 di posta)."),
    ("Probabilità implicita", "p = (1 / quota) × 100. Quota 2.00 → 50%. È la stima del MERCATO, non la verità."),
    ("Overround / margine", "Somma delle probabilità implicite di tutti gli esiti: è >100% (tipicamente 105-108%). La differenza è il guadagno atteso del bookmaker."),
    ("Value bet", "Quando la TUA probabilità stimata p è maggiore di quella implicita dalla quota. Esempio: p=60%, quota 2.00 (implicita 50%) → c'è valore."),
    ("EV (valore atteso)", "EV = p·(quota−1) − (1−p). EV>0 → nel lungo periodo vinci in media. Buffer ~2% prima di considerare una giocata."),
    ("Kelly frazionario", "Puntata ottimale = edge / varianza. Noi usiamo ¼ Kelly per ridurre la varianza: mai puntare più di una piccola % del bankroll."),
    ("CLV (Closing Line Value)", "Se la tua quota è migliore della quota di chiusura del mercato, nel lungo periodo sei vincente. È la metrica più onesta per giudicare un modello."),
    ("RPS (Ranked Probability Score)", "Misura quanto le tue probabilità (1,X,2) sono vicine al risultato: 0 = perfetto. Meglio dell'accuracy secca perché usa le probabilità, non solo il segno."),
    ("Log-loss / Brier", "Altre metriche probabilistiche: penalizzano le certezze sbagliate. Le usiamo nel backtest insieme a RPS."),
    ("Calibrazione / ECE", "Una probabilità del 70% dovrebbe verificarsi ~70% delle volte. L'ECE misura questa distanza: senza calibrazione le % sono fuorvianti."),
    ("Walk-forward / backtest", "Validazione onesta: prevedi la giornata N usando SOLO i dati disponibili prima di N. Niente leakage (niente dati del futuro)."),
    ("xG (expected goals)", "Gol attesi dai tiri (posizione, difficoltà). Misura la qualità delle occasioni, non solo i gol segnati. La forma «vera» si legge con l'xG."),
    ("Elo / DC", "Elo = forza storica squadra. DC (Dixon-Coles) = modello sui gol con forma pesata sui 180 giorni recenti."),
    ("Edge vs mercato", "Differenza tra la probabilità del nostro modello e quella implicita dalla quota: |edge| > 3pp = segnale forte (🚨)."),
    ("TiP (tiri in porta) Over 5.5", "TiP = Tiri in Porta (shots on target) di TUTTE e due le squadre sommati. O5.5 = Over 5.5, cioè la stima che le due squadre tirino in porta più di 5 volte e mezzo in totale (quindi almeno 6 tiri in porta). Non sono gol: sono i tiri che il portiere ha parato o che sono finiti in porta. È un mercato di volume, più prevedibile dei gol ma con quote più basse."),
    ("Cartellini Over 4.5", "Scommessa che nella partita ci siano più di 4.5 cartellini (quindi almeno 5) tra gialli e rossi. Il modello lo stima dalla frequenza storica di squadre e arbitro, ma è un mercato molto volatile: mai una certezza."),
    ("Edge vs quote (pp)", "Edge = differenza in punti percentuali (pp) tra la probabilità del NOSTRO modello e la probabilità implicita nella QUOTA del mercato. Esempio: modello 45.6%, quota 2.88 → mercato 34.7% → edge +10.9 pp. Edge positivo grande (🚨 sopra 3 pp) = la quota paga meno di quanto varrebbe secondo noi (c'è valore); edge negativo grande = il mercato la sopravvaluta. La quota da sola non basta mai: conta sempre l'edge."),
    ("Scoreboard pubblico", "Archivio di TUTTI i pronostici con esito vinto/perso + metriche. Se un sito non lo pubblica, le sue % non sono verificabili."),
    ("Mercati mostrati vs mercati giocati (regola aggiornata)", "Nel report mostriamo le stime di TUTTI i mercati (1X2, doppia chance, GG/NG, Over/Under 2.5, TiP, cartellini, marcatori, TiP 0.5 giocatori): nell'ANALISI si segue il mercato con la % da giocare più alta. La GIOCATA ufficiale (Singola + Raddoppio del giorno) può usare QUALSIASI mercato: Singola = la giocata con probabilità più alta (qualsiasi quota); Raddoppio = 2-3 eventi su partite diverse con quota combinata ≈ 2.00. I TiP 0.5 sui giocatori puntano su difensori/centrocampisti (quota più alta degli attaccanti a parità di rischio). Sempre stime con incertezza + 18+/ADM/autoesclusione.it/800 558822."),
    ("Pronostico modello vs Verdict analista", "Il PRONOSTICO DEL MODELLO è la scelta puramente statistica (solo dati: Elo, forma, gol attesi, quote). Il VERDICT DELL'ANALISTA è la scelta finale DOPO il contesto web (indisponibili, news) e il confronto col mercato: può differire dal modello (es. modello «1» → verdict «X2» se mercato e assenze lo suggeriscono). La confidence (alta/media/bassa) dice quanto ci fidiamo del verdict. Nel report mostriamo sempre entrambi, con una nota quando differiscono."),
    ("Confidence alta/media/bassa", "Nel nostro report: alta = edge alto + modello e mercato d'accordo; bassa = edge alto ma mercato in disaccordo o molte assenze. Mai «sicuro»."),
]

RED_FLAGS = [
    "'% di vincita' in vetrina senza quota media, ROI o RPS: un 70% a quota 1.20 perde soldi nel lungo periodo.",
    "'Pronostico sicuro / garantito / 100%': red flag assoluto. Nessun metodo statistico è certo.",
    "Blog che pubblica solo le vittorie (schedine vincenti, en plein): sélection bias.",
    "Algoritmi 'matematici/AI' black-box senza pesi, fonti o validazione pubblica.",
    "Affiliazione ai bookmaker nascosta o banner enormi sopra la prima pagina: l'incentivo è il click, non il valore.",
    "Multiple/schedine/sistemoni spinti come prodotto principale: alta varianza, difíciles da battere.",
    "'Affidabilità 4/5' o 'livello affidabilità' subjetivi: non sono probabilità calibrate.",
    "VIP/canali a pagamento (PayPal/Telegram) con % di un solo mese cherry-picked.",
    "Nessun disclaimer 18+/ADM/gioco responsabile visibile.",
    'Siti di tips/affiliate valutati e non usati (🚩): mai linkati né usati come fonte.',
]

GREEN_FLAGS = [
    "Scoreboard pubblico completo: ogni pronostico con esito, win% + ROI + RPS insieme, sconfitte incluse.",
    "Metodologia dichiarata e riproducibile + backtest walk-forward pubblico.",
    "Probabilità calibrate con incertezza dichiarata.",
    "Confronto con la linea di chiusura del mercato (CLV) e best-price multi-bookmaker.",
    "Stake discipline (es. ¼ Kelly) e gestione del bankroll.",
    "Disclaimer sempre visibili: 18+, solo operatori ADM, autoesclusione.it, disclosure affiliazione.",
    "Onestà sui periodi negativi (pubblicare anche ROI negativo).",
]


def build_glossario():
    terms = "".join(f'<div class="term"><b>{t}</b> — {d}</div>' for t, d in GLOSSARIO)
    reds = "".join(f"<li>{r}</li>" for r in RED_FLAGS)
    greens = "".join(f"<li>{g}</li>" for g in GREEN_FLAGS)
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Glossario — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card">
  <h1>📚 <span class="g">Glossario</span> & guida alla lettura</h1>
  <p class="sub">I termini che usiamo nei report, spiegati senza fuorviare. Poi: come riconoscere un sito di pronostici affidabile (dal nostro studio sui competitor).</p>
  <h2>Termini tecnici</h2>
  {terms}
  <h2>🚩 Red flags: i siti di pronostici da cui stare alla larga</h2>
  <div class="warn"><ul style="margin:6px 0 6px 18px">{reds}</ul></div>
  <h2>✅ Green flags: cosa cercare in un sito serio</h2>
  <div class="okbox"><ul style="margin:6px 0 6px 18px">{greens}</ul></div>
  <h2>Come leggiamo noi una partita (le 4 fasi)</h2>
  <p class="sub">1) <b>Modello</b> (probabilità 1X2 + mercati) → 2) <b>Contesto web</b> (indisponibili, formazioni, news multi-sorgente) →
  3) <b>Confronto col mercato</b> (edge vs quota, best-price) → 4) <b>Verdetto con confidence</b> (alta/media/bassa) + rischio.
  Una sola partita per giornata (mode 1).</p>
</div>
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · Numero Verde 800 558822</div>
{footer("")}
</div></body></html>"""
    with open(os.path.join(SITE, "glossario.html"), "w") as f:
        f.write(wrap_tables(html))


def build_quote(bp):
    g = gj_num(bp)
    with open(bp) as f:
        rows = list(csv.DictReader(f))
    trs = ""
    for r in rows:
        pi = r.get("prob_implicita_pct") or ""
        aw = r.get("algo_wincomparator_pct") or ""
        trs += (f"<tr><td data-label='Partita'><b>{r['partita']}</b></td><td data-label='Data'>{r['data']}</td><td data-label='Esito'><b>{r['esito']}</b></td>"
                f"<td data-label='Best quota'><b>{r['best_quota']}</b></td><td data-label='Bookmaker'>{r['bookmaker']}</td>"
                f"<td data-label='Prob. implicita'>{pi}%</td><td data-label='Prob. algo'>{aw}%</td><td data-label='Fonte' class='sub'>{r['fonte']}</td></tr>")
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Quote best-price Giornata {g} — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card">
  <h1>💰 Quote <span class="g">best-price</span> — Giornata {g}</h1>
  <p class="sub">Per ogni esito 1X2 la <b>migliore quota disponibile</b> tra i bookmaker ADM mostrati dai comparatori
  (qui: wincomparator), con la <b>probabilità implicita</b> (1/quota × 100) e, per confronto, la probabilità del loro algoritmo.
  Giocare sempre la quota più alta = massimizzare il CLV. <b>Le quote cambiano: verifica sempre sul sito dell'operatore.</b></p>
  <table><tr><th>Partita</th><th>Data</th><th>Esito</th><th>Best quota</th><th>Bookmaker</th><th>Prob. implicita</th><th>Prob. algo (rif.)</th><th>Fonte</th></tr>{trs}</table>
  <p class="sub" style="margin-top:10px">Nota: "prob. implicita" è la stima del mercato, non una previsione nostra. Il nostro modello la confronta col proprio edge (vedi report).</p>
</div>
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · 800 558822 · Le quote mostrate sono indicative e possono variare.</div>
{footer("archivio")}
</div></body></html>"""
    with open(os.path.join(SITE, f"quote_giornata{g}.html"), "w") as f:
        f.write(wrap_tables(html))



def norm(name):
    return name.replace(" - ", "-").replace("\u2013", "-").strip()


def build_giocata(g):
    """Pagina giocata_giornataN.html: Singola del giorno (max EV) + Raddoppio (top2 EV, partite diverse).
    Mostra sempre: p modello, best quota, prob implicita, edge pp, EV%, stake 1/4 Kelly. Mai 'sicuro'."""
    fpath = os.path.join(DATA, f"forecast_giornata{g}.csv")
    bpath = os.path.join(DATA, f"odds_giornata{g}_bestprice.csv")
    if not (os.path.exists(fpath) and os.path.exists(bpath)):
        return
    try:
        from make_report import VERDICTS
    except Exception:
        VERDICTS = {}
    with open(fpath) as f:
        fc = {norm(r["partita"]): r for r in csv.DictReader(f)}
    with open(bpath) as f:
        bp = list(csv.DictReader(f))
    pm = {"1": "p1%", "X": "pX%", "2": "p2%"}
    cands = []
    for r in bp:
        key = norm(r["partita"])
        if key not in fc:
            continue
        p = float(fc[key][pm[r["esito"]]]) / 100.0
        q = float(r["best_quota"])
        ev = p * (q - 1) - (1 - p)
        edge_pp = (p - 1.0 / q) * 100
        kelly = ev / (q - 1) if q > 1 else 0.0
        stake = min(max(kelly / 4 * 100, 0.0), 5.0)
        cands.append(dict(partita=r["partita"], data=r["data"], esito=r["esito"], q=q,
                          book=r["bookmaker"], p=p * 100, ev=ev * 100, edge=edge_pp,
                          stake=stake, conf=fc[key].get("conf%", ""), orario=fc[key].get("orario", ""),
                          motivo=(fc[key].get("motivo_verbale") or fc[key].get("motivo") or "—").replace("<", "&lt;")))
    if not cands:
        return
    # SINGOLA DEL GIORNO = miglior percentuale di riuscita del modello
    single = max(cands, key=lambda c: c["p"])
    # RADDOPPIO/TRIS DEL GIORNO = 2-3 eventi su partite diverse, quota combinata (prodotto quote) ~ 2.00
    best_combo, best_key = None, None
    for size in (2, 3):
        for combo in combinations(cands, size):
            if len({c["partita"] for c in combo}) != size:   # una sola quota per partita
                continue
            q2 = 1.0
            p2 = 1.0
            for c in combo:
                q2 *= c["q"]
                p2 *= c["p"] / 100
            ev2 = p2 * (q2 - 1) - (1 - p2)
            key = (abs(q2 - 2.00), -ev2)   # prima vicinanza a 2.00, poi EV più alto
            if best_key is None or key < best_key:
                best_key, best_combo = key, list(combo)
    double = best_combo or []

    def row_html(c, label=""):
        v = VERDICTS.get(c["partita"].replace("-", " - "), None)
        verd = f" · verdict: <b>{v[0]}</b> (conf {v[1]})" if v else ""
        return (f"<tr><td data-label='Partita'><b>{c['partita']}</b><br><span class='sub'>{c['data']} · {c['orario']}</span></td>"
                f"<td data-label='Esito'><b>{c['esito']}</b>{verd}</td>"
                f"<td data-label='p modello'>{c['p']:.1f}%</td>"
                f"<td data-label='Best quota'><b>{c['q']:.2f}</b> @ {c['book']}</td>"
                f"<td data-label='Prob. implicita'>{100 / c['q']:.1f}%</td>"
                f"<td data-label='Edge'>{c['edge']:+.1f} pp</td>"
                f"<td data-label='EV'>{c['ev']:+.2f}%</td>"
                f"<td data-label='Stake 1/4 Kelly'>{c['stake']:.2f}% bankroll</td></tr>"
                f"<tr class='mrow'><td colspan='8' data-label='Motivo (perché)'>{c.get('motivo','—')}</td></tr>")

    if len(double) >= 2:
        q2 = 1.0
        p2 = 1.0
        for c in double:
            q2 *= c["q"]
            p2 *= c["p"] / 100
        p2 *= 100
        ev2 = (p2 / 100) * (q2 - 1) - (1 - p2 / 100)
        kelly2 = (ev2 / 100) / (q2 - 1) if q2 > 1 else 0
        stake2 = min(max(kelly2 / 4 * 100, 0), 5.0)
        dbl_html = f"""
<div class="card">
  <h2>➕ Raddoppio/Tris del giorno <span class="sub">(2-3 eventi su partite diverse, quota combinata ≈ 2.00)</span></h2>
  <div class="tablewrap"><table>
  <tr><th>Partita</th><th>Esito</th><th>p modello</th><th>Best quota</th><th>Prob. implicita</th><th>Edge</th><th>EV</th><th>Stake ¼ Kelly</th></tr>
  {"".join(row_html(c) for c in double)}
  </table></div>
  <p class="sub" style="margin-top:10px"><b>Totale raddoppio/tris:</b> quota combinata <b>{q2:.2f}</b> ·
  probabilità combinata <b>{p2:.1f}%</b> (= p1 × p2, le probabilità si moltiplicano) ·
  EV <b>{ev2 * 100:+.2f}%</b> · stake ¼ Kelly <b>{stake2:.2f}%</b> del bankroll.<br>
  ⚠️ La multipla (2-3 eventi) ha <b>varianza molto più alta</b> di una singola: basta un evento sbagliato e perdi tutto.
  È una stima con incertezza, non un "pronostico sicuro".</p>
</div>"""
    else:
        dbl_html = ""

    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Giocata del giorno — Giornata {g} — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card">
  <h1>🎯 Giocata del giorno — <span class="g">Giornata {g}</span></h1>
  <p class="sub">Selezionata dal modello: <b>Singola</b> = la giocata con la <b>maggiore probabilità di riuscita</b> stimata;
  <b>Raddoppio/Tris</b> = 2-3 eventi su partite diverse con <b>quota combinata (prodotto delle quote) ≈ 2.00</b>. Ogni dato è una <b>stima con incertezza</b>.</p>
</div>
<div class="card">
  <h2>1️⃣ Singola del giorno <span class="sub">(max % di riuscita del modello)</span></h2>
  <div class="tablewrap"><table>
  <tr><th>Partita</th><th>Esito</th><th>p modello</th><th>Best quota</th><th>Prob. implicita</th><th>Edge</th><th>EV</th><th>Stake ¼ Kelly</th></tr>
  {row_html(single)}
  </table></div>
  <p class="sub" style="margin-top:10px">EV = p·(quota−1) − (1−p): se > 0 c'è valore teorico vs mercato. Edge = p modello − prob. implicita.
  Stake = ¼ Kelly (frazione prudente), mai più del 5% del bankroll. <b>Non è un consiglio di gioco.</b></p>
</div>
{dbl_html}
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · Numero Verde 800 558822.<br>
Queste sezioni sono <b>analisi statistiche a scopo educativo</b>: probabilità stimate dal modello, mai certezze.
I risultati passati non garantiscono risultati futuri. Nessun "pronostico sicuro" esiste. Gioca solo se maggiorenne e con denaro che puoi permetterti di perdere.</div>
{footer("archivio")}
</div></body></html>"""
    with open(os.path.join(SITE, f"giocata_giornata{g}.html"), "w") as f:
        f.write(wrap_tables(html))



def _norm(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


_IND_EURO = None


def indisponibili_euro():
    """CSV fantacalcio EuroLeghe -> dizionario team-normalizzato -> lista giocatori."""
    global _IND_EURO
    if _IND_EURO is not None:
        return _IND_EURO
    _IND_EURO = {}
    p = os.path.join(DATA, "indisponibili_euro.csv")
    if os.path.exists(p):
        with open(p) as f:
            for r in csv.DictReader(f):
                tag = "🚫 squalificato" if (r.get("tipo") or "") == "Squalificati" else "🤕 infortunato"
                _IND_EURO.setdefault(_norm(r["team"]), []).append(f"{r['giocatore']} ({tag})")
    return _IND_EURO


def ind_euro_for(partita):
    """Dato 'Casa - Ospite', restituisce le assenze trovate per le due squadre."""
    ind = indisponibili_euro()
    if not ind or " - " not in str(partita):
        return ""
    h, a = str(partita).split(" - ", 1)
    out = []
    for name in (h, a):
        n = _norm(name)
        for tn, lst in ind.items():
            if n and (n in tn or tn in n):
                out.append(f"{name}: " + ", ".join(lst[:6]))
    return (" ⚠️ Indisponibili EuroLeghe (fantacalcio.it): " + " | ".join(out)) if out else ""


def match_card(r):
    pc = {"1": "p1", "X": "pX", "2": "p2"}.get(str(r["pronostico"]), "mut")
    q = r.get("quota_best") or "—"
    # 🆕 06/11 edge calcolato QUI (EV% del pronostico su quota best): la colonna edge_vs_mercato non esiste in forecast_multi.csv
    try:
        pv0 = {"1": float(r["p1%"]), "X": float(r["pX%"]), "2": float(r["p2%"])}[str(r["pronostico"])]
        ev0 = (pv0 / 100.0 * float(str(q).replace(",", ".")) - 1.0) * 100.0
        e = f"{ev0:+.1f}%"
    except Exception:
        e = "—"
    ec = "ev-pos" if e.startswith("+") else ("ev-neg" if e.startswith("-") else "mut")
    edge = e  # 🆕 il template usa {edge}: edge calcolato sopra (EV% su quota best)
    warn = r.get("⚠️") or ""
    try:
        if float(q) > 6.0:
            warn += " ⚠️ quota anomala (ignora)"
    except (ValueError, TypeError):
        pass
    try:
        if abs(float(str(edge).replace("+", ""))) > 25:
            warn += " ⚠️ edge estremo (quota sospetta)"
    except (ValueError, TypeError):
        pass
    mot = (r.get("motivo_verbale") or r.get("motivo") or "—").replace("<", "&lt;")
    mot_num = (r.get("motivo") or "").replace("<", "&lt;")
    # 🆕 06/11 verdetto dell'analista per ogni partita (da EV del pronostico + conf)
    try:
        pv = {"1": float(r["p1%"]), "X": float(r["pX%"]), "2": float(r["p2%"])}[str(r["pronostico"])]
        qq = float(str(q).replace(",", "."))
        ev = (pv / 100.0 * qq - 1.0) * 100.0
    except Exception:
        ev = None
    try:
        cf = float(r["conf%"])
    except Exception:
        cf = 0.0
    vconf = "alta" if cf >= 60 else ("media" if cf >= 50 else "bassa")
    if ev is None:
        vtxt, vc = "❔ senza quota → solo analisi, nessuna giocata", "v-ok"
    elif ev >= 15:
        vtxt, vc = f"✅ VAI — edge forte (EV {ev:+.1f}%)", "v-go"
    elif ev >= 5:
        vtxt, vc = f"👍 VAI — edge buono (EV {ev:+.1f}%)", "v-go"
    elif ev > 0:
        vtxt, vc = f"⚠️ BORDERLINE — EV {ev:+.1f}% (gioca solo se resta >0 dopo margine ~2%)", "v-bor"
    else:
        vtxt, vc = f"⛔ NO — EV {ev:+.1f}% negativo: nessuna giocata", "v-no"
    return f"""
<div class="mc">
  <div class="mc-h">{r['partita']} <span class="sub">giornata {r['giornata']} · {r['orario']}</span>{f' · ⚽ corner attesi {r["corners_attesi"]}' + (f' (O9.5 {r["CornersO95%"]}% @ {r["quota_C_O95_best"]})' if str(r.get('CornersO95%') or '') not in ('','nan') and str(r.get('quota_C_O95_best') or '') not in ('','nan') else '') if str(r.get('corners_attesi') or '') not in ('', 'nan') else ''}{f' · 📈 mov. quota {r["steam1"]}%' if str(r.get('steam1') or '') not in ('', 'nan') and abs(float(r['steam1'])) >= 3 else ''}</div>
  <div class="mc-row">
    <div class="ms"><span class="stl">Pron.</span><span class="stv"><span class="pill {pc}">{r['pronostico']}</span> {warn}</span></div>
    <div class="ms"><span class="stl">Conf.</span><span class="stv">{r['conf%']}%</span><span class="cbar"><i style="width:{r['conf%']}%"></i></span></div>
    <div class="ms"><span class="stl">1X2</span><span class="stv">1&nbsp;{r['p1%']}%</span><span class="stv">X&nbsp;{r['pX%']}%</span><span class="stv">2&nbsp;{r['p2%']}%</span></div>
    <div class="ms"><span class="stl">O2.5</span><span class="stv">{r['Over2.5%']}%</span></div>
    <div class="ms"><span class="stl">GG</span><span class="stv">{r['BTTS%']}%</span></div>
    <div class="ms"><span class="stl">Punt. esatto+prob</span><span class="stv">{r['risultato+prob%']}</span></div>
    <div class="ms"><span class="stl">Quota best 1X2</span><span class="stv">{q}</span></div>
    {f'<div class="ms"><span class="stl">Quota GG</span><span class="stv">{r.get("quota_GG_best")}</span></div>' if str(r.get('quota_GG_best') or '') not in ('', 'nan') else ''}
    {f'<div class="ms"><span class="stl">Quota O2.5</span><span class="stv">{r.get("quota_O25_best")}</span></div>' if str(r.get('quota_O25_best') or '') not in ('', 'nan') else ''}
    <div class="ms"><span class="stl">Edge</span><span class="stv"><span class="pill {ec}">{edge}</span></span></div>
  </div>
  <div class="mc-mot">🔍 <b>Motivo (in parole):</b> {mot}{ind_euro_for(r.get('partita',''))}
    <details style="margin-top:4px;color:#64748b"><summary style="cursor:pointer;font-size:10px">dati numerici</summary><span style="font-size:10px">{mot_num}</span></details>
  </div>
  <div class="verdetto {vc}">🧑‍⚖️ Verdetto dell'analista: {vtxt} — conf {vconf} ({r['conf%']}%). Stima, non garanzia.</div>
</div>"""


def league_section(l, frows):
    ms = [x for x in frows if x["lega"] == l]
    cards = "".join(match_card(r) for r in sorted(ms, key=lambda x: x["orario"]))
    return f"""<div class="card" id="{slug(l)}"><h2>🏴 {l} <span class="chip">{len(ms)} partite</span></h2>
<div class="mc-grid">{cards}</div></div>"""


def toc(leagues, label="Indice sezioni"):
    links = " ".join(f'<a class="btn" href="#{slug(l)}">{l}</a>' for l in leagues)
    return f'<p class="sub"><b>📑 {label}:</b> {links}</p>'


def validation_card():
    val_p = os.path.join(DATA, "validation_multi.csv")
    if not os.path.exists(val_p):
        return ""
    with open(val_p) as f:
        vrows = list(csv.DictReader(f))
    agg = {}
    for r in vrows:
        l = r["lega"]
        a = agg.setdefault(l, {"n": 0, "am": [], "rm": [], "ak": [], "rk": []})
        try: a["n"] += int(float(r["partite"]))
        except Exception: pass
        for k, col in (("am", "acc_modello%"), ("rm", "RPS_modello"), ("ak", "acc_mercato%"), ("rk", "RPS_mercato")):
            try: a[k].append(float(r[col]))
            except Exception: pass
    vtr = ""
    for l, a in sorted(agg.items()):
        am = sum(a["am"]) / len(a["am"]) if a["am"] else 0
        rm = sum(a["rm"]) / len(a["rm"]) if a["rm"] else 0
        ak = sum(a["ak"]) / len(a["ak"]) if a["ak"] else 0
        rk = sum(a["rk"]) / len(a["rk"]) if a["rk"] else 0
        edge = rk - rm
        vtr += (f"<tr><td data-label='Lega'><b>{l}</b></td><td data-label='Partite'>{a['n']}</td>"
                f"<td data-label='Acc. modello'>{am:.1f}%</td><td data-label='Acc. mercato'>{ak:.1f}%</td>"
                f"<td data-label='RPS modello'>{rm:.4f}</td><td data-label='RPS mercato'>{rk:.4f}</td>"
                f"<td data-label='Edge RPS'>{'+' if edge >= 0 else ''}{edge:.4f}</td></tr>")
    return f"""<div class="card"><h2>📊 Validazione walk-forward per lega (g6-g10 2026/27)</h2>
<p class="sub">RPS modello vs mercato (quote di chiusura) addestrando solo sulle partite precedenti a ogni giornata.
Edge positivo = il modello batte il mercato su quella lega. Campioni piccoli: da leggere con cautela.</p>
<table><tr><th>Lega</th><th>Partite</th><th>Acc. modello</th><th>Acc. mercato</th><th>RPS modello</th><th>RPS mercato</th><th>Edge RPS</th></tr>
{vtr}</table></div>"""


def giocata_card_html():
    """Card giocata RAGGRUPPATE PER GIORNO: per ogni data della finestra, Singola del giorno + Raddoppio del giorno."""
    # 🆕 13/11 esito reale sulle giocate dei giorni passati (da verifica_*.csv)
    _nn = lambda t: "".join(ch for ch in str(t).lower() if ch.isalnum())
    ver_map = {}
    for vf in sorted(glob.glob(os.path.join(DATA, "verifica_*.csv"))):
        with open(vf) as f:
            for r in csv.DictReader(f):
                ver_map[(_nn(r["data"])[:10], r["tipo"], _nn(str(r["partita"]).split("[")[0].strip()))] = r.get("vinto", "")
    gj_p = os.path.join(DATA, "giocata_multi.csv")
    if not os.path.exists(gj_p):
        return ""
    with open(gj_p) as f:
        grows = list(csv.DictReader(f))
    days = {}
    for r in grows:
        days.setdefault(r.get("data") or "", []).append(r)
    parts = []
    for d in sorted(days):
        label = (d[8:] + "/" + d[5:7] + "/" + d[:4]) if d else "finestra"
        gtr = ""
        for r in days[d]:
            mot = (r.get("motivo") or "—").replace("<", "&lt;")
            mc = r.get("mercato") or "1X2"
            evv = str(r.get('EV%') or '')
            evc = 'ev-pos' if evv.startswith('+') or (evv and float(evv) > 0) else ('ev-neg' if evv else 'mut')
            vd = (r.get("verdetto") or "").replace("<", "&lt;")
            vc = 'v-no' if vd.startswith('⛔') else ('v-bor' if vd.startswith('⚠️') else ('v-go' if vd.startswith('✅') else 'v-ok'))
            gtr += (f"<tr><td data-label='Tipo'><span class='pill t-{r['tipo'].lower()}'>{r['tipo']}</span></td><td data-label='Lega'>{r['lega']}</td>"
                    f"<td data-label='Partita'>{r['partita']}{(' <b>' + ver_map.get((_nn(r.get('data','')), r['tipo'], _nn(str(r['partita']).split('[')[0].strip())), '') + '</b>') if ver_map.get((_nn(r.get('data','')), r['tipo'], _nn(str(r['partita']).split('[')[0].strip()))) else ''}</td><td data-label='Mercato'>{mc}</td>"
                    f"<td data-label='Esito'><b>{r['esito']}</b></td>"
                    f"<td data-label='p modello'>{r['p_modello%']}%</td><td data-label='Quota best'>{r['quota_best']}</td>"
                    f"<td data-label='EV'><span class='pill {evc}'>{r['EV%']}%</span></td></tr>"
                    f"<tr class='mrow'><td colspan='8' data-label='Motivo (perché)'>{mot}</td></tr>"
                    f"<tr class='mrow'><td colspan='8' data-label='Verdetto'><div class='verdetto {vc}'>🧑‍⚖️ Verdetto dell'analista: {vd}</div></td></tr>")
        parts.append(f"""<div class="card" style="border:1px solid #0ea5e9" id="g{label.replace('/', '')}">
<h2 class="day">📅 {label} — Singola + Raddoppio del giorno</h2>
<table><tr><th>Tipo</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Esito</th><th>p modello</th><th>Quota best</th><th>EV</th></tr>{gtr}</table></div>""")
    if not parts:
        return ""
    return "".join(parts)


def lineups_tips_cards():
    body = ""
    lu_files = sorted(glob.glob(os.path.join(DATA, "lineups_giornata*.csv")), key=gj_num)
    if lu_files:
        lp = lu_files[-1]
        lg = gj_num(lp)
        with open(lp) as f:
            lrows = list(csv.DictReader(f))
        ltr = ""
        for r in lrows:
            ltr += (f"<tr><td data-label='Squadra'><b>{r['team']}</b></td>"
                    f"<td data-label='Modulo'>{r['modulo']}</td><td data-label='Allenatore'>{r['allenatore']}</td>"
                    f"<td data-label='XI probabile' class='sub' style='font-size:11px'>{r['xi_probabile']}</td>"
                    f"<td data-label='Indisponibili' class='sub' style='font-size:11px;color:#f87171'>{r['indisponibili']}</td></tr>")
        body += f"""<div class="card" style="border:1px solid #f59e0b"><h2>📋 Probabili formazioni — Serie A g{lg} (squadre tipo + indisponibili)</h2>
<p class="sub">Modulo e XI probabili per squadra tipo + indisponibili della giornata. Nel modello gli indisponibili generano una <b>penalità di rotazione Elo</b>.
Stime con incertezza: le formazioni possono cambiare fino all'ultimo. 18+ · ADM · autoesclusione.it · 800 558822.</p>
<table><tr><th>Squadra</th><th>Modulo</th><th>Allenatore</th><th>XI probabile</th><th>Indisponibili</th></tr>{ltr}</table></div>"""
    tip_files = sorted(glob.glob(os.path.join(DATA, "player_tip_giornata*.csv")), key=gj_num)
    if tip_files:
        tp = tip_files[-1]
        tg = gj_num(tp)
        with open(tp) as f:
            trows = [r for r in csv.DictReader(f) if r.get("solo_DM") == "True"][:10]
        ttr = ""
        for r in trows:
            mot = (r.get("motivo_verbale") or "").replace("<", "&lt;")
            ttr += (f"<tr><td data-label='Giocatore'><b>{r['giocatore']}</b></td>"
                    f"<td data-label='Squadra'>{r['team']}</td><td data-label='Ruolo'>{r['ruolo']}</td>"
                    f"<td data-label='P(TiP O0.5)'><b>{r['p_TiP0.5%']}%</b></td>"
                    f"<td data-label='SoT/90'>{r['sot_ogni_90']}</td><td data-label='Minuti medi'>{r['minuti_medi']}</td>"
                    f"<td data-label='Quota best'>best-price ADM</td>"
                    f"<td data-label='Motivo (in parole)' class='sub' style='font-size:11px'>{mot}</td></tr>")
        body += f"""<div class="card" style="border:1px solid #a855f7"><h2>🎯 TiP 0.5 GIOCATORI — difensori/centrocampisti (Serie A g{tg})</h2>
<p class="sub">P(almeno 1 tiro in porta) dal modello sui dati FotMob (SoT ogni 90', half-life 30 gg). Su D/M la quota TiP O0.5 è più alta che sugli attaccanti:
best-price su comparatore ADM. Analisi educativa solo: stime con incertezza, mai certezze. 18+ · ADM · autoesclusione.it · 800 558822.</p>
<table><tr><th>Giocatore</th><th>Squadra</th><th>Ruolo</th><th>P(TiP O0.5)</th><th>SoT/90</th><th>Min medi</th><th>Quota</th><th>Motivo (in parole)</th></tr>{ttr}</table></div>"""
    return body


def window_label(frows):
    days = sorted({r["orario"].split(" ")[0] for r in frows})
    return f"{days[0]}–{days[-1]}/11/2026" if days else "—"


def page(title, h1, sub, body, active=""):
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>{title} — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card"><h1>{h1}</h1>
<p class="sub">{sub}</p>
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · Numero Verde 800 558822</div>
</div>
{body}
{footer(active)}
</div></body></html>"""


def build_multi():
    """Pagina 🌍 Top 5: validazione + formazioni/TiP + forecast delle 5 leghe nazionali."""
    fc_p = os.path.join(DATA, "forecast_multi.csv")
    if not os.path.exists(fc_p):
        return
    with open(fc_p) as f:
        frows = [r for r in csv.DictReader(f) if r["lega"] in TOP5]
    body = validation_card() + lineups_tips_cards()
    if frows:
        leagues = [l for l in TOP5 if any(r["lega"] == l for r in frows)]
        cards = "".join(league_section(l, frows) for l in leagues)
        body += f"""<div class="card"><h2>🌍 Previsioni Top 5 — finestra {window_label(frows)}</h2>
<p class="sub">{len(frows)} partite non ancora giocate su {len(leagues)} campionati. Ogni lega è addestrata separatamente (Elo + Dixon-Coles su quella lega).</p>
<p><a class="btn" href="altre-leghe.html">➕ Altre leghe (Serie B, Championship, Eredivisie, …) →</a></p>
{toc(leagues)}
<p class="sub" style="font-size:11px">ℹ️ <b>Pron.</b> = esito 1X2 più probabile (somma di tutti i punteggi con quell'esito). <b>Punt. esatto+prob</b> = singolo punteggio più frequente (es. 1-1 13%):
può essere un pareggio anche se il pronostico è «1», perché la «1» si spartisce su tanti punteggi (1-0, 2-1, 3-0...).</p>
<p class="sub" style="font-size:11px">Le quote best-price sono recuperate da wincomparator (🚨 = edge &gt; 3pp vs mercato medio).</p></div>""" + cards
    html = page("Previsioni Top 5", '🌍 <span class="g">Top 5</span> — League nazionali',
                "Serie A · Premier League · LaLiga · Bundesliga · Ligue 1. Modello addestrato separatamente per ogni campionato, validato walk-forward. Stime con incertezza, mai certezze.",
                body, active="top5")
    with open(os.path.join(SITE, "multi-lega.html"), "w") as f:
        f.write(wrap_tables(html))


def build_altre():
    """Pagina ➕ Altre leghe: le 8 leghe extra con storico gratis (Serie B, Championship, Eredivisie, ...)."""
    fc_p = os.path.join(DATA, "forecast_multi.csv")
    if not os.path.exists(fc_p):
        return
    with open(fc_p) as f:
        frows = [r for r in csv.DictReader(f) if r["lega"] in EXTRA + INTL]  # 🆕 10/11 + nazionali
    if not frows:
        return
    leagues = [l for l in EXTRA + INTL if any(r["lega"] == l for r in frows)]
    cards = "".join(league_section(l, frows) for l in leagues)
    body = f"""<div class="card"><h2>➕ Altre leghe — fonti gratis</h2>
<p class="sub">{len(frows)} partite non ancora giocate — finestra {window_label(frows)}.
Leghe aggiunte il 04/11/2026 con dati gratis: storico 2022→2026 da <b>football-data.co.uk</b> (CSV), calendario da <b>FotMob</b>, quote best-price da <b>wincomparator</b>.
Ogni lega ha il suo modello (Elo + Dixon-Coles) addestrato solo sui propri match storici. Stime con incertezza, mai certezze.</p>
{toc(leagues)}
<p class="sub" style="font-size:11px">Stesse convenzioni della pagina Top 5: <b>Pron.</b> = esito 1X2 più probabile · <b>Punt. esatto+prob</b> = punteggio più frequente · quote best-price wincomparator (🚨 = edge &gt; 3pp).</p>
<p><a class="btn" href="multi-lega.html">← Torna a Top 5</a></p></div>""" + cards
    html = page("Altre leghe", '➕ <span class="g">Altre leghe</span>',
                "Serie B · Championship · Eredivisie · Primeira Liga · Süper Lig · Bundesliga 2 · LaLiga 2 · Ligue 2 — fonti gratis, modello per-lega.",
                body, active="top5")
    with open(os.path.join(SITE, "altre-leghe.html"), "w") as f:
        f.write(wrap_tables(html))


def build_coppe():
    """Pagina 🏆 Coppe europee: forecast UCL/UEL/UECL con Elo seminato dalle leghe nazionali."""
    fc_p = os.path.join(DATA, "forecast_coppe.csv")  # 🆕 06/11: persistente, non svuotato dalle finestre senza coppe
    if not os.path.exists(fc_p):
        fc_p = os.path.join(DATA, "forecast_multi.csv")
    if not os.path.exists(fc_p):
        return
    with open(fc_p) as f:
        frows = [r for r in csv.DictReader(f) if r["lega"] in CUPS]
    if not frows:
        return
    leagues = [l for l in CUPS if any(r["lega"] == l for r in frows)]
    cards = "".join(league_section(l, frows) for l in leagues)
    body = f"""<div class="card"><h2>🏆 Come è fatto il modello per le coppe</h2>
<p class="sub">Le coppe non hanno uno storico lungo come i campionati: uso i <b>match già giocati della stagione in corso</b>
(UCL 54, UEL 54, UECL 36 da FotMob) e semino l'<b>Elo di ogni squadra con il rating della sua lega nazionale</b> (Top 5).
Per questo le stime delle coppe hanno <b>più incertezza</b> di quelle delle leghe: leggile come indicative, mai come certezze.</p>
<p class="sub">{len(frows)} partite non ancora giocate — finestra {window_label(frows)} (turno UCL/UEL 4, UECL 3). Quote best-price da wincomparator.</p>
{toc(leagues)}</div>""" + cards
    html = page("Coppe europee", '🏆 <span class="g">Coppe europee</span> — UCL · UEL · UECL',
                "Champions League · Europa League · Conference League 2026/27. Elo seminato dalle leghe nazionali + Dixon-Coles sui match di coppa già giocati. Stime con incertezza, mai certezze.",
                body, active="europa")
    with open(os.path.join(SITE, "coppe.html"), "w") as f:
        f.write(wrap_tables(html))


def build_giocata_multi():
    """Pagina 🎯 Giocata multi-lega dedicata (Singola + Raddoppio della finestra corrente)."""
    card = giocata_card_html()
    body = card or '<div class="card"><p class="sub">Giocata non ancora generata: <code>python3 src/weekly_multi.py</code></p></div>'
    body += """<div class="card"><p class="sub">Per <b>ogni giorno</b> della finestra il modello propone la sua <b>Singola del giorno</b> e il suo <b>Raddoppio del giorno</b>
(2-3 eventi su partite diverse, quota ≈ 2.00) — <b>solo se EV &gt; 0</b>: se in un giorno non c'è nulla con EV positivo,
la pagina mostra <b>NESSUNA</b> e lo stake resta 0. Stake pieno solo se EV &gt; +2% (¼ Kelly).
Rigirando <code>python3 src/weekly_multi.py</code> ogni giorno la pagina si aggiorna con le nuove partite. Analisi a scopo di studio:
stime con incertezza, mai certezze né consigli di gioco. 18+ · ADM · autoesclusione.it · 800 558822.</p></div>"""
    html = page("Giocata multi-lega", '🎯 <span class="g">Giocata</span> multi-lega',
                "Per ogni giorno: Singola del giorno + Raddoppio del giorno (quota ≈ 2.00), con probabilità, best-price, EV e regola stake. Analisi solo, non consigli di gioco.", body, active="giocate")
    with open(os.path.join(SITE, "giocata_multi.html"), "w") as f:
        f.write(wrap_tables(html))


def build_report_weekend():
    """Pagina report-weekend.html: previsioni walk-forward vs risultati del weekend, 5 leghe."""
    rp = os.path.join(DATA, "report_weekend.csv")
    if not os.path.exists(rp):
        return
    with open(rp) as f:
        rows = list(csv.DictReader(f))
    # riepilogo per lega
    agg = {}
    for r in rows:
        if r["✅/❌"] in ("✅", "❌"):
            a = agg.setdefault(r["lega"], {"n": 0, "ok": 0, "vok": 0, "rm": [], "rk": []})
            a["n"] += 1
            a["ok"] += int(r["✅/❌"] == "✅")
            a["vok"] += int(r.get("verdict_ok") == "✅")
            if r.get("rps_modello"): a["rm"].append(float(r["rps_modello"]))
            if r.get("rps_mercato"): a["rk"].append(float(r["rps_mercato"]))
    srow = ""
    for l, a in sorted(agg.items()):
        rm = sum(a["rm"]) / len(a["rm"]) if a["rm"] else 0
        rk = sum(a["rk"]) / len(a["rk"]) if a["rk"] else 0
        srow += (f"<tr><td data-label='Lega'><b>{l}</b></td><td data-label='Giocate'>{a['n']}</td>"
                 f"<td data-label='Modello 1X2'>{a['ok']}/{a['n']} ({100*a['ok']/a['n']:.1f}%)</td>"
                 f"<td data-label='Verdict analista'><b>{a['vok']}/{a['n']} ({100*a['vok']/a['n']:.1f}%)</b></td>"
                 f"<td data-label='RPS modello'>{rm:.4f}</td><td data-label='RPS mercato'>{rk:.4f}</td></tr>")
    body = f"""<div class="card"><h2>📊 Riepilogo weekend 31/10-02/11/2026 — 5 campionati</h2>
<p class="sub">Previsioni fatte PRIMA delle partite (walk-forward: addestramento solo su dati precedenti) confrontate con i risultati ufficiali.
RPS: 0 = perfetto, più basso è meglio. Le partite del 02/11 ancora in corso sono marcate ⏳.</p>
<table><tr><th>Lega</th><th>Giocate</th><th>Modello 1X2</th><th>Verdict analista</th><th>RPS modello</th><th>RPS mercato</th></tr>{srow}</table></div>"""
    for l in sorted({r["lega"] for r in rows}):
        cards = ""
        for r in sorted([x for x in rows if x["lega"] == l], key=lambda x: x["orario"]):
            mot = (r.get("motivo_verbale") or r.get("motivo") or "—").replace("<", "&lt;")
            ok = r["✅/❌"]
            okcls = {"✅": "#4ade80", "❌": "#f87171"}.get(ok, "#fbbf24")
            vok = r.get("verdict_ok") or "—"
            vokcls = {"✅": "#4ade80", "❌": "#f87171"}.get(vok, "#fbbf24")
            vconf = r.get("verdict_conf") or ""
            vcls = {"alta": "#4ade80", "media": "#fbbf24", "bassa": "#f87171"}.get(vconf, "#e2e8f0")
            gg_ok = r.get("gg_ok") or "—"; ou_ok = r.get("ou_ok") or "—"; mkt_ok = r.get("mercato_ok") or "—"
            ggcls = {"✅": "#4ade80", "❌": "#f87171"}.get(gg_ok, "#fbbf24")
            oucls = {"✅": "#4ade80", "❌": "#f87171"}.get(ou_ok, "#fbbf24")
            mktcls = {"✅": "#4ade80", "❌": "#f87171"}.get(mkt_ok, "#fbbf24")
            cards += f"""
<div class="mc">
  <div class="mc-h">{r['partita']} <span class="sub">g{r['giornata']} · {r['orario']} · <b style="color:{okcls}">{ok} 1X2 {r['risultato']}</b></span></div>
  <div class="mc-row">
    <div class="ms"><span class="stl">Verdict analista</span><span class="stv" style="color:{vcls}">{r.get('verdict','?')} <b style="color:{vokcls}">{vok}</b></span></div>
    <div class="ms"><span class="stl">Conf. verdict</span><span class="stv">{vconf}</span></div>
    <div class="ms"><span class="stl">Pron. modello</span><span class="stv">{r['pronostico']} <b style="color:{okcls}">{ok}</b></span></div>
    <div class="ms"><span class="stl">Mercato 1X2</span><span class="stv">{r.get('mercato_pick') or '—'} <b style="color:{mktcls}">{mkt_ok}</b></span></div>
    <div class="ms"><span class="stl">1X2 %</span><span class="stv">1&nbsp;{r['p1%']}%</span><span class="stv">X&nbsp;{r['pX%']}%</span><span class="stv">2&nbsp;{r['p2%']}%</span></div>
    <div class="ms"><span class="stl">GG (mod.)</span><span class="stv">{r.get('gg_pron','—')} <b style="color:{ggcls}">{gg_ok}</b> · {r['BTTS%']}%</span></div>
    <div class="ms"><span class="stl">O/U 2.5 (mod.)</span><span class="stv">{r.get('ou_pron','—')} <b style="color:{oucls}">{ou_ok}</b> · O {r['Over2.5%']}%</span></div>
    <div class="ms"><span class="stl">RPS mod.</span><span class="stv">{r['rps_modello'] or '—'}</span></div>
  </div>
  <div class="mc-mot">🔍 <b>Motivo (in parole):</b> {mot}</div>
</div>"""
        body += f'<div class="card"><h2>🏴 {l}</h2><div class="mc-grid">{cards}</div></div>'
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>Report weekend multi-lega — Serie A Predictor</title>
<style>{CSS}</style></head><body><div class="wrap">{NAV}
<div class="card"><h1>📊 <span class="g">Report weekend</span> — Top 5 (31/10-02/11/2026)</h1>
<p class="sub">Analisi retrospettiva di TUTTE le partite del weekend su Serie A, Premier League, LaLiga, Bundesliga e Ligue 1:
ogni pronostico era stato fatto prima del fischio d'inizio (niente dati del futuro). Stime con incertezza, mai certezze; le sconfitte sono pubblicate.</p>
<div class="warn">⚠️ <b>18+</b> · Solo operatori con <b>licenza ADM</b> · Gioca responsabilmente · <b>autoesclusione.it</b> · Numero Verde 800 558822</div>
</div>
{body}
{footer("archivio")}
</div></body></html>"""
    with open(os.path.join(SITE, "report-weekend.html"), "w") as f:
        f.write(wrap_tables(html))


SW_JS = """const C='predictor-v2';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const r=e.request;
  if(r.mode==='navigate'){
    e.respondWith(fetch(r).then(res=>{if(res&&res.ok){const cp=res.clone();caches.open(C).then(c=>c.put(r,cp));}return res;}).catch(()=>caches.match(r).then(m=>m||caches.match('index.html'))));
  }else{
    e.respondWith(caches.match(r).then(h=>h||fetch(r).then(res=>{if(res&&res.ok){const cp=res.clone();caches.open(C).then(c=>c.put(r,cp));}return res;})));
  }
});
"""


def main():
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "sw.js"), "w", encoding="utf-8") as f:
        f.write(SW_JS)  # network-first per le pagine: mai data stantia; v2 invalida la cache v1
    for fp in sorted(glob.glob(os.path.join(DATA, 'forecast_giornata*.csv')), key=gj_num):
        build_giocata(gj_num(fp))
    build_index()
    build_metodo()
    build_glossario()
    build_multi()
    build_altre()
    build_coppe()
    build_giocata_multi()
    build_archivio()
    build_benchmark()
    build_guida()
    build_report_weekend()
    nq = 0
    for bp in bestprice_files():
        build_quote(bp)
        nq += 1
    n = 0
    for rp in glob.glob(os.path.join(ROOT, "report_giornata*.html")):
        dst = os.path.join(SITE, os.path.basename(rp))
        shutil.copy(rp, dst)
        # 🛠 09/11 report storici: aggiungi link home + legale se manca il tabbar
        t = open(dst, encoding="utf-8").read()
        if 'class="tabbar"' not in t and "</body>" in t:
            t = t.replace("</body>", '<p style="text-align:center;font-size:12px;color:#94a3b8;padding:12px">⬅ <a href="index.html" style="color:#60a5fa">Home</a> · ⚠️ 18+ · ADM · autoesclusione.it · 800 558822</p></body>')
            open(dst, "w", encoding="utf-8").write(t)
        n += 1
    print(f" sito generato in {SITE}: index, metodo, glossario, top5, europa(coppe), giocate, archivio, {nq} quote, {n} report")


if __name__ == "__main__":
    main()
