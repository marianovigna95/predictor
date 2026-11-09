#!/usr/bin/env python3
"""step11_template.py — stampa il template clv_manuale.csv per le giocate della finestra corrente.
L'utente compila solo la colonna quota_chiusura (da oddsportal/Pinnacle, pagina partita → closing odds).
Uso: python3 src/step11_template.py [--data 2026-11-06]
"""
import argparse, glob, os, re
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

ap = argparse.ArgumentParser()
ap.add_argument("--data", default=None)
a = ap.parse_args()
g = pd.read_csv(os.path.join(DATA, "giocata_multi.csv"))
if a.data:
    g = g[g["data"].astype(str).str.startswith(a.data)]
rows = []
for _, r in g.iterrows():
    for part, tag in re.findall(r"(.+?) \[([^\]]+)\]", str(r["partita"])) or []:
        part = part.strip().lstrip("+").strip()
        mkt = tag.split()[0]
        if mkt in ("1X2", "O2.5", "U2.5", "GG", "NG"):
            rows.append({"data": r["data"], "partita": part, "mercato": mkt, "quota_chiusura": ""})
    if "[" not in str(r["partita"]):
        rows.append({"data": r["data"], "partita": str(r["partita"]).strip(), "mercato": r["mercato"], "quota_chiusura": ""})
out = pd.DataFrame(rows).drop_duplicates(subset=["data", "partita", "mercato"])
print("# incolla queste righe in data/clv_manuale.csv e riempi quota_chiusura:")
print(out.to_csv(index=False))
