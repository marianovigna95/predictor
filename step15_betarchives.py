#!/usr/bin/env python3
"""step15_betarchives.py — chiusure AUTOMATICHE da BetArchives (closing odds, tutte le leghe + coppe).

Per ogni giocata in giocata_*.csv / verifica_*.csv: trova la pagina match su betarchives.com
(lega slug + data → lista match → match page) e legge le CLOSING odds dai title="Opened X, closed Y":
1X2 (result), Over/Under 2.5 (goals, riga "2.5 Main"), BTTS (btts Yes/No), Corners (riga Main).

Output: data/betarchives_closing.csv  (data,lega,home,away,close_1,close_X,close_2,close_O25,close_U25,close_GG,close_NG,corner_line,corner_over,corner_under)
Uso: python3 src/step15_betarchives.py [--since 2026-11-03]
"""
import argparse
import glob
import os
import re
import time
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
BASE = "https://betarchives.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
      "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}

SLUG = {
    "Premier League": "premier-league", "LaLiga": "la-liga", "Serie A": "serie-a",
    "Bundesliga": "bundesliga", "Ligue 1": "ligue-1", "Eredivisie": "netherlands-eredivisie",
    "Primeira Liga": "portugal-primeira-liga", "Championship": "england-championship",
    "Serie B": "italy-serie-b", "LaLiga 2": "spain-segunda", "Bundesliga 2": "germany-bundesliga-ii",
    "Ligue 2": "france-ligue-2", "Süper Lig": "super-lig",
    "Champions League": "champions-league", "Europa League": "europa-league", "Conference League": "conference-league",
}


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25).read().decode("utf-8", "ignore")


def nn(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


def slug_teams(link):
    # /match/fc-copenhagen-vs-fc-iberia-1999-2026-11-05 → (fc copenhagen, fc iberia 1999)
    m = re.match(r"/match/(.+)-vs-(.+)-(\d{4}-\d{2}-\d{2})$", link)
    if not m:
        return None
    return nn(m.group(1)), nn(m.group(2))


def parse_section(html, sec_id):
    # sezioni: id="xxx" class="card ..." — prendi fino alla prossima id="yyy" class="card
    ids = [m.start() for m in re.finditer(r'id="[a-z-]+" class="card', html)]
    i = html.find(f'id="{sec_id}"')
    if i < 0:
        return ""
    nxt = min([p for p in ids if p > i + 50], default=i + 80000)
    return html[i:min(nxt, i + 80000)]


def closes_in(sec):
    """ritorna lista [(label, close)] dai title="Opened X, closed Y" con label dallo span precedente."""
    out = []
    for m in re.finditer(r'title="Opened ([\d.]+), closed ([\d.]+)[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span><span[^>]*>([\d.]+)</span>', sec, re.S):
        out.append((m.group(3).strip(), float(m.group(2))))
    return out


def parse_match(html):
    r = {}
    mft = re.search(r'FT (\d+)\u2013(\d+)', html) or re.search(r'FT (\d+)-(\d+)', html)
    if mft:
        r["ft_home"], r["ft_away"] = int(mft.group(1)), int(mft.group(2))
    mc = re.search(r'(\d+) corners', html)
    if mc:
        r["corners_total"] = int(mc.group(1))
    # 1X2
    sec = parse_section(html, "result")
    for label, close in closes_in(sec):
        if label.startswith("1"):
            r["close_1"] = close
        elif label.startswith("X"):
            r["close_X"] = close
        elif label.startswith("2"):
            r["close_2"] = close
    # Goals O/U: riga con linea 2.5 (e badge Main) — le righe sono div grid, non <tr>
    sec = parse_section(html, "goals")
    i = sec.find(">2.5<")
    if i >= 0:
        row = sec[i:i + 4000]
        if "Main" in row:
            cl = re.findall(r'closed ([\d.]+)', row)
            if len(cl) >= 2:
                r["close_O25"], r["close_U25"] = float(cl[0]), float(cl[1])
    # BTTS
    sec = parse_section(html, "btts")
    for label, close in closes_in(sec):
        if label.lower().startswith("yes"):
            r["close_GG"] = close
        elif label.lower().startswith("no"):
            r["close_NG"] = close
    # Corners: prima riga dati (salta header) con 'closed'
    sec = parse_section(html, 'corners')
    pat = r'grid grid-cols-\[64px[^"]*"[^>]*>.*?(?=grid grid-cols-\[64px|</section|$)'
    row = ''
    for m in re.finditer(pat, sec, re.S):
        if 'closed' in m.group(0):
            row = m.group(0); break
    if row:
        line = re.search(r'tabular-nums text-slate-900">([0-9.]+)<', row)
        cl = re.findall(r'closed ([0-9.]+)', row)
        if len(cl) >= 2:
            r['corner_line'] = float(line.group(1)) if line else 9.5
            r['corner_over'], r['corner_under'] = float(cl[0]), float(cl[1])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-03")
    ap.add_argument("--until", default=None)
    ap.add_argument("--all", action="store_true", help="tutte le partite delle leghe nei giorni (non solo giocate)")
    ap.add_argument("--leagues", default="", help="virgola: nomi lega da includere (es. 'Serie A,Premier League')")
    args = ap.parse_args()

    # target dalle giocate/verifiche
    targets = {}  # (data, home, away) → lega
    files = sorted(glob.glob(os.path.join(DATA, "giocata_*.csv"))) + sorted(glob.glob(os.path.join(DATA, "verifica_*.csv")))
    for f in files:
        try:
            g = pd.read_csv(f)
        except Exception:
            continue
        for _, r in g.iterrows():
            d = str(r.get("data"))[:10]
            if d < args.since:
                continue
            raw = str(r.get("partita", ""))
            parts = [p for p in re.split(r" \+ ", raw)]
            for part in parts:
                part = re.sub(r"\s*\[[^\]]*\]", "", part).strip()
                m = re.match(r"(.+?) - (.+)$", part.strip().lstrip("+").strip())
                if m and str(r.get("lega")) in SLUG:
                    targets[(d, nn(m.group(1)), nn(m.group(2)))] = r["lega"]
    print(f"🎯 target: {len(targets)} partite (dal {args.since})")

    out = []
    import datetime
    until = args.until or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if args.all:
        # tutte le partite: per ogni data nel range, tutte le leghe
        d0 = pd.Timestamp(args.since)
        d1 = pd.Timestamp(until)
        targets = {}
        for d in pd.date_range(d0, d1):
            ds = d.date().isoformat()
            if ds > until:
                continue
            for lg, slug in SLUG.items():
                if args.leagues and lg not in [x.strip() for x in args.leagues.split(",")]:
                    continue
                targets[(ds, "", "")] = lg  # placeholder
        by_date_league = {}
        for (d, _, _), lg in targets.items():
            by_date_league.setdefault((d, lg), []).append(("", ""))
    else:
        by_date_league = {}
    for (d, h, a), lg in targets.items():
        by_date_league.setdefault((d, lg), []).append((h, a))

    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    for (d, lg), teams in sorted(by_date_league.items()):
        if d > yesterday:
            continue  # partite non ancora giocate: niente closing
        slug = SLUG[lg]
        try:
            lst = get(f"{BASE}/?date={d}&league={slug}")
        except Exception as e:
            print(f"  ✘ lista {lg} {d}: {str(e)[:40]}")
            continue
        links = {}
        for lk in set(re.findall(r'href="(/match/[^"]+)"', lst)):
            st = slug_teams(lk)
            if st:
                links[st] = lk
        import difflib
        team_iter = teams
        if args.all:
            team_iter = list(links.keys())  # tutte le partite della lista
        for h, a in team_iter:
            lk = links.get((h, a)) or links.get((a, h))
            if not lk and not args.all:
                # fuzzy su stringa "home vs away" (gestisce PSG↔Paris Saint-Germain, Beşiktaş↔Besiktas)
                tgt = f"{h} vs {a}"
                best, bs = None, 0.0
                for (bh, ba), l in links.items():
                    cand = f"{bh} vs {ba}"
                    ratio = difflib.SequenceMatcher(None, tgt, cand).ratio()
                    if ratio > bs:
                        best, bs = l, ratio
                if best and bs >= 0.72:
                    lk = best
            if not lk:
                print(f"  ⚠️ non trovata su BA: {lg} {d} {h}-{a}")
                continue
            time.sleep(2.5)
            try:
                html = get(BASE + lk)
                r = parse_match(html)
                mdate = re.search(r"-(\d{4}-\d{2}-\d{2})$", lk)
                row = {"data": mdate.group(1) if mdate else d, "lega": lg, "home": h, "away": a, "link": BASE + lk}
                if args.all and (not h or not a):
                    m2 = re.match(r"/match/(.+)-vs-(.+)-\d{4}-\d{2}-\d{2}$", lk)
                    if m2:
                        row["home"], row["away"] = m2.group(1).replace("-", " "), m2.group(2).replace("-", " ")
                row.update(r)
                out.append(row)
                print(f"  ✔ {lg} {d} {h}-{a}: 1X2 {r.get('close_1')}/{r.get('close_X')}/{r.get('close_2')} O25 {r.get('close_O25')}/{r.get('close_U25')} GG {r.get('close_GG')} C {r.get('corner_over')}/{r.get('corner_under')}@{r.get('corner_line')}")
            except Exception as e:
                print(f"  ✘ match {lk}: {str(e)[:50]}")
            time.sleep(2.5)

    df = pd.DataFrame(out)
    if len(df):
        fn = "betarchives_all.csv" if args.all else "betarchives_closing.csv"
        fp = os.path.join(DATA, fn)
        if os.path.exists(fp) and not args.all:
            old = pd.read_csv(fp)
            df = pd.concat([old, df]).drop_duplicates(subset=["data", "lega", "link"], keep="last")
        df.to_csv(fp, index=False)
        print(f"💾 data/{fn}: {len(df)} partite con chiusure BetArchives")
    else:
        print("Nessuna partita trovata.")


if __name__ == "__main__":
    main()
