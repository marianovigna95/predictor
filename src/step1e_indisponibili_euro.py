#!/usr/bin/env python3
"""step1e_indisponibili_euro.py — indisponibili/squalificati per coppe europee e leghe estere
da fantacalcio.it (pagine EuroLeghe, pubbliche e server-rendered).

Uso: python3 src/step1e_indisponibili_euro.py
Output: data/indisponibili_euro.csv  (team, giocatore, tipo, motivo)
Usato da make_site.py per arricchire i motivi delle match card di coppe ed extra leghe.
"""
import html as htmlmod
import os
import re
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
URL = "https://www.fantacalcio.it/indisponibili-euro-leghe"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0",
     "Accept": "text/html", "Accept-Language": "it-IT,it;q=0.9"}


def fetch():
    req = urllib.request.Request(URL, headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse(html):
    rows = []
    chunks = re.split(r'Stemma', html)
    for ch in chunks[1:]:
        m = re.search(r'title="([^"]+)"', ch) or re.search(r'team-name">([^<]+)<', ch)
        if not m:
            continue
        team = m.group(1).strip()
        for tipo in ("Infortunati", "Squalificati"):
            mi = ch.find(f">{tipo}</strong>")
            if mi < 0:
                continue
            nxt = [x for x in (ch.find(">Squalificati</strong>", mi + 1) if tipo == "Infortunati" else -1,
                               ch.find(">Diffidati</strong>", mi + 1),
                               ch.find("</section>", mi + 1)) if x > 0]
            end = min(nxt) if nxt else len(ch)
            sec = ch[mi:end]
            for pm in re.finditer(r'item-name">([^<]{2,40})</strong>.*?item-description"><p>(.*?)</p>', sec, re.S):
                player = pm.group(1).strip()
                why = re.sub(r"<[^>]+>|\s+", " ", pm.group(2)).strip(" .,-")
                rows.append({"team": htmlmod.unescape(team), "giocatore": htmlmod.unescape(player), "tipo": tipo, "motivo": htmlmod.unescape(why)[:180]})
    return pd.DataFrame(rows).drop_duplicates(subset=["team", "giocatore", "tipo"]) if rows else pd.DataFrame(
        columns=["team", "giocatore", "tipo", "motivo"])


def main():
    df = parse(fetch())
    out = os.path.join(DATA, "indisponibili_euro.csv")
    df.to_csv(out, index=False)
    print(f"💾 {out}: {len(df)} indisponibili ({df['team'].nunique()} squadre)")
    print(df.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
