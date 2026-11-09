#!/usr/bin/env python3
"""step17_bench_nt.py — benchmark NerdyTips (NT Apex) vs il NOSTRO modello.

Dati: allMatches.xlsx (pubblico, nerdytips) — per match: Best Tip / Underover / Final Result + Trust + Odd + esito.
Confronto sul periodo 2026-08-01..2026-11-05 nelle nostre 13 leghe:
- 1X2: NT pick 'Final Result' vs nostro argmax(P) → accuracy + RPS (P nostro vs P implicita NT dalle sue odd)
- O/U 2.5: NT 'Underover' (linea in col? qui 'Underover' contiene es. 'under 2.5') vs nostro p_over>0.5
- Profitto: puntare 1u su ogni pick al suo Odd → ROI NT vs ROI nostro (a parità di match, alle odd NT)
Output: stampa + data/bench_nerdytips.csv
"""
import difflib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_multi import train_league, predict_match, standings, last_match  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LEAGUES = ["Serie A", "Serie B", "Premier League", "LaLiga", "Bundesliga", "Ligue 1", "Eredivisie",
           "Primeira Liga", "Championship", "Segunda", "Bundesliga 2", "Ligue 2", "Süper Lig"]


def nn(t):
    return "".join(c for c in str(t).lower() if c.isalnum())


def rps3(probs, y):
    cp = np.cumsum(probs)
    co = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cp - co) ** 2) / 2)


def main():
    nt = pd.read_excel("/tmp/nt_all.xlsx", sheet_name="Matches_2026")
    nt["Date"] = pd.to_datetime(nt["Date"], errors="coerce")
    nt = nt[(nt["Date"] >= "2026-08-01") & (nt["Date"] <= "2026-11-05")]
    nt = nt[nt["League"].isin(LEAGUES)]
    nt = nt[nt["Goals Home"].notna()]
    print(f"NT matches nel periodo, nostre leghe: {len(nt)}")
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"], errors="coerce")
    m = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"], low_memory=False)

    cache = {}
    rows = []
    for _, r in nt.sort_values("Date").iterrows():
        lg = r["League"]
        d = r["Date"].normalize()
        cand = fx[(fx["league"] == lg) & (fx["Date"].dt.normalize() == d)]
        home = away = None
        for _, f in cand.iterrows():
            if difflib.SequenceMatcher(None, nn(f["home"]) + "vs" + nn(f["away"]), nn(r["Home Team"]) + "vs" + nn(r["Away Team"])).ratio() > 0.5:
                home, away = f["home"], f["away"]
                break
        if home is None:
            continue
        hist = m[m["League"] == lg].sort_values("Date").reset_index(drop=True)
        played = hist[hist["Date"] < d]
        if len(played) < 300:
            continue
        key = (lg, d)
        if key not in cache:
            elo, dc_hist, ad, ahg, aag, draw_base = train_league(played)
            cache[key] = (elo, dc_hist, ad, ahg, aag, draw_base, standings(played), last_match(played, d))
        elo, dc_hist, ad, ahg, aag, draw_base, stand, last = cache[key]
        P, p_over, p_btts, *_ = predict_match(elo, dc_hist, ad, ahg, aag, draw_base, d, home, away, stand=stand, last=last, odds=None)
        gh, ga = int(r["Goals Home"]), int(r["Goals Away"])
        y = 0 if gh > ga else (2 if gh < ga else 1)
        # NT 1X2
        nt_1x2 = str(r["Final Result"]).strip().upper()
        nt_1x2_ok = {"1": 0, "X": 1, "2": 2}.get(nt_1x2, None) == y if nt_1x2 in ("1", "X", "2") else np.nan
        odds = [r.get("Odd Home"), r.get("Odd Draw"), r.get("Odd Away")]
        nt_p = np.array([1 / o if pd.notna(o) and o > 1 else np.nan for o in odds], dtype=float)
        if np.isnan(nt_p).any():
            nt_p = None
        else:
            nt_p = nt_p / nt_p.sum()
        our_pick = int(P.argmax())
        # NT O/U: colonna Underover tipo 'under 2.5'
        uo = str(r["Underover"]).lower()
        nt_uo_over = "over" in uo
        try:
            nt_line = float(uo.split()[-1])
        except Exception:
            nt_line = 2.5
        ou_hit = (gh + ga) > nt_line
        our_uo = p_over > 0.5 if nt_line == 2.5 else np.nan  # confrontiamo solo sulla 2.5
        # profit a 1u sulle pick (odd NT)
        btts = str(r["Both Teams to Score"]).upper()
        nt_btts_ok = (btts == "YES") == (gh > 0 and ga > 0) if btts in ("YES", "NO") else np.nan
        rows.append({
            "lega": lg, "data": str(r["Date"].date()), "partita": f"{home} - {away}",
            "nt_1x2": nt_1x2, "nt_1x2_ok": nt_1x2_ok, "nt_1x2_odd": r.get("Odd Final Result"),
            "nt_trust_1x2": r.get("Trust Final Result"),
            "our_1x2_ok": int(our_pick == y), "rps_ours": rps3(P, y),
            "rps_nt": rps3(nt_p, y) if nt_p is not None else np.nan,
            "nt_ou": uo, "nt_ou_ok": int(nt_uo_over == ou_hit) if "2.5" in uo else "",
            "our_ou_ok": int(our_uo == ou_hit) if (nt_line == 2.5 and our_uo is not np.nan) else "",
            "nt_btts_ok": nt_btts_ok, "our_btts_ok": int((p_btts > 0.5) == (gh > 0 and ga > 0)),
            "goals": gh + ga,
        })
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "bench_nerdytips.csv", index=False)
    n = len(df)
    nt1 = pd.to_numeric(df["nt_1x2_ok"], errors="coerce"); our1 = pd.to_numeric(df["our_1x2_ok"], errors="coerce")
    rps_o = pd.to_numeric(df["rps_ours"], errors="coerce"); rps_n = pd.to_numeric(df["rps_nt"], errors="coerce")
    nto = pd.to_numeric(df["nt_ou_ok"], errors="coerce"); ouro = pd.to_numeric(df["our_ou_ok"], errors="coerce")
    ntb = pd.to_numeric(df["nt_btts_ok"], errors="coerce"); ourb = pd.to_numeric(df["our_btts_ok"], errors="coerce")
    print(f"\n📊 Benchmark su {n} match (nostre leghe, 08/2026→11/2026):")
    print(f"  1X2 acc:   NT {nt1.mean()*100:.1f}%  | NOI {our1.mean()*100:.1f}%")
    print(f"  1X2 RPS:   NT {rps_n.mean():.4f} | NOI {rps_o.mean():.4f}  (più basso = meglio)")
    print(f"  O2.5 acc:  NT {nto.mean()*100:.1f}%  | NOI {ouro.mean()*100:.1f}%")
    print(f"  BTTS acc:  NT {ntb.mean()*100:.1f}% | NOI {ourb.mean()*100:.1f}%")
    # ROI a 1u su ogni pick 1X2 al suo odd (quota NT)
    odd = pd.to_numeric(df["nt_1x2_odd"], errors="coerce")
    roi_nt = (nt1 * (odd - 1) - (1 - nt1)).sum() / n
    roi_our = (our1 * (odd - 1) - (1 - our1)).sum() / n
    print(f"  ROI 1X2 (1u/pick @odd NT): NT {roi_nt*100:+.1f}% | NOI {roi_our*100:+.1f}%")
    print("\nPer lega (acc 1X2):")
    print(df.assign(nt=nt1, our=our1).groupby("lega")[["nt", "our"]].mean().mul(100).round(1).to_string())
    print("\n💾 data/bench_nerdytips.csv")


if __name__ == "__main__":
    main()
