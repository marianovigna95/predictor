#!/usr/bin/env python3
"""step27_schedina.py — 🧾 Schedina del giorno (stampabile + PDF).

Legge data/giocata_multi.csv, prende la SINGOLA + il RADDOPPIO del giorno con EV>+2%
(stake solo EV>+2% — regola del sito), calcola lo stake ¼ Kelly e genera:
  - site/schedina.html          (pagina web, stile scontrino, @media print)
  - site/schedina_YYYY-MM-DD.pdf (PDF via fpdf2)

Uso: python3 src/step27_schedina.py [--date 2026-11-12]
"""
import argparse
import csv
import datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

FOOTER = "⚠️ Solo analisi, mai certezze · 18+ · puntare SOLO su ADM · autoesclusione.it · 800 558822"
NAV = ('<nav><button id="themeBtn" title="tema chiaro/scuro" style="background:none;border:1px solid var(--line,#22345a);color:inherit;border-radius:8px;padding:3px 8px;cursor:pointer">☀️</button><a href="index.html" onclick="if(history.length>1){history.back();return false;}" aria-label="torna indietro" title="indietro">‹</a><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a>'
       '<a href="multi-lega.html">Multi-lega</a><a href="coppe.html">Coppe</a>'
       '<a href="giocata_multi.html">Giocate</a><a href="ppa.html">⚡ PPA</a>'
       '<a href="surebets.html">⚖️ Surebets</a><a class="on" href="schedina.html">🧾 Schedina</a>'
       '<a href="bankroll.html">💰 Bankroll</a><a href="archivio.html">Archivio+CLV</a>'
       '<a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a></nav>')


def kelly_quarter(p, o, n_eff=50):
    """🆕 13/11 ¼ Kelly con incertezza: p_low = p - sqrt(p(1-p)/n_eff) (IC ~68%), poi f*=(p_low*O-1)/(O-1), stake=f*/4."""
    import math
    se = math.sqrt(max(p*(1-p), 1e-9) / n_eff)
    pl = max(0.0, p - se)
    f = (pl * o - 1.0) / (o - 1.0) if o > 1.0 else 0.0
    return max(0.0, f) / 4.0


def load_day(date_str, min_ev=2.0):
    f = DATA / "giocata_multi.csv"
    out = []
    if not f.exists():
        return out
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("data") != date_str:
                continue
            try:
                ev = float(r.get("EV%") or 0)
            except Exception:
                ev = 0.0
            if ev > min_ev:  # stake solo EV>+2%
                out.append(r | {"ev": ev})
    out.sort(key=lambda r: (0 if r.get("tipo", "").upper().startswith("SINGOLA") else 1, -r["ev"]))
    return out


CSS = """
body{background:#0b1220;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0}
.wrap{max-width:640px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:8px 0}
.sub{color:#8ea3c8;font-size:12px}
.card{background:#101b33;border:1px solid #22345a;border-radius:10px;padding:12px 14px;margin:10px 0}
.card .top{display:flex;justify-content:space-between;align-items:baseline}
.badge{background:#7f1d1d;color:#fecaca;font-size:11px;font-weight:700;border-radius:6px;padding:2px 8px}
.pick{font-size:17px;font-weight:700;color:#fff;margin:6px 0 2px}
.meta{color:#8ea3c8;font-size:12px;line-height:1.5}
.kelly{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}
.k{flex:1;background:#0b1220;border:1px solid #22345a;border-radius:8px;padding:8px;text-align:center}
.k b{display:block;font-size:15px;color:#93c5fd}
.k span{font-size:10px;color:#8ea3c8;text-transform:uppercase;letter-spacing:.05em}
.perche{color:#7dd3fc;font-size:12.5px;font-weight:600;margin-top:6px;background:rgba(56,189,248,.08);border-radius:6px;padding:6px 8px}
.empty{color:#8ea3c8;padding:20px;text-align:center}
footer{color:#475569;font-size:11px;text-align:center;padding:14px}
@media print{body{background:#fff;color:#000}.card{background:#fff;border:1px solid #ccc}
nav,footer .no{display:none}.sub,.meta{color:#333}k b{color:#000}.k{background:#fff;border-color:#ccc}}
"""


def page_html(date_str, rows):
    cards = []
    for r in rows:
        p = float(r.get("p_modello%", 0) or 0) / 100.0
        q = float(r.get("quota_best", 0) or 0)
        k = kelly_quarter(p, q) if q > 1 else 0.0
        _st = r.get("stake%") if hasattr(r, "get") else None
        if _st not in (None, "", "nan") and str(_st).replace(".","",1).isdigit():
            k = float(_st) / 100.0  # 🆕 13/11 stake con incertezza (Brier) da weekly_multi
        stake100 = round(k, 2)  # % bankroll
        win100 = round(stake100 * (float(q) - 1), 2) if q else 0
        cards.append(f"""<div class="card">
  <div class="top"><b>{r.get('tipo','')}</b><span class="badge">EV +{float(r.get('ev',0) or 0):.1f}%</span></div>
  <div class="pick">{r.get('partita','')}</div>
  <div class="meta">🏆 {r.get('lega','')} · 🕐 {r.get('data','')} · mercato: <b>{r.get('mercato','')}</b> — esito <b>{r.get('esito','')}</b></div>
  {"<div class='perche'>"+r.get('perche','').replace('<','&lt;')+"</div>" if r.get('perche') else ""}
  <div class="kelly">
    <div class="k"><b>{q}</b><span>quota best-price</span></div>
    <div class="k"><b>{p}%</b><span>p modello</span></div>
    <div class="k"><b>{stake100}%</b><span>stake ¼ Kelly</span></div>
    <div class="k"><b>+{win100}%</b><span>vincita se entra (su bankroll)</span></div>
  </div>
  <div class="sub" style="font-size:10.5px;opacity:.75;margin-top:6px">Quota best-price = la migliore disponibile tra gli operatori ADM. Non è una quota negoziata né garantita: verifica sempre sul sito dell'operatore prima di giocare.</div>
</div>""")
    body = "".join(cards) if cards else '<p class="empty">Oggi nessuna schedina: nessuna giocata con EV &gt; +2% (regola del sito: stake 0).</p>'
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🧾 Schedina {date_str} — Predictor</title><style>{CSS}[data-theme="light"] body{{filter:invert(1) hue-rotate(180deg)}}
</style></head><body>
<div class="wrap">
<h1>🧾 Schedina del giorno — {date_str}</h1>
<p class="sub">Max 1 SINGOLA + 1 RADDOPPIO · stake solo se EV &gt; +2% · ¼ Kelly · puntare SOLO su ADM · modello walk-forward (nessuna certezza)</p>
{NAV}
{body}
<p class="sub">Stampa o salva PDF: Ctrl+P → Salva come PDF · <a href="#" id="share" style="color:#93c5fd">🔗 condividi schedina</a></p>
<script>
document.getElementById('share').addEventListener('click',function(e){{e.preventDefault();
  var url=location.origin+location.pathname;
  if(navigator.share){{navigator.share({{title:'Schedina',url:url}}).catch(function(){{}});}}
  else if(navigator.clipboard){{navigator.clipboard.writeText(url).then(function(){{alert('Link copiato');}});}}
}});
</script>
</div>
<footer>{FOOTER}</footer>
<script>
(function(){{var b=document.getElementById('themeBtn');if(!b)return;
function set(t){{document.documentElement.setAttribute('data-theme',t);try{{localStorage.setItem('theme',t);}}catch(e){{}}b.textContent=t==='light'?'🌙':'☀️';}}
var t='dark';try{{t=localStorage.getItem('theme')||'dark';}}catch(e){{}}
set(t);b.onclick=function(){{set(document.documentElement.getAttribute('data-theme')==='light'?'dark':'light');}};}})();
</script>
</body></html>"""


def make_pdf(date_str, rows, path):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, f"Schedina del giorno - {date_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.multi_cell(0, 5, "Max 1 SINGOLA + 1 RADDOPPIO. Stake solo EV>+2% (1/4 Kelly). Puntare SOLO su ADM. Solo analisi, mai certezze. 18+ - autoesclusione.it - 800 558822")
    pdf.ln(4)
    if not rows:
        pdf.set_font("helvetica", "", 12)
        pdf.multi_cell(0, 7, "Oggi nessuna schedina: nessuna giocata con EV > +2% (stake 0).")
    for r in rows:
        p, q = float(r.get("p_modello%", 0) or 0) / 100.0, float(r.get("quota_best", 0) or 0)
        _ev = float(r.get("ev", 0) or 0)
        k = (kelly_quarter(p, q) if q > 1 else 0.0) if _ev > 2.0 else 0.0   # 🆕 13/11-b solo EV>+2%
        _st = r.get("stake%") if hasattr(r, "get") else None
        if _st not in (None, "", "nan") and str(_st).replace(".","",1).isdigit():
            k = float(_st) / 100.0  # 🆕 13/11 stake con incertezza (Brier) da weekly_multi
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 8, f"{r.get('tipo','')} — EV +{float(r.get('ev',0) or 0):.1f}%", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 11)
        pdf.multi_cell(0, 6, f"{r.get('partita','')}  ({r.get('lega','')})")
        pdf.multi_cell(0, 6, f"Mercato: {r.get('mercato','')}  |  Esito: {r.get('esito','')}  |  Quota best-price: {q}  |  p modello: {p}%")
        pdf.multi_cell(0, 6, f"Stake consigliato: {k:.2f}% del bankroll (1/4 Kelly)")
        pdf.ln(3)
    pdf.output(str(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    rows = load_day(a.date)
    (SITE / "schedina.html").write_text(page_html(a.date, rows), encoding="utf-8")
    try:
        make_pdf(a.date, rows, SITE / f"schedina_{a.date}.pdf")
        pdf_note = f" + PDF schedina_{a.date}.pdf"
    except Exception as e:
        pdf_note = f" (PDF saltato: {e})"
    print(f"🧾 site/schedina.html: {len(rows)} giocate EV>+2% per {a.date}{pdf_note}")


if __name__ == "__main__":
    main()
