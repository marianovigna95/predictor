#!/usr/bin/env python3
"""step9b_xg_all.py — xG match-level da FotMob per TUTTE le 16 leghe (stagione 2026/27 giocata).

Uso: python3 src/step9b_xg_all.py [--since 2026-08-01]
Output: data/xg_fotmob_all.csv  (matchId,date,league,home,away,xgH,xgA,hg,ag)
Base per la feature rolling-xG nel modello (backtest in step10b).
"""
import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step1b_fixtures_leagues import LEAGUES  # noqa: E402  (id FotMob + nome lega)
from step9_fotmob_xg import get, next_data, match_xg, NAME_MAP  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def league_played(lid, since):
    url = f"https://fotmob.com/leagues/{lid}/fixtures"
    j = next_data(get(url))
    matches = j["props"]["pageProps"]["fixtures"]["allMatches"]
    out = []
    for m in matches:
        st = m.get("status", {})
        if not st.get("finished"):
            continue
        d = st.get("utcTime", "")[:10]
        if d < since:
            continue
        out.append(m)
    return out


def fetch(m, lega):
    try:
        url = "https://fotmob.com" + m["pageUrl"].split("#")[0]
        xh, xa = match_xg(get(url))
        sc = m.get("status", {}).get("scoreStr", "")
        hg, ag = (None, None)
        mm = re.match(r"(\d+)\s*-\s*(\d+)", sc or "")
        if mm:
            hg, ag = int(mm.group(1)), int(mm.group(2))
        return {"matchId": m["id"], "date": m["status"]["utcTime"][:10], "league": lega,
                "home": NAME_MAP.get(m["home"]["name"], m["home"]["name"]),
                "away": NAME_MAP.get(m["away"]["name"], m["away"]["name"]),
                "xgH": xh, "xgA": xa, "hg": hg, "ag": ag}
    except Exception as e:
        return {"matchId": m.get("id"), "league": lega, "error": str(e)[:80]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01")
    args = ap.parse_args()
    out_p = os.path.join(DATA, "xg_fotmob_all.csv")
    done = set()
    if os.path.exists(out_p):
        done = set(pd.read_csv(out_p)["matchId"].astype(str))
    rows = []
    for code, (lid, name) in LEAGUES.items():
        try:
            played = league_played(lid, args.since)
        except Exception as e:
            print(f"✘ {name}: {str(e)[:60]}")
            continue
        todo = [m for m in played if str(m["id"]) not in done]
        print(f"⚽ {name}: {len(played)} giocate (da scaricare {len(todo)})")
        with ThreadPoolExecutor(max_workers=8) as ex:
            rows += list(ex.map(lambda m: fetch(m, name), todo))
        if rows:
            pd.DataFrame(rows).to_csv(out_p, index=False, mode="a" if os.path.exists(out_p) else "w",
                                      header=not os.path.exists(out_p))
    df = pd.read_csv(out_p)
    print(f"\n💾 {out_p}: {len(df)} match totali, {df['league'].nunique()} leghe, con xG: {df['xgH'].notna().sum()}")


if __name__ == "__main__":
    main()
