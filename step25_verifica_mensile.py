#!/usr/bin/env python3
"""step25_verifica_mensile.py — pagina verifica MENSILE: aggrega data/eval_day_*.csv per mese
(acc, RPS modello vs mercato, per lega) → site/verifica.html
Uso: python3 src/step25_verifica_mensile.py
"""
import datetime
import glob
import html
import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


def main():
    files = sorted(glob.glob(str(DATA / "eval_day_*.csv")))
    rows = []
    for f in files:
        d = re.search(r"eval_day_(\d{4}-\d{2}-\d{2})", f).group(1)
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        for _, r in df.iterrows():
            rows.append({"data": d, "mese": d[:7], "lega": r.get("lega", ""), "partita": r.get("partita", ""),
                         "pronostico": r.get("pronostico"), "reale": r.get("reale"), "hit": r.get("hit"),
                         "rps_mod": r.get("rps_mod"), "rps_mkt": r.get("rps_mkt")})
    if not rows:
        print("⚠️ nessun eval_day trovato")
        return
    ev = pd.DataFrame(rows)
    ev["hit"] = pd.to_numeric(ev["hit"], errors="coerce")
    ev["rps_mod"] = pd.to_numeric(ev["rps_mod"], errors="coerce")
    ev["rps_mkt"] = pd.to_numeric(ev["rps_mkt"], errors="coerce")

    meses = []
    for m, g in ev.groupby("mese"):
        per_lega = "".join(
            f"<tr><td>{lg}</td><td>{len(gg)}</td><td>{gg.hit.mean()*100:.0f}%</td>"
            f"<td>{gg.rps_mod.mean():.4f}</td><td>{gg.rps_mkt.mean():.4f}</td></tr>"
            for lg, gg in g.groupby("lega") if len(gg) >= 3)
        meses.append(f"""
<h2>📅 {m}</h2>
<table><tr><th>Totale</th><th>Partite</th><th>Acc 1X2</th><th>RPS modello</th><th>RPS mercato</th></tr>
<tr><td><b>{m}</b></td><td>{len(g)}</td><td><b>{g.hit.mean()*100:.1f}%</b></td>
<td>{g.rps_mod.mean():.4f}</td><td>{g.rps_mkt.mean():.4f}</td></tr></table>
{('<h3>Per lega (≥3 partite)</h3><table><tr><th>Lega</th><th>n</th><th>Acc</th><th>RPS mod</th><th>RPS mkt</th></tr>' + per_lega + '</table>') if per_lega else ''}""")

    page = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>📅 Verifica mensile — Predictor</title><style>
:root{{--bg:#0b1220;--card:#111c33;--txt:#e2e8f0;--sub:#94a3b8;--acc:#2563eb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}}
header{{padding:12px 14px;border-bottom:1px solid #1e293b}}nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:#16233d}}nav a.on{{background:var(--acc);color:#fff}}
main{{max-width:900px;margin:0 auto;padding:12px}}h2{{font-size:17px;margin:18px 0 8px}}h3{{font-size:14px;margin:12px 0 6px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;font-size:13px;margin-bottom:12px}}
td,th{{padding:7px 9px;border-bottom:1px solid #1e293b;text-align:left}}th{{color:var(--sub);font-size:11px;text-transform:uppercase}}
.warn{{background:#3b0d0d;border:1px solid #dc2626;border-radius:10px;padding:10px 12px;font-size:13px;margin:10px 0}}
@media (max-width:720px){{table{{display:block}}thead,tr th{{display:none}}tr{{display:block;border:1px solid #1e293b;border-radius:10px;margin-bottom:10px;padding:6px 9px}}td{{display:flex;justify-content:space-between;border:0;padding:3px 2px}}td::before{{content:attr(data-label);color:var(--sub);font-size:10px;text-transform:uppercase}}}}
</style></head><body>
<header><b>📅 Verifica mensile</b> <span style="color:var(--sub)">— pronostici vs esiti reali, da eval_day giornaliera</span></header>
<nav><a href="index.html">Home</a><a href="archivio.html">Archivio+CLV</a><a class="on" href="verifica.html">📅 Verifica</a><a href="ppa.html">⚡ PPA</a><a href="surebets.html">⚖️ Surebets</a><a href="metodo.html">Metodo</a></nav>
<main>
<div class="warn">⚠️ Statistiche passate = <b>stime con incertezza</b>, mai garanzia di risultati futuri. 18+ · ADM · autoesclusione.it · 800 558822</div>
{''.join(meses)}
</main></body></html>"""
    SITE.mkdir(exist_ok=True)
    (SITE / "verifica.html").write_text(page, encoding="utf-8")
    print(f"📅 site/verifica.html: {len(ev)} match verificati, {ev['mese'].nunique()} mesi")


if __name__ == "__main__":
    main()
