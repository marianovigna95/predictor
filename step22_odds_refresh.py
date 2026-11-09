#!/usr/bin/env python3
"""step22_odds_refresh.py — aggiorna le quote best-price wincomparator per una data della finestra.
Uso: python3 src/step22_odds_refresh.py --date 2026-11-08 [--file data/odds_window_0611_bestprice.csv]
Rileggge ogni pagina match wincomparator (fonte) e ricalcola best_1/X/2, O/U 2.5, GG/NG.
"""
import argparse
import datetime
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
QRE = re.compile(r">(\d+\.\d{2})<")


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")


def seg_of(h, sec):
    i = h.find('id="' + sec + '"')
    if i < 0:
        return ""
    j = h.find('id="odds-', i + 10)
    return h[i:j if j > 0 else len(h)]


def book_rows(seg, n):
    """[(slug, [q1..qn])] dai blocchi bookmakers/<size>/<slug>.webp seguiti dalle quote >x.xx<"""
    out = []
    for pp in seg.split("bookmakers/")[1:]:
        mm = re.match(r"\d+x\d+/([a-z0-9-]+)\.webp", pp)
        if not mm:
            continue
        qs = QRE.findall(pp)
        if len(qs) >= n:
            out.append((mm.group(1), [float(x) for x in qs[:n]]))
    return out


def parse_match(h):
    res = seg_of(h, "odds-RESULT")
    f0 = res.find("Full Time Result")
    k = res.find("Double Chance", f0 + 10 if f0 > 0 else 10)
    res_ft = res[f0 if f0 > 0 else 0: k if k > 0 else len(res)]
    r12 = book_rows(res_ft, 3)
    # 🆕 09/11 doppie chance reali (blocco "Double Chance" dentro odds-RESULT)
    k2 = res.find("Double Chance")
    k3 = res.find('id="odds-', k2) if k2 > 0 else -1
    dc_seg = res[k2: k3 if k3 > 0 else len(res)] if k2 > 0 else ""
    rdc = book_rows(dc_seg, 3)

    ou = seg_of(h, "odds-UNDER_OVER")
    ou25 = ""
    occ = list(re.finditer(r'data-panel-key="UNDER_OVER_2_5"', ou))
    if occ:
        m = occ[-1]  # occorrenza del pannello contenuto (con la tabella)
        nxt = ou.find('data-panel-key="UNDER_OVER_', m.end())
        ou25 = ou[m.end(): nxt if nxt > 0 else len(ou)]
    rou = book_rows(ou25, 2)

    goal = seg_of(h, "odds-GOAL")
    b = goal.find("Both Teams To Score")
    e = goal.find("First Team To Score", b + 10) if b > 0 else -1
    btts_seg = goal[b:e if e > 0 else len(goal)] if b > 0 else goal
    rg = book_rows(btts_seg, 2)

    def best(i, rows):
        vals = [r[1][i] for r in rows]
        return round(max(vals), 2) if vals else float("nan")

    return {
        "best_1": best(0, r12), "best_X": best(1, r12), "best_2": best(2, r12),
        "best_O25": best(0, rou), "best_U25": best(1, rou),
        "best_GG": best(0, rg), "best_NG": best(1, rg),
        "best_DC1X": best(0, rdc), "best_DCX2": best(1, rdc), "best_DC12": best(2, rdc),
        "n_books": len(r12),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--file", default="odds_window_0611_bestprice.csv")
    a = ap.parse_args()
    f = DATA / a.file
    od = pd.read_csv(f)
    od["data"] = od["data"].astype(str)
    sub = od[od["data"] == a.date]
    print(f"🔄 refresh {len(sub)} match del {a.date} da wincomparator…")
    n_ok = 0
    for idx, r in sub.iterrows():
        m = re.search(r"([a-z0-9-]+-\d+)/", str(r.get("fonte", "")))
        if not m:
            continue
        url = "https://www.wincomparator.com/predictions/" + m.group(1) + "/"
        try:
            b = None
            for _ in range(3):  # retry: a volte la pagina arriva senza tabella quote
                h = fetch(url)
                b = parse_match(h)
                if b["n_books"] >= 3:
                    break
                time.sleep(1.0)
            if b is None or b["n_books"] == 0:
                print(f"  ⚠️ {r['partita']}: nessun book parsato")
                continue
            for k2, v in b.items():
                if k2 != "n_books":
                    od.loc[idx, k2] = v
            od.loc[idx, "fonte"] = str(r["fonte"]).split(" (")[0] + f" (best-price {datetime.datetime.now():%d/%m/%Y %H:%M})"
            n_ok += 1
            print(f"  ✅ {r['partita']}: 1={b['best_1']} X={b['best_X']} 2={b['best_2']} O25={b['best_O25']} U25={b['best_U25']} GG={b['best_GG']} NG={b['best_NG']} ({b['n_books']} book)")
        except Exception as e:
            print(f"  ⚠️ {r['partita']}: {e}")
        time.sleep(0.4)
    od.to_csv(f, index=False)
    print(f"💾 {f.name} aggiornato: {n_ok}/{len(sub)} match refreshed alle {datetime.datetime.now():%H:%M}")


if __name__ == "__main__":
    main()
