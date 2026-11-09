"""
Genera un report HTML auto-contenuto (stile inline, no risorse esterne) per una giornata.
Uso:  python3 src/make_report.py --giornata 10   ->  report_giornata10.html
Su mobile (<640px) la tabella diventa una pila di card (una per partita) con etichette.
"""
import argparse
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def st(label, valore):
    """Statistica impilata in colonna: etichetta sopra (piccola), valore sotto (grande)."""
    return f'<span class="stl">{label}</span><span class="stv">{valore}</span>'

VERDICTS = {  # verdict dell'analista (fase 4) per le partite chiave
    "Lecce - Genoa": ("X2 (doppia chance)", "bassa", "Modello 1 (40%) vs mercato 2 (2.40): entrambe le squadre con assenze pesanti (Geubbels, Gaspar, Ilic out dal Lecce). Meglio la doppia chance."),
    "Juventus - Napoli": ("1", "media-bassa", "Modello 43% e mercato d'accordo (2.20). Ma Juve in crisi (Yildiz, Locatelli out) e Napoli senza 6 titolari + Allegri squalificato: partita bloccata, Under 2.5 57%."),
    "Sassuolo - Fiorentina": ("1X", "bassa", "Modello 1 (44%) vs mercato 2 (2.35). Thorstvedt squalificato per il Sassuolo. GG 61%: partita da gol."),
    "Atalanta - Parma": ("1", "ALTA", "Modello 62% = mercato (1.53). Unico forte accordo. Parma peggior attacco del campionato. Risultato atteso 2-0."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giornata", type=int, required=True)
    args = ap.parse_args()
    md = args.giornata

    fc = pd.read_csv(DATA / f"forecast_giornata{md}.csv")
    mk = pd.read_csv(DATA / f"markets_giornata{md}.csv")
    df = fc.merge(mk, on="partita", how="left")

    cards_html = ""
    for _, r in df.iterrows():
        part = r["partita"]
        oggi = "OGGI 01/11" if str(r["orario"]).startswith("01/11") else "domani 02/11"
        v = VERDICTS.get(part, (str(r["pronostico"]), "—", ""))
        edge = r.get("edge_vs_mercato", "")
        flag = " 🚨" if str(r.get("⚠️", "")).strip() == "🚨" else ""
        conf_class = {"ALTA": "alta", "alta": "alta", "media-bassa": "media", "bassa": "bassa"}.get(v[1], "media")
        motivo = str(r.get("motivo_verbale") or r.get("motivo") or "—").replace("<", "&lt;")
        motivo_num = str(r.get("motivo") or "").replace("<", "&lt;")
        marcatori = str(r.get("marcatori") or "—").replace("<", "&lt;")
        nota = str(v[2]).replace("<", "&lt;")
        if nota and v[0][:1] != str(r["pronostico"]):
            note_html = (f'<div class="mc-note">⚠️ <b>Verdict diverso dal modello</b> '
                         f'(modello: {r["pronostico"]} → verdict: {v[0]}, conf. {v[1]}): {nota}</div>')
        elif nota:
            note_html = f'<div class="mc-sub">📝 Nota analista: {nota}</div>'
        else:
            note_html = ''
        cards_html += f"""
<div class="mc">
  <div class="mc-h">{part} <span class="when">{oggi} · {r['orario']}</span></div>
  <div class="mc-row">
    <div class="ms"><span class="stl">Pron. modello</span><span class="stv">{r['pronostico']}</span></div>
    <div class="ms"><span class="stl">Confidenza</span><span class="stv">{r['conf%']}%</span></div>
    <div class="ms"><span class="stl">1X2</span><span class="stv">1&nbsp;{r['p1%']}%</span><span class="stv">X&nbsp;{r['pX%']}%</span><span class="stv">2&nbsp;{r['p2%']}%</span></div>
    <div class="ms"><span class="stl">GG / NG</span><span class="stv">{r['GG%']}% / {r['NG%']}%</span></div>
    <div class="ms"><span class="stl">Over 2.5</span><span class="stv">{r['O2.5 gol%']}%</span></div>
    <div class="ms"><span class="stl">Under 2.5</span><span class="stv">{r['U2.5 gol%']}%</span></div>
    <div class="ms"><span class="stl">TiP O5.5</span><span class="stv">{r['TiP tot O5.5%']}%</span></div>
    <div class="ms"><span class="stl">Cart. O4.5</span><span class="stv">{r['cart O4.5%']}%</span></div>
    <div class="ms"><span class="stl">Punteggio esatto+prob</span><span class="stv">{r['risultato+prob%']}</span></div>
    <div class="ms"><span class="stl">Edge vs quote</span><span class="stv">{edge}{flag}</span></div>
    <div class="ms"><span class="stl">Verdict analista</span><span class="stv verdict v-{conf_class}">{v[0]}</span></div>
    <div class="ms"><span class="stl">Conf. verdict</span><span class="stv">{v[1]}</span></div>
    <div class="ms wide"><span class="stl">Marcatore</span><span class="stv" style="font-weight:400;font-size:11px">{marcatori}</span></div>
  </div>
  {note_html}
  <div class="mc-mot">🔍 <b>Motivo (in parole):</b> {motivo}
    <details style="margin-top:4px;color:#64748b"><summary style="cursor:pointer;font-size:10px">dati numerici del motivo</summary><span style="font-size:10px">{motivo_num}</span></details>
  </div>
  <div class="mc-sub hide-m">📝 Nota analista: {v[2]}</div>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report Giornata {md} — Serie A 2026/27</title>
<style>
 body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
 .card {{ max-width:1200px; margin:auto; background:#1e293b; border-radius:14px; padding:24px; box-shadow:0 8px 30px rgba(0,0,0,.4); }}
 h1 {{ font-size:22px; margin:0 0 4px; }} h1 .g {{ color:#38bdf8; }}
 .sub {{ color:#94a3b8; font-size:13px; margin-bottom:18px; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th {{ text-align:left; color:#38bdf8; border-bottom:2px solid #334155; padding:8px 6px; font-size:12px; text-transform:uppercase; }}
 td {{ border-bottom:1px solid #334155; padding:10px 6px; vertical-align:top; }}
 tr:hover {{ background:#273449; }}
 .when {{ color:#fbbf24; font-size:11px; }}
 .muted {{ color:#94a3b8; font-size:11px; display:block; margin-top:4px; }}
 .small {{ font-size:11px; }}
 /* statistiche impilate dritte in colonna: etichetta sopra, valore sotto */
 .stl {{ display:block; font-size:9px; color:#38bdf8; text-transform:uppercase; letter-spacing:.4px; margin-top:4px; }}
 .stv {{ display:block; font-size:14px; font-weight:700; color:#e2e8f0; }}
 tr.mrow td {{ background:#0f172a; color:#94a3b8; font-size:11px; line-height:1.5; border-bottom:2px solid #38bdf8; }}
 tr.mrow:hover td {{ background:#0f172a; }}
 /* SCHEDA PARTITA: titolo in alto, categorie in colonne ORIZZONTALI */
 .mc-grid {{ display:grid; gap:12px; grid-template-columns:1fr; }}
 @media (min-width:1000px) {{ .mc-grid {{ grid-template-columns:1fr 1fr; }} }}
 .mc {{ background:#0f172a; border:1px solid #334155; border-radius:12px; padding:12px 14px; }}
 .mc-h {{ font-size:15px; font-weight:700; margin-bottom:8px; }}
 .mc-row {{ display:flex; flex-wrap:wrap; gap:8px 22px; }}
 .ms {{ display:flex; flex-direction:column; min-width:58px; }}
 .ms.wide {{ max-width:230px; }}
 .ms .stv {{ font-size:13px; }}
 .mc-mot {{ margin-top:9px; padding-top:7px; border-top:1px dashed #334155; font-size:11px; color:#94a3b8; line-height:1.55; }}
 .mc-sub {{ margin-top:6px; font-size:11px; color:#94a3b8; line-height:1.5; }}
 .mc-note {{ margin-top:8px; background:rgba(69,10,10,.35); border:1px solid #7f1d1d; border-radius:8px; padding:7px 9px; font-size:11px; color:#fecaca; line-height:1.5; }}
 .verdict {{ font-weight:700; }} .v-alta {{ color:#4ade80; }} .v-media {{ color:#fbbf24; }} .v-bassa {{ color:#f87171; }}
 .warn {{ background:#450a0a; border:1px solid #7f1d1d; border-radius:10px; padding:12px; margin-top:18px; font-size:12px; color:#fecaca; }}
 .foot {{ margin-top:14px; font-size:11px; color:#64748b; }}
 .tablewrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
 /* MOBILE: la tabella diventa una pila di card, una per partita */
 @media (max-width:640px){{
   body{{padding:10px}} .card{{padding:14px}} h1{{font-size:18px}} .sub{{font-size:12px}}
   .tablewrap{{overflow-x:visible}}
   table{{font-size:12px}}
   table tr:first-child{{display:none}}
   table, tbody, tr, td{{display:block; width:100%}}
   tr{{background:#0f172a; border:1px solid #334155; border-radius:10px; margin-bottom:12px; padding:6px 10px}}
   tr:hover{{background:#0f172a}}
   td{{border:none; padding:3px 6px; white-space:normal}}
   td::before{{content:attr(data-label) ": "; color:#38bdf8; font-size:10px; font-weight:700; text-transform:uppercase}}
   tr.mrow{{background:#0f172a; border:none; border-top:1px dashed #334155; border-radius:0; margin-top:-12px; padding:2px 10px 8px}}
   .hide-m{{display:none}}
 }}
</style></head><body><div class="card">
<h1>⚽ Report <span class="g">Giornata {md}</span> — Serie A 2026/27</h1>
<div class="sub">Modello v4 (xG reali Understat + Elo/Dixon-Coles + motivation + congestione + assenze a xG + quote) · generato il 01/11/2026 · stime con incertezza, mai certezze</div>
<p class="sub" style="font-size:11px">ℹ️ <b>Come si legge:</b> <b>Pronostico</b> = esito 1X2 più probabile (somma di tutti i punteggi con quell'esito, es. "1" = 1-0 + 2-0 + 2-1 + 3-1...). <b>Punteggio esatto+prob</b> = il singolo punteggio più frequente (qui 1-1 13%): può essere un pareggio anche quando il pronostico è "1", perché la vittoria casa si spartisce su tanti punteggi diversi.</p>
<div class="mc-grid">{cards_html}</div>
<div class="warn">⚠️ Queste sono <b>stime probabilistiche</b> basate su dati pubblici e news: non sono certezze né consigli di gioco. Gioco responsabile: <b>18+</b>, solo operatori <b>ADM</b> autorizzati — <b>autoesclusione.it</b> · Numero Verde <b>800 558822</b> in caso di difficoltà.</div>
<div class="foot">Fonte dati: football-data.co.uk · understat.com (API getLeagueData) · fotmob.com · quote da screenshot/oddsportal. File: data/forecast_giornata{md}.csv, data/markets_giornata{md}.csv — progetto football-predictor.</div>
</div></body></html>"""

    out = Path(__file__).resolve().parent.parent / f"report_giornata{md}.html"
    out.write_text(html, encoding="utf-8")
    print(f"💾 Report salvato: {out}")


if __name__ == "__main__":
    main()
