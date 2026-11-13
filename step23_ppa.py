#!/usr/bin/env python3
"""step23_ppa.py — pagina PPA (Pronostici Percentuale Alta): per ogni giorno della finestra,
i match con la percentuale modello più alta (>= --minp, default 55%), con quota ed EV.
Output: site/ppa.html. Uso: python3 src/step23_ppa.py [--minp 55]
"""
import argparse
import html
import datetime
import sys
from pathlib import Path

import pandas as pd
from make_site import footer  # 🛠 09/11 tabbar+legale condivisi

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minp", type=float, default=60.0)
    ap.add_argument("--topn", type=int, default=10)
    ap.add_argument("--hide-done", action="store_true", help="nasconde le partite già terminate")
    a = ap.parse_args()
    today = datetime.date.today().isoformat()

    # 🆕 08/11 esiti reali (eval_day) per marcare ✅/❌ le pick finite
    evday = {}
    ef = DATA / f"eval_day_{today}.csv"
    if ef.exists():
        for _, r in pd.read_csv(ef).iterrows():
            evday[(str(r["lega"]), str(r["partita"]))] = r

    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)  # 🛠 09/11 tutte le finestre
    od["data"] = od["data"].astype(str)
    od = od[od["data"] >= today]
    fo = pd.read_csv(DATA / "forecast_multi.csv")
    fo["giornata"] = fo["giornata"].astype(int)

    by_date = {}
    od["_hhmm"] = od["orario"].astype(str).str[-5:]
    for _, o in od.sort_values(["data", "_hhmm"]).iterrows():
        f = fo[(fo["lega"] == o["lega"]) & (fo["giornata"] == int(o["giornata"]))]
        f = f[f["partita"].str.lower().str.contains(str(o["home"]).split()[0].lower()[:6], na=False)]
        if len(f) == 0:
            continue
        r = f.iloc[0]
        p1, px, p2 = r["p1%"], r["pX%"], r["p2%"]
        pO, pGG = r["Over2.5%"], r["BTTS%"]
        dc1x = round(0.96 / (1 / o["best_1"] + 1 / o["best_X"]), 2) if pd.notna(o.get("best_1")) and pd.notna(o.get("best_X")) else None
        dcx2 = round(0.96 / (1 / o["best_X"] + 1 / o["best_2"]), 2) if pd.notna(o.get("best_X")) and pd.notna(o.get("best_2")) else None
        mkts = [("1", p1, o.get("best_1")), ("X", px, o.get("best_X")), ("2", p2, o.get("best_2")),
                ("O2.5", pO, o.get("best_O25")), ("U2.5", 100 - pO, o.get("best_U25")),
                ("GG", pGG, o.get("best_GG")), ("NG", 100 - pGG, o.get("best_NG")),
                ("DC 1X", p1 + px, dc1x), ("DC X2", px + p2, dcx2)]
        for label, p, q in mkts:
            if p < a.minp or q is None or pd.isna(q):
                continue
            ev = round((p / 100 * (q - 1) - (1 - p / 100)) * 100, 2)
            r7 = evday.get((o["lega"], o["partita"]))
            esito = ""
            if r7 is not None:
                reale = str(r7.get("reale", ""))
                if label in ("1", "X", "2"):
                    esito = "✅" if reale == label else f"❌ ({reale})"
                elif label == "DC 1X":
                    esito = "✅" if reale in ("1", "X") else f"❌ ({reale})"
                elif label == "DC X2":
                    esito = "✅" if reale in ("X", "2") else f"❌ ({reale})"
                elif label == "DC 12":
                    esito = "✅" if reale in ("1", "2") else f"❌ ({reale})"
                elif label in ("O2.5", "U2.5"):
                    ou = str(r7.get("ou_reale", ""))
                    want = "Over" if label == "O2.5" else "Under"
                    esito = "✅" if ou == want else f"❌ ({ou})"
            by_date.setdefault(o["data"], []).append({
                "ora": str(r["orario"])[-5:] if pd.notna(r.get("orario")) else str(o["orario"])[-5:], "lega": o["lega"], "partita": o["partita"],
                "pick": label, "p%": round(p, 1), "quota": round(float(q), 2), "EV%": ev,
                "esito": esito, "done": bool(esito),
                "motivo": str(r.get("motivo_verbale") or r.get("motivo") or ""),
                "perche": str(r.get("perche") or r.get("motivo_verbale") or "")})

    sections = []
    for d in sorted(by_date):
        rows = sorted(by_date[d], key=lambda x: (x["ora"], -x["p%"]))[: a.topn * 2]  # 🛠 08/11 ordina per orario di inizio
        # 🛠 08/11 no doppioni: se c'è una doppia chance (DC) del match, togli i singoli 1/X/2 dello stesso match
        dc_matches = {x["partita"] for x in rows if x["pick"].startswith("DC")}
        if dc_matches:
            rows = [x for x in rows if not (x["pick"] in ("1", "X", "2") and x["partita"] in dc_matches)]
        # 🛠 08/11 UNA sola pick per partita: tieni il mercato con p più alta
        best = {}
        for x in rows:
            k = x["partita"]
            if k not in best or x["p%"] > best[k]["p%"]:
                best[k] = x
        rows = sorted(best.values(), key=lambda x: (x["ora"], -x["p%"]))
        if a.hide_done:
            rows = [x for x in rows if not x["done"]]
        trs = ""
        for r in rows:
            ev_cls = "pos" if (r["EV%"] is not None and r["EV%"] > 0) else "neg"
            ev_txt = f'<span class="{ev_cls}">{r["EV%"]:+.1f}%</span>' if r["EV%"] is not None else "—"
            q_txt = f"{r['quota']:.2f}" if r["quota"] else "—"
            mot = html.escape(str(r.get("motivo") or ""))  # testo completo, senza taglio
            per = html.escape(str(r.get("perche") or ""))  # 🆕 13/11 frase breve "perché"
            es = f" <b>{r['esito']}</b>" if r.get("esito") else (" <b class='sub'>⏳ in verifica</b>" if o["data"] < today else "")
            trs += (f"<tr><td data-label='Ora'>{r['ora']}</td><td data-label='Lega'>{html.escape(r['lega'])}</td><td data-label='Partita'>{html.escape(r['partita'])}{es}</td>"
                    f"<td data-label='Mercato'><b>{r['pick']}</b></td><td data-label='p modello'><b>{r['p%']}%</b></td><td data-label='Quota'>{q_txt}</td><td data-label='EV'>{ev_txt}</td></tr>")
            trs += ((f"<tr class='motrow'><td colspan='7' class='perche'>{per}</td></tr>") if per else "")
            trs += (f"<tr class='motrow'><td colspan='7'><details><summary>💬 perché questo pick? (dettaglio)</summary>"
                    f"<div class='mot'>{mot}</div></details></td></tr>")
        is_past = d < today
        sec = f"""
    <h2 id="d-{d}">📅 {d} <span class='sub'>({len(rows)} picks, p ≥ {a.minp:.0f}%)</span></h2>
    <table><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>p modello</th><th>Quota</th><th>EV</th></tr>{trs}</table>"""
        if is_past:
            sections.append(f"<details><summary><b>📅 {d}</b> <span class='sub'>({len(rows)} picks — giorno passato)</span></summary>{sec}</details>")
        else:
            sections.append(sec)

    page = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>⚡ PPA — Pronostici Percentuale Alta</title><style>
:root{{--bg:#0b1220;--card:#111c33;--txt:#e2e8f0;--sub:#94a3b8;--acc:#2563eb;--pos:#4ade80;--neg:#f87171}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}}
header{{padding:12px 14px;border-bottom:1px solid #1e293b}}nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:#16233d}}nav a.on{{background:var(--acc);color:#fff}}
main{{max-width:920px;margin:0 auto;padding:12px}}h2{{font-size:16px;margin:16px 0 8px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;font-size:13px;margin-bottom:14px}}
td,th{{padding:7px 9px;border-bottom:1px solid #1e293b;text-align:left}}th{{color:var(--sub);font-size:11px;text-transform:uppercase}}
.pos{{color:var(--pos);font-weight:700}}.neg{{color:var(--neg)}}.sub{{color:var(--sub);font-size:11px}} tr.motrow td{{padding:0 9px 8px 9px;background:#0e1830}} details{{font-size:12px;color:#94a3b8}} summary{{cursor:pointer;font-size:12px;color:#60a5fa;padding:2px 0}} .mot{{color:#cbd5e1;font-size:12.5px;line-height:1.45;padding:6px 0 2px 12px;border-left:2px solid #2563eb}}.perche{{color:#7dd3fc;font-weight:600;font-size:12.5px;background:rgba(56,189,248,.08)}}
details{{margin:0 0 8px;background:var(--card);border-radius:10px;padding:6px 10px}} details summary{{cursor:pointer;font-size:14px}} .warn{{background:#3b0d0d;border:1px solid #dc2626;border-radius:10px;padding:10px 12px;font-size:13px;margin:10px 0}}
@media (max-width:720px){{
main{{padding:8px}} table{{display:block}} table tr th{{display:none}}
table tr{{display:block;border:1px solid #1e293b;border-radius:10px;margin:0 0 10px;padding:6px 9px;background:var(--card)}}
table td{{display:flex;justify-content:space-between;gap:10px;border:0;padding:3px 2px;font-size:12.5px;text-align:right}}
table td::before{{content:attr(data-label);color:var(--sub);font-size:10px;text-transform:uppercase}}
tr.motrow td{{display:block;text-align:left}} tr.motrow td::before{{content:none}}
}}</style></head><body>
<header><b>⚡ PPA — Pronostici Percentuale Alta</b> <span class="sub">— dal {today}, p modello ≥ {a.minp:.0f}%</span></header>
<nav><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a><a href="giocata_multi.html">Giocate EV</a><a class="on" href="ppa.html">⚡ PPA</a><a href="surebets.html">⚖️ Surebets</a><a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a href="glossario.html">Glossario</a></nav>
<main>
<p class="sub" style="margin:4px 0 8px">📆 Giorni: {''.join(f"<a href='#d-{d}' style='margin-right:8px;color:#60a5fa'>{d[8:]}/{d[5:7]}</a>" for d in sorted(by_date))}</p>
<div class="warn">⚠️ <b>Percentuale alta ≠ vittoria certa.</b> La colonna EV dice se il prezzo vale la probabilità: senza EV>0 non c'è edge. Queste sono <b>stime con incertezza</b>, mai certezze. 18+ · ADM · autoesclusione.it · 800 558822</div>
{''.join(sections) if sections else '<p>Nessun match sopra la soglia oggi.</p>'}
</main>{footer("ppa")}</body></html>"""
    SITE.mkdir(exist_ok=True)
    (SITE / "ppa.html").write_text(page, encoding="utf-8")
    n = sum(len(v) for v in by_date.values())
    print(f"⚡ site/ppa.html: {n} pronostici PPA (p≥{a.minp:.0f}%) su {len(by_date)} giorni")


if __name__ == "__main__":
    main()
