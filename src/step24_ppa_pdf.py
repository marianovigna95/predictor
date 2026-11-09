#!/usr/bin/env python3
"""step24_ppa_pdf.py — PDF stampabile della sezione PPA (tutti i mercati, p>=soglia, motivi completi).
Uso: python3 src/step24_ppa_pdf.py [--minp 55] [--out sito/ppa_2026-11-08.pdf]
"""
import argparse
import datetime
from pathlib import Path

import pandas as pd
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def clean(t):
    return (str(t).replace("«", '"').replace("»", '"').replace("’", "'").replace("‘", "'")
            .replace("–", "-").replace("—", "-").replace("…", "..."))


class PDF(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("helvetica", "I", 7)
        self.set_text_color(120)
        self.cell(0, 5, clean("18+ | Gioca responsabilmente | ADM | autoesclusione.it | 800 558822  —  "
                             f"Pagina {self.page_no()}/{{nb}}"), align="C")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minp", type=float, default=60.0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    today = datetime.date.today().isoformat()
    out = a.out or f"{ROOT.parent}/sito/ppa_{today}.pdf"

    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)  # 🛠 09/11 tutte le finestre; od["data"] = od["data"].astype(str)
    od = od[od["data"] >= today]
    fo = pd.read_csv(DATA / "forecast_multi.csv"); fo["giornata"] = fo["giornata"].astype(int)

    by_date = {}
    for _, o in od.sort_values(["data", "orario"]).iterrows():
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
            by_date.setdefault(o["data"], []).append({
                "ora": str(o["orario"])[-5:], "lega": o["lega"], "partita": o["partita"],
                "pick": label, "p": round(p, 1), "quota": round(float(q), 2), "ev": ev,
                "motivo": str(r.get("motivo_verbale") or r.get("motivo") or "")})

    pdf = PDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 9, clean(f"PPA - Pronostici Percentuale Alta  ({today})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(90)
    pdf.multi_cell(0, 5, clean(
        f"Tutti i mercati con probabilita' modello >= {a.minp:.0f}%, ordinati per %. "
        "EV>0 = il prezzo vale la probabilita' (edge). Percentuale alta NON e' una certezza: sono stime con incertezza. "
        "Analisi statistica a solo scopo informativo."))
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(180, 30, 30)
    pdf.cell(0, 6, clean("18+ | Gioca responsabilmente | ADM | autoesclusione.it | 800 558822"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    tot = 0
    for d in sorted(by_date):
        rows = sorted(by_date[d], key=lambda x: (x["ora"], -x["p"]))  # 🛠 08/11 ordina per orario di inizio
        dc_matches = {x["partita"] for x in rows if x["pick"].startswith("DC")}
        if dc_matches:
            rows = [x for x in rows if not (x["pick"] in ("1", "X", "2") and x["partita"] in dc_matches)]
        best = {}
        for x in rows:
            k = x["partita"]
            if k not in best or x["p"] > best[k]["p"]:
                best[k] = x
        rows = sorted(best.values(), key=lambda x: (x["ora"], -x["p"]))
        tot += len(rows)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(20, 40, 90)
        pdf.cell(0, 8, clean(f"{d}  ({len(rows)} picks)"), new_x="LMARGIN", new_y="NEXT")
        # header
        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(230, 236, 250)
        pdf.set_text_color(30)
        for w, h in zip([14, 30, 78, 18, 18, 18, 20], ["Ora", "Lega", "Partita", "Mercato", "p%", "Quota", "EV"]):
            pdf.cell(w, 6, h, border=1, fill=True)
        pdf.ln()
        pdf.set_font("helvetica", "", 8)
        for r in rows:
            if pdf.get_y() > 182:
                pdf.add_page()
            pdf.set_text_color(20)
            pdf.cell(14, 5.2, r["ora"], border=1)
            pdf.cell(30, 5.5, clean(r["lega"])[:22], border=1)
            pdf.cell(78, 5.5, clean(r["partita"])[:52], border=1)
            pdf.cell(18, 5.5, r["pick"], border=1)
            pdf.set_font("helvetica", "B", 8)
            pdf.cell(18, 5.5, f"{r['p']}%", border=1)
            pdf.set_font("helvetica", "", 8)
            pdf.cell(18, 5.5, f"{r['quota']:.2f}", border=1)
            pdf.set_text_color(0, 140, 0) if r["ev"] > 0 else pdf.set_text_color(190, 30, 30)
            pdf.set_font("helvetica", "B", 8)
            pdf.cell(20, 5.5, f"{r['ev']:+.1f}%", border=1)
            pdf.ln()
            # motivo sotto la riga, a tutta larghezza, in piccolo
            if pdf.get_y() > 250:
                pdf.add_page()
            pdf.set_font("helvetica", "I", 6.5)
            pdf.set_text_color(100)
            pdf.multi_cell(0, 3.1, clean("perche': " + r["motivo"])[:240], )
            pdf.set_text_color(20)
    pdf.output(out)
    print(f"📄 PDF PPA: {out} — {tot} picks su {len(by_date)} giorni")


if __name__ == "__main__":
    main()
