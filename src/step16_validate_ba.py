#!/usr/bin/env python3
"""step16_validate_ba.py — validazione modello vs chiusure BetArchives (tutte le partite 31/10-05/11).

Per ogni match in data/betarchives_all.csv: walk-forward (train su matches.csv prima della data),
predizione modello, confronto con closing BetArchives:
- 1X2: edge (p_model - p_close) in pp, RPS, hit
- O2.5: edge p_over vs close_O25
- Corner: p(corner>linea) da Poisson(corners_attesi) vs close corner_over → edge + hit reale
Output: stampa per lega + data/validation_ba.csv
Uso: python3 src/step16_validate_ba.py
"""
import difflib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_multi import train_league, predict_match, standings, last_match, corners_exp, pois_cdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BA2LEAGUE = {"Champions League": "Champions League", "Europa League": "Europa League", "Conference League": "Conference League",
             "Serie A": "Serie A", "Premier League": "Premier League", "LaLiga": "LaLiga", "Bundesliga": "Bundesliga", "Ligue 1": "Ligue 1"}


def nn(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


def rps3(probs, y):
    cp = np.cumsum(probs)
    co = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cp - co) ** 2) / 2)


def main():
    ba = pd.read_csv(DATA / "betarchives_all.csv")
    m = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"], low_memory=False)
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"], errors="coerce")

    # mappa (lega, data, home, away) -> riga matches.csv per allineare nomi
    rows = []
    cache = {}
    for _, r in ba.sort_values("data").iterrows():
        lg = BA2LEAGUE.get(r["lega"])
        if not lg:
            continue
        d = pd.Timestamp(r["data"])
        hist = m[m["League"] == lg].sort_values("Date").reset_index(drop=True)
        # trova il match in fixtures_leagues (nomi nostri) per allineare
        cand = fx[(fx["league"] == lg) & (fx["Date"].dt.normalize() == d.normalize())]
        home = away = None
        for _, f in cand.iterrows():
            combo = difflib.SequenceMatcher(None, nn(f["home"]) + "vs" + nn(f["away"]), nn(r["home"]) + "vs" + nn(r["away"])).ratio()
            if combo > 0.45:
                home, away = f["home"], f["away"]
                break
        if home is None:
            # fallback: match in matches.csv
            cm = hist[hist["Date"].dt.normalize() == d.normalize()]
            for _, mm in cm.iterrows():
                combo = difflib.SequenceMatcher(None, nn(mm["HomeTeam"]) + "vs" + nn(mm["AwayTeam"]), nn(r["home"]) + "vs" + nn(r["away"])).ratio()
                if combo > 0.45:
                    home, away = mm["HomeTeam"], mm["AwayTeam"]
                    break
        if home is None:
            continue
        played = hist[hist["Date"] < d.normalize()]
        if len(played) < 300:
            continue
        key = (lg, d.normalize())
        if key not in cache:
            elo, dc_hist, ad, ahg, aag, draw_base = train_league(played)
            cache[key] = (elo, dc_hist, ad, ahg, aag, draw_base, standings(played), last_match(played, d.normalize()))
        elo, dc_hist, ad, ahg, aag, draw_base, stand, last = cache[key]
        P, p_over, p_btts, *_ = predict_match(elo, dc_hist, ad, ahg, aag, draw_base, d, home, away, stand=stand, last=last, odds=None)
        pick = int(P.argmax())
        # chiusure BA
        c1, cx, c2 = r.get("close_1"), r.get("close_X"), r.get("close_2")
        if pd.notna(c1):
            cp = np.array([1 / c1, 1 / cx, 1 / c2]); cp = cp / cp.sum()
            edge = (P[pick] - cp[pick]) * 100
            y = 0 if r.get("ft_home", 0) > r.get("ft_away", 0) else (2 if r.get("ft_home", 0) < r.get("ft_away", 0) else 1)
            rps_m = rps3(P, y); rps_c = rps3(cp, y)
        else:
            edge = rps_m = rps_c = np.nan; y = np.nan
        # O2.5
        if pd.notna(r.get("close_O25")):
            po = 1 / float(r["close_O25"])
            ou_edge = (p_over - po) * 100
            ou_hit = (p_over > 0.5) == (r.get("ft_home", 0) + r.get("ft_away", 0) > 2.5)
        else:
            ou_edge, ou_hit = np.nan, np.nan
        # Corner
        c_att = corners_exp(played, d, home, away)
        if pd.notna(r.get("corner_over")) and c_att:
            line = float(r.get("corner_line") or 9.5)
            pc = 1 - pois_cdf(int(line), c_att)  # P(corner > line) = P(>= line+1) → cdf(line-0.5)... uso int(line)
            pc = 1 - pois_cdf(int(line) - 1, c_att) if line == int(line) else 1 - pois_cdf(int(line), c_att)
            co_edge = (pc - 1 / float(r["corner_over"])) * 100
            ct = r.get("corners_total")
            co_hit = (pc > 0.5) == (ct > line) if pd.notna(ct) else np.nan
        else:
            co_edge, co_hit = np.nan, np.nan
        rows.append({"lega": lg, "data": str(r["data"]), "partita": f"{home} - {away}",
                     "edge_1x2_pp": round(edge, 2) if pd.notna(edge) else "", "RPS_mod": round(rps_m, 4) if pd.notna(rps_m) else "",
                     "RPS_close": round(rps_c, 4) if pd.notna(rps_c) else "", "hit": 1 if pd.notna(y) and pick == y else (0 if pd.notna(y) else ""),
                     "edge_O25_pp": round(ou_edge, 2) if pd.notna(ou_edge) else "", "ou_hit": ou_hit,
                     "edge_corner_pp": round(co_edge, 2) if pd.notna(co_edge) else "", "corner_hit": co_hit,
                     "corners_attesi": c_att, "corners_reali": r.get("corners_total")})
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "validation_ba.csv", index=False)
    print(f"📊 Validazione vs chiusure BetArchives: {len(df)} match")
    for c in ["edge_1x2_pp", "RPS_mod", "RPS_close", "edge_O25_pp", "edge_corner_pp"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    print(f"  1X2: edge medio {df['edge_1x2_pp'].mean():+.2f} pp | RPS mod {df['RPS_mod'].mean():.4f} vs close {df['RPS_close'].mean():.4f} | acc {pd.to_numeric(df['hit'], errors='coerce').mean()*100:.0f}%")
    print(f"  O2.5: edge medio {df['edge_O25_pp'].mean():+.2f} pp | hit {pd.to_numeric(df['ou_hit'], errors='coerce').mean()*100:.0f}%")
    print(f"  CORNER: edge medio {df['edge_corner_pp'].mean():+.2f} pp | hit {pd.to_numeric(df['corner_hit'], errors='coerce').mean()*100:.0f}%  (corners attesi vs reali: corr {df[['corners_attesi','corners_reali']].corr().iloc[0,1]:.2f})")
    print(df.groupby("lega")[["edge_1x2_pp", "edge_O25_pp", "edge_corner_pp"]].mean().round(2).to_string())
    print("💾 data/validation_ba.csv")


if __name__ == "__main__":
    main()
