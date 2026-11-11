#!/usr/bin/env python3
"""step22b_window.py — quote best-price wincomparator per la FINESTRA MOBILE (oggi → +7 giorni).

Scrapea l'indice https://www.wincomparator.com/predictions/football/ (gratis, no key),
matcha le nostre partite della finestra (fixtures_leagues.csv, non giocate) per data+slug,
scarica la pagina match e calcola best_1/X/2, O/U 2.5, GG/NG, DC reali (parser condiviso step22).
Output: data/odds_window_<startMMDD>_bestprice.csv  (una per finestra; le vecchie restano per CLV/archivio)
Uso: python3 src/step22b_window.py [--days 7] [--max 150]
"""
import argparse
import bisect
import datetime
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd

from step22_odds_refresh import fetch, parse_match  # parser quote condiviso

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}

HDR_RE = re.compile(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*-\s*(\d{2}:\d{2})')
LINK_RE = re.compile(r"href='/predictions/([a-z0-9-]+?)-(\d+)/'")


def norm(s):
    """normalizza un nome squadra per matchare lo slug: 'Real Sociedad B' -> 'realsociedadb'."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(cd|fc|sc|ac|cf|ud|rc|ss|sporting|club|deportivo|calcio)\b", " ", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    ALIAS = {"turkiye": "turkey", "czechia": "czechrepublic", "unitedstates": "usa",
             "cotedivoire": "ivorycoast", "korearepublic": "southkorea", "iran": "iriran"}
    return ALIAS.get(s, s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max", type=int, default=150, help="max match da scaricare (throttling)")
    a = ap.parse_args()

    today = datetime.date.today()
    frm, to = today, today + datetime.timedelta(days=a.days)

    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fi = DATA / "fixtures_intl.csv"
    if fi.exists():  # 🆕 10/11 quote anche per le nazionali
        fx = pd.concat([fx, pd.read_csv(fi)], ignore_index=True)
    fx["Date"] = pd.to_datetime(fx["date"])
    win = fx[(fx["played"] == False) & (fx["Date"] >= pd.Timestamp(frm)) &
             (fx["Date"] <= pd.Timestamp(to) + pd.Timedelta(hours=23, minutes=59))].copy()
    print(f"🪟 finestra quote: {frm} → {to} | {len(win)} partite nostre non giocate")
    if win.empty:
        return

    print("📥 indice wincomparator /predictions/football/ …")
    h = fetch("https://www.wincomparator.com/predictions/football/")
    headers = [(m.start(), int(m.group(1)), MONTHS[m.group(2)], m.group(3)) for m in HDR_RE.finditer(h)]
    links = [(m.start(), m.group(1), m.group(2)) for m in LINK_RE.finditer(h)]
    hpos = [x[0] for x in headers]
    yr = today.year
    cand = {}  # data -> [(hhmm, slug)]
    for pos, slug, _mid in links:
        i = bisect.bisect_right(hpos, pos) - 1
        if i < 0:
            continue
        d, mon, hhmm = headers[i][1], headers[i][2], headers[i][3]
        y = yr + 1 if (mon <= 2 and today.month >= 11) else yr  # gennaio visto a nov/dic = anno prox
        cand.setdefault(f"{y}-{mon:02d}-{d:02d}", []).append((hhmm, slug, _mid))
    print(f"   indice: {len(links)} link, {len(cand)} date")

    rows = []
    n = 0
    for _, r in win.iterrows():
        if n >= a.max:
            print(f"   ⏸️ stop a --max={a.max}")
            break
        ds = str(r["Date"].date())
        hn, an = norm(r["home"]), norm(r["away"])
        found = None
        for hhmm, slug, mid in cand.get(ds, []):
            sn = re.sub(r"[^a-z0-9]", "", slug.lower())
            if hn and an and hn in sn and an in sn:
                found = (hhmm, slug, mid)
                break
        if not found:
            continue
        hhmm, slug, mid = found
        path = f"{slug}-{mid}"
        url = f"https://www.wincomparator.com/predictions/{path}/"
        try:
            b = None
            for _ in range(3):
                b = parse_match(fetch(url))
                if b and b["n_books"] >= 3:
                    break
                time.sleep(1.0)
            if not b or b["n_books"] == 0:
                print(f"  ⚠️ {path}: nessun book")
                continue
            rows.append({
                "lega": r["league"], "giornata": r.get("matchday", ""), "data": ds,
                "orario": f"{ds[8:]}/{ds[5:7]} {hhmm}",
                "home": r["home"], "away": r["away"], "partita": f"{r['home']} - {r['away']}",
                "best_1": b["best_1"], "best_X": b["best_X"], "best_2": b["best_2"],
                "best_O25": b["best_O25"], "best_U25": b["best_U25"],
                "best_GG": b["best_GG"], "best_NG": b["best_NG"],
                "fonte": f"wincomparator.com/predictions/{path}/ (best-price {datetime.datetime.now():%d/%m/%Y %H:%M})",
                "best_DC1X": b["best_DC1X"], "best_DCX2": b["best_DCX2"], "best_DC12": b["best_DC12"],
            })
            n += 1
            print(f"  ✅ {ds} {hhmm} {r['home']} - {r['away']}: 1={b['best_1']} X={b['best_X']} 2={b['best_2']} O25={b['best_O25']} U25={b['best_U25']} ({b['n_books']} book)")
        except Exception as e:
            print(f"  ⚠️ {path}: {e}")
        time.sleep(0.4)

    out = DATA / f"odds_window_{frm.strftime('%d%m')}_bestprice.csv"
    if rows:
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"💾 {out.name}: {len(rows)} match best-price per finestra {frm}→{to}")
    else:
        print("⚠️ nessuna quota trovata (throttling?): weekly_multi usa il fallback football-data Max*")


if __name__ == "__main__":
    main()
