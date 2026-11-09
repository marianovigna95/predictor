#!/usr/bin/env python3
"""step21_surebets.py — pagina SUREBETS divisa in:
  🚩 NON-ADM (da centroquote /sure-bets/, book USA ecc. — solo informative, ILLEGALI per residenti IT)
  ⚪ best-price misti (dai nostri odds wincomparator, overround<1 — da verificare su book ADM)
Output: site/surebets.html + nav in make_site. Uso: python3 src/step21_surebets.py
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd
from make_site import footer  # 🛠 09/11 tabbar+legale condivisi

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}

# operatori con licenza ADM Italia (scommesse a quota fissa) — elenco pubblico ADM
ADM_IT = {"snai", "sisal", "goldbet", "eurobet", "betaland", "leovegas", "williamhill", "bet365",
          "bwin", "pokerstars", "planetwin", "admiral", "codere", "lottomatica", "betflag", "mister",
          "snai-wc", "goldbet.it", "eurobet.it", "sisal.it", "sisal-wc", "winner", "better"}


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")


def parse_centroquote():
    """Estrae le surebet dalla pagina centroquote con nome bookmaker e profitto."""
    try:
        h = fetch("https://www.centroquote.it/sure-bets/")
    except Exception as e:
        print("centroquote err:", e)
        return []
    out = []
    # blocchi: każda surebet ha link /proxy/bookmakers/<slug>/... e 'Profitto' con %
    blocks = re.split(r'Profitto', h)
    books_in_page = re.findall(r'/proxy/bookmakers/([a-z0-9-]+)/', h)
    # euristica: per ogni match bloccato, prendi i book citati e la % più vicina
    for m in re.finditer(r'([A-ZÀ-Ü][\w\' .-]{3,60}?)-([A-ZÀ-Ü][\w\' .-]{3,60}?)</a>[\s\S]{0,3000}?([\d.]+)\s*%', h):
        pass
    # più robusto: estrai tutte le coppie (book, quota) e le % profit
    pairs = re.findall(r'/proxy/bookmakers/([a-z0-9-]+)/[\s\S]{0,200}?>([\d.]+)<', h)
    profits = re.findall(r'>([\d.]+)\s*%', h)
    # fallback: lista dei book nella pagina con ADM flag
    seen = []
    for b in dict.fromkeys(books_in_page):
        adm = b in ADM_IT or any(b.startswith(a) for a in ADM_IT)
        seen.append((b, "ADM ✅" if adm else "NON-ADM 🚩"))
    return seen, profits[:10]


ADM_SLUGS = {"snai", "sisal", "goldbet", "eurobet", "betaland", "leovegas", "william-hill", "bet365",
             "bwin", "pokerstars", "unibet", "planetwin", "admiral", "codere", "betflag", "winner", "lottomatica"}


def wc_match_url(fonte):
    m = re.search(r'([a-z0-9-]+-\d+)/', fonte)
    return f"https://www.wincomparator.com/predictions/{m.group(1)}/" if m else None


def per_book_odds(fonte, section="odds-RESULT"):
    """Quote 1X2 per bookmaker dalla pagina match wincomparator. Ritorna [(slug, q1, qx, q2)]"""
    u = wc_match_url(fonte)
    if not u:
        return []
    try:
        h = fetch(u)
    except Exception:
        return []
    i = h.find(f'id="{section}"')
    if i < 0:
        return []
    j = h.find('id="odds-', i + 10)
    seg = h[i:j if j > 0 else i + 60000]
    parts = seg.split("bookmakers/")
    out = []
    for k, pp in enumerate(parts[1:], 1):
        m = re.match(r"(\d+x\d+)/([a-z0-9-]+?)\.(?:webp|png|svg)", pp)
        if m and k + 1 < len(parts):
            slug = m.group(2).split("-")[0] if not m.group(2)[:-36].strip("-") else m.group(2)
            slug = re.sub(r"-[0-9a-f]{12}$", "", m.group(2))
            qs = re.findall(r">(\d\.\d{2})<", parts[k + 1][:2500])
            if len(qs) >= 3:
                out.append((slug, qs[0], qs[1], qs[2]))
    # dedupe: tieni la prima occorrenza per slug (sezione 1X2)
    seen, res = set(), []
    for slug, a, b, c in out:
        if slug not in seen:
            seen.add(slug)
            res.append((slug, a, b, c))
    return res


def surebet_detail(r):
    """Per una riga odds: quote per book + overround ADM vs all. Ritorna dict o None."""
    books = per_book_odds(r.get("fonte", ""))
    if not books:
        return None
    adm = [(sl, a, b, c) for sl, a, b, c in books if sl in ADM_SLUGS]
    allq = books
    def best(rows, idx):
        return max(rows, key=lambda x: float(x[idx])) if rows else None
    res = {"partita": r["partita"], "lega": r["lega"], "ora": str(r["orario"])[-5:], "fonte": r.get("fonte", ""),
           "books": books, "adm": adm}
    for label, rows in [("ALL", allq), ("ADM", adm)]:
        if not rows:
            res[label] = None
            continue
        b1, bx, b2 = best(rows, 1), best(rows, 2), best(rows, 3)
        ov = 1 / float(b1[1]) + 1 / float(bx[2]) + 1 / float(b2[3])
        legs = [("1", b1[1], b1[0]), ("X", bx[2], bx[0]), ("2", b2[3], b2[0])]
        res[label] = {"ov": round(ov, 4), "margine%": round((1 - ov) * 100, 2) if ov < 1 else None, "legs": legs}
    return res


def per_book_multi(fonte):
    """Quote per book su TUTTI i mercati (1X2, DC, O/U 2.5, GG/NG) dalla pagina wc."""
    u = wc_match_url(fonte)
    if not u:
        return {}
    try:
        h = fetch(u)
    except Exception:
        return {}
    QRE = re.compile(r">(\d+\.\d{2})<")
    def seg(sec):
        i = h.find('id="' + sec + '"')
        if i < 0:
            return ""
        j = h.find('id="odds-', i + 10)
        return h[i:j if j > 0 else len(h)]
    def rows(segm, n):
        out = {}
        for pp in segm.split("bookmakers/")[1:]:
            mm = re.match(r"\d+x\d+/([a-z0-9-]+)\.webp", pp)
            if not mm:
                continue
            qs = QRE.findall(pp)
            if len(qs) >= n:
                out.setdefault(mm.group(1), []).extend(float(x) for x in qs[:n])
        return out
    res = seg("odds-RESULT")
    f0 = res.find("Full Time Result")
    k = res.find("Double Chance", f0 + 10 if f0 > 0 else 10)
    ft = rows(res[f0 if f0 > 0 else 0: k if k > 0 else len(res)], 3)
    k2 = res.find("Double Chance")
    dcseg = res[k2:] if k2 > 0 else ""
    dcend = dcseg.find("Bookmaker", 10)
    if dcend > 0:
        dcseg = dcseg[:dcend]
    dc = rows(dcseg, 3)
    ou = seg("odds-UNDER_OVER")
    occ = list(re.finditer(r'data-panel-key="UNDER_OVER_2_5"', ou))
    ou25 = ""
    if occ:
        m = occ[-1]
        nxt = ou.find('data-panel-key="UNDER_OVER_', m.end())
        ou25 = ou[m.end(): nxt if nxt > 0 else len(ou)]
    ro = rows(ou25, 2)
    goal = seg("odds-GOAL")
    b = goal.find("Both Teams To Score")
    e = goal.find("First Team To Score", b + 10) if b > 0 else -1
    rg = rows(goal[b:e if e > 0 else len(goal)] if b > 0 else goal, 2)
    books = {}
    for sl, v in ft.items():
        books.setdefault(sl, {})["1X2"] = v[:3]
    for sl, v in dc.items():
        if sl in books and len(v) >= 3:
            books[sl]["DC"] = v[:3]
    for sl, v in ro.items():
        if sl in books and len(v) >= 2:
            books[sl]["OU"] = v[:2]
    for sl, v in rg.items():
        if sl in books and len(v) >= 2:
            books[sl]["GG"] = v[:2]
    return books


MKT_LEG = {
    "1X2": [("1", ("1X2", 0)), ("X", ("1X2", 1)), ("2", ("1X2", 2))],
    "O2.5": [("O2.5", ("OU", 0)), ("U2.5", ("OU", 1))],
    "GG/NG": [("GG", ("GG", 0)), ("NG", ("GG", 1))],
    "DC 1X": [("DC 1X", ("DC", 0)), ("2", ("1X2", 2))],
    "DC X2": [("DC X2", ("DC", 1)), ("1", ("1X2", 0))],
    "DC 12": [("DC 12", ("DC", 2)), ("X", ("1X2", 1))],
}


def bp_details(bp_rows, date_str, stake=100.0):
    """Per ogni match con surebet best-price: per ogni mercato le leg con quota + book di riferimento."""
    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)
    od["data"] = od["data"].astype(str)
    od = od[od["data"] == date_str]
    import time
    out = []
    seen = set()
    for b in bp_rows:
        key = (b["lega"], b["partita"])
        if key in seen:
            continue
        seen.add(key)
        r = od[(od["lega"] == b["lega"]) & (od["partita"] == b["partita"])]
        if len(r) == 0:
            continue
        r = r.iloc[0]
        books = per_book_multi(r.get("fonte", ""))
        if not books:
            continue
        mkts = [b["mercato"] for b in bp_rows if (b["lega"], b["partita"]) == key]
        mlist = []
        for mkt in mkts:
            legs, ok = [], True
            for esito, (grp, idx) in MKT_LEG.get(mkt, []):
                cand = [(sl, bm[grp][idx]) for sl, bm in books.items() if grp in bm and len(bm[grp]) > idx]
                if not cand:
                    ok = False
                    break
                sl, q = max(cand, key=lambda x: x[1])
                legs.append((esito, round(q, 2), sl))
            if ok and len(legs) == len(MKT_LEG[mkt]):
                ov = sum(1 / q for _, q, _ in legs)
                if ov < 1.0:
                    # 🆕 09/11 importi: budget S=stake, punta x_i = S/(q_i*ov) → vincita netta uguale su ogni leg
                    legs_s = [(e, q, bk, round(stake / (q * ov))) for e, q, bk in legs]  # 🛠 09/11 puntate arrotondate all'euro
                    mlist.append({"mkt": mkt, "margine%": round((1 - ov) * 100, 2),
                                  "netto": round(stake * (1 / ov - 1), 2), "legs": legs_s})
        if mlist:
            out.append({"ora": b["ora"], "lega": b["lega"], "partita": b["partita"], "fonte": r.get("fonte", ""), "mkts": mlist})
        time.sleep(1.5)
    return out


def bestprice_surebets(date_str):
    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)
    od["data"] = od["data"].astype(str)
    od = od[od["data"] == date_str]
    rows = []
    for _, r in od.iterrows():
        checks = []
        if pd.notna(r.get("best_1")) and pd.notna(r.get("best_X")) and pd.notna(r.get("best_2")):
            checks.append(("1X2", 1 / r["best_1"] + 1 / r["best_X"] + 1 / r["best_2"],
                           f"1@{r['best_1']} X@{r['best_X']} 2@{r['best_2']}"))
        for mkt, a, b in [("O2.5", "best_O25", "best_U25"), ("GG/NG", "best_GG", "best_NG")]:
            if pd.notna(r.get(a)) and pd.notna(r.get(b)):
                checks.append((mkt, 1 / r[a] + 1 / r[b], f"{mkt}: {r[a]} / {r[b]}"))
        # 🆕 09/11 doppie chance: solo con quote DC REALI (best_DC* da wincomparator), mai calcolate
        for mkt, dck, restk in [("DC 1X", "best_DC1X", "best_2"), ("DC X2", "best_DCX2", "best_1"), ("DC 12", "best_DC12", "best_X")]:
            if pd.notna(r.get(dck)) and pd.notna(r.get(restk)):
                ov = 1 / r[dck] + 1 / r[restk]
                checks.append((mkt, ov, f"{mkt}@{r[dck]:.2f} + {r[restk]:.2f}"))
        for mkt, ov, qs in checks:
            if ov < 1.0:
                rows.append({"ora": str(r["orario"])[-5:], "lega": r["lega"], "partita": r["partita"],
                             "mercato": mkt, "margine%": round((1 - ov) * 100, 2), "quote": qs})
    return rows


def page(nonadm_books, profits, bp_rows, date_str, details, bpdet):
    def surebet_rows(details, key):
        """Una riga per LEG della surebet: solo la quota migliore per esito + book. Solo se overround<1."""
        out = ""
        for d in details:
            sec = d.get(key)
            if not sec or not sec.get("margine%"):
                continue
            mu = wc_match_url(d.get("fonte", "")) or "#"
            for esito, q, book in sec["legs"]:
                out += (f"<tr><td>{d['ora']}</td><td>{html.escape(d['lega'])}</td><td>{html.escape(d['partita'])}</td>"
                        f"<td>1X2 {esito}</td><td><a href='{mu}' target='_blank' title='Vedi la quota su wincomparator (aggregatore — analisi, non gioco)'><b>{q}</b> @ <b>{html.escape(book)}</b> ↗</a></td></tr>")
            out += (f"<tr><td colspan=4 style='text-align:right;color:var(--sub)'>margine surebet</td>"
                    f"<td><b>+{sec['margine%']}%</b></td></tr>")
        return out or "<tr><td colspan=5>nessuna surebet in questa categoria oggi</td></tr>"
    adm_rows = surebet_rows(details, "ADM")
    na_rows = surebet_rows(details, "ALL")
    na = "".join(f"<tr><td>{html.escape(b)}</td><td>{c}</td></tr>" for b, c in nonadm_books) or "<tr><td colspan=2>nessuna</td></tr>"
    bp = "".join(f"<tr><td>{r['ora']}</td><td>{html.escape(r['lega'])}</td><td>{html.escape(r['partita'])}</td><td>{r['mercato']}</td><td><b>+{r['margine%']}%</b></td><td class='sub'>{html.escape(r['quote'])}</td></tr>" for r in bp_rows) or "<tr><td colspan=6>nessuna surebet best-price oggi</td></tr>"
    bpd = ""
    for d in bpdet:
        mu = wc_match_url(d.get("fonte", "")) or "#"
        trs = ""
        for mk in d["mkts"]:
            legtxt = " · ".join(f"{e} <a href='{mu}' target='_blank' title='Vedi quota su wincomparator (aggregatore — analisi, non gioco)'><b>{q:.2f}</b> @ <b>{html.escape(bk)}</b> ↗</a> — punta <b>€{st:.2f}</b>" for e, q, bk, st in mk["legs"])
            trs += (f"<tr><td>{d['ora']}</td><td>{html.escape(d['lega'])}</td><td>{html.escape(d['partita'])}</td>"
                    f"<td><b>{mk['mkt']}</b></td><td><b>+{mk['margine%']}%</b> (netto €{mk['netto']:.2f} su €100)</td><td>{legtxt}</td></tr>")
        bpd += (f"<table style='margin-bottom:14px'><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Margine</th>"
                f"<th>Leg: esito · quota @ book · punta €</th></tr>{trs}</table>")
    if not bpd:
        bpd = "<p class='sub'>nessun dettaglio disponibile</p>"
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="apple-touch-icon" href="icon-192.png"><script>if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js")</script>
<title>⚖️ Surebets — Predictor</title><style>
:root{{--bg:#0b1220;--card:#111c33;--txt:#e2e8f0;--sub:#94a3b8;--acc:#2563eb;--bad:#dc2626;--ok:#16a34a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}}
header{{padding:12px 14px;border-bottom:1px solid #1e293b}}nav{{display:flex;gap:6px;flex-wrap:wrap;padding:8px 14px;background:#0d1526;border-bottom:1px solid #1e293b}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:12px;padding:5px 10px;border-radius:8px;background:#16233d}}nav a.on{{background:var(--acc);color:#fff}}
main{{max-width:900px;margin:0 auto;padding:12px}}h2{{font-size:17px;margin:18px 0 8px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;font-size:13px}}
td,th{{padding:7px 9px;border-bottom:1px solid #1e293b;text-align:left}}th{{color:var(--sub);font-size:11px;text-transform:uppercase}}
.warn{{background:#3b0d0d;border:1px solid var(--bad);border-radius:10px;padding:10px 12px;font-size:13px;margin:10px 0}}
.note{{background:#0d1526;border:1px solid #1e293b;border-radius:10px;padding:10px 12px;font-size:12px;color:var(--sub);margin:10px 0}}
.sub{{color:var(--sub);font-size:11px}}
</style></head><body>
<header><b>⚖️ Surebets {date_str}</b> <span class="sub">— analisi, non Raccomandazione di gioco</span></header>
<nav><a href="index.html">Home</a><a href="diretta.html">🔴 Diretta</a><a href="giocata_multi.html">Giocate</a><a href="archivio.html">Archivio+CLV</a><a href="metodo.html">Metodo</a><a class="on" href="surebets.html">⚖️ Surebets</a><a href="glossario.html">Glossario</a></nav>
<main>
<div class="warn">🚩 <b>In Italia si può scommettere SOLO su opérateurs con licenza ADM.</b> Le surebet su book esteri/non-ADM sono <b>illegali</b> per i residenti IT e senza alcuna tutela. Questa pagina è <b>solo analisi</b>: non pratichiamo arbitraggio (il nostro metodo è EV del modello + ¼ Kelly). Rischi reali: slippage quote, gubbing (limitazione conto), errori operativi. 18+ · ADM · autoesclusione.it · 800 558822</div>
<h2>🚩 Book NON-ADM citati su CentroQuote /sure-bets/ (solo informativi — NON giocabili legalmente in Italia)</h2>
<table><tr><th>Bookmaker</th><th>Classificazione</th></tr>{na}</table>
<p class="sub">Profitti indicati da CentroQuote: {', '.join(profits) if profits else 'n/d'} — fonte centroquote.it/sure-bets (429 allo scraping diretto, pagina con ads a book USA)</p>
<h2>⚪ Surebet best-price dai nostri odds (wincomparator, {date_str}) — book misti, da verificare su ADM</h2>
<div class="note">Overround &lt; 100% usando le MIGLIORI quote di mercato (multi-book). Per giocarla legalmente in Italia andrebbe replicata SOLO su book ADM: le nostre dati non separano il book, quindi da verificare manualmente sulle schedine ADM.</div>
<table><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Margine</th><th>Quote best</th></tr>{bp}</table>
<h2>🔎 Come/come giocare la surebet best-price — per mercato, quota &amp; book di riferimento</h2>
<div class="note">Per ogni mercato in arbitraggio (margine &gt; 0) vedi ogni <b>leg</b>: esito da puntare, <b>quota migliore</b> e <b>book di riferimento</b> (dove quella quota è quotata). Link solo alla pagina wincomparator del match (aggregatore): <b>in Italia si può puntare SOLO su book con licenza ADM</b> — verifica il book in elenco ADM prima di qualsiasi operazione. Analisi, non istigazione al gioco.</div>
{bpd}
<h2>🔎 Dettaglio per bookmaker (wincomparator live)</h2>
<div class="note">⚠️ I link sulle quote portano alla pagina <b>wincomparator</b> del match (aggregatore: vedi la quota e il book). <b>Nessun link diretto per puntare su book non-ADM</b>: in Italia è illegale (solo ADM). Colonne: <b>ora · lega · partita · mercato · quota&amp;book</b>. Una riga per <b>ogni leg della surebet</b> (solo la quota migliore per esito e il book dove puntarla). Tabella verde = surebet su book ADM; rossa = solo su book esteri.</div>
<h3 style="color:#4ade80">✅ Surebet su book ADM (giocabile legalmente in Italia)</h3>
<table><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Quota &amp; book</th></tr>{adm_rows}</table>
<h3 style="color:#f87171">🚩 Surebet su book NON-ADM (esteri — solo informative, illegali per residenti IT)</h3>
<table><tr><th>Ora</th><th>Lega</th><th>Partita</th><th>Mercato</th><th>Quota &amp; book</th></tr>{na_rows}</table>
</main>{footer("surebets")}</body></html>"""


if __name__ == "__main__":
    import datetime
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    books, profits = parse_centroquote()
    bp = bestprice_surebets(date_str)
    bpdet = bp_details(bp, date_str)
    # dettaglio per book (quota + book di riferimento) sulle partite con overround basso
    od = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("odds_window_*_bestprice.csv"))], ignore_index=True)
    od["data"] = od["data"].astype(str)
    od = od[od["data"] == date_str].dropna(subset=["best_1", "best_X", "best_2"])
    od = od.assign(ov=1 / od["best_1"] + 1 / od["best_X"] + 1 / od["best_2"])
    cand = od[od["ov"] < 1.03]
    details = []
    import time
    for _, r in cand.iterrows():
        d = surebet_detail(r)
        if d:
            details.append(d)
        time.sleep(2)
    SITE.mkdir(exist_ok=True)
    (SITE / "surebets.html").write_text(page(books, profits, bp, date_str, details, bpdet), encoding="utf-8")
    print(f"⚖️ site/surebets.html: {len(books)} book centroquote, {len(bp)} surebet best-price, {len(details)} match dettaglio 1X2, {len(bpdet)} match dettaglio multi-mercato — {date_str}")
