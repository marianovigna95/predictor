"""
📊 REPORT MULTI-LEGA DEL WEEKEND — prévisions walk-forward vs risultati ufficiali
per tutte e 5 le leghe (Serie A, PL, LaLiga, Bundesliga, Ligue 1) nella finestra 31/10-02/11.

Per ogni lega: addestra Elo + Dixon-Coles SOLO sulle partite prima della finestra,
prevede ogni partita del weekend e la confronta con il risultato reale (matches.csv).
Output: data/report_weekend.csv (una riga per partita, con motivo in parole + RPS modello vs mercato)

Uso:  python3 src/report_weekend.py                 # default 2026-10-31 .. 2026-11-02
      python3 src/report_weekend.py --from 2026-10-31 --to 2026-11-02
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_multi import (LEAGUES, DIV2LEAGUE, train_league, predict_match,
                          standings, last_match)
from motivi import motivo_match, frase_motivo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def rps_one(p, y):
    cum_p = np.cumsum(p)
    cum_o = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cum_p - cum_o) ** 2) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2026-10-31")
    ap.add_argument("--to", dest="to", default="2026-11-02")
    args = ap.parse_args()
    frm, to = pd.Timestamp(args.frm), pd.Timestamp(args.to) + pd.Timedelta(hours=23, minutes=59)

    matches = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"])
    fa = pd.read_csv(DATA / "fixtures_all_2627.csv", encoding="utf-8-sig")
    fa["Date"] = pd.to_datetime(fa["Date"], format="%d/%m/%Y", errors="coerce")
    fa = fa.dropna(subset=["Date"])
    odds_avg = {}
    for _, r in fa.iterrows():
        k = (r["Div"], r["Date"].normalize(), r["HomeTeam"], r["AwayTeam"])
        if pd.notna(r.get("AvgH")):
            odds_avg[k] = (r["AvgH"], r["AvgD"], r["AvgA"])

    # risultati ufficiali nella finestra
    res = {}
    for _, m in matches[(matches["Date"] >= frm) & (matches["Date"] <= to)].iterrows():
        res[(m["League"], m["Date"].normalize(), m["HomeTeam"], m["AwayTeam"])] = (m["FTHG"], m["FTAG"], m["FTR"])

    window = fx[(fx["Date"] >= frm) & (fx["Date"] <= to)]
    print(f"🪟 Finestra weekend: {frm.date()} → {to.date()} | partite in calendario: {len(window)}")

    rows = []
    for league in LEAGUES:
        sub = window[window["league"] == league].sort_values("Date")
        if sub.empty:
            continue
        played = matches[(matches["League"] == league) & (matches["Date"] < frm)].sort_values("Date")
        elo, dc_hist, ad, ahg, aag, draw_base = train_league(played)
        stand = standings(played)
        last = last_match(played, sub["Date"].min())
        div = next(d for d, l in DIV2LEAGUE.items() if l == league)
        n_ok = n_tot = 0
        rps_m, rps_k = [], []
        for _, f in sub.iterrows():
            k = (div, f["Date"].normalize(), f["home"], f["away"])
            o_avg = odds_avg.get(k)
            P, p_over, p_btts, top, top_p, rh, ra, lh, la = predict_match(
                elo, dc_hist, ad, ahg, aag, draw_base, f["Date"], f["home"], f["away"],
                stand=stand, last=last, odds=o_avg)
            pick = int(P.argmax())
            # verdetto analista automatico (regola trasparente): modello==mercato → pick; disaccordo → doppia chance
            j_m = None
            if o_avg is not None:
                inv = 1 / np.array(o_avg, float)
                j_m = int((inv / inv.sum()).argmax())
            if j_m is None or j_m == pick:
                verdict = ["1", "X", "2"][pick]
                vconf = "alta" if P.max() >= 0.55 else "media"
            else:
                pair = sorted({pick, j_m})
                verdict = {0: "1X", 1: "12", 2: "X2"}[[0,1,2].index(pair[0])] if len(pair) == 2 else ["1","X","2"][pick]
                verdict = {(0, 1): "1X", (1, 2): "12", (0, 2): "X2"}[tuple(pair)]
                vconf = "bassa"
            motivo = motivo_match(f["home"], f["away"], f["Date"], played, rh, ra, lh, la,
                                  stand=stand, last=last, P=P, pick=pick, elo_raw=elo)
            verbale = frase_motivo(f["home"], f["away"], f["Date"], played, rh, ra, lh, la,
                                   stand=stand, last=last, P=P, pick=pick, elo_raw=elo)
            rk = (league, f["Date"].normalize(), f["home"], f["away"])
            # pronostici degli ALTRI mercati (dal modello): GG/NG e Over/Under 2.5
            gg_pron = "GG" if p_btts >= 0.5 else "NG"
            ou_pron = "O2.5" if p_over >= 0.5 else "U2.5"
            if rk in res:
                hg, ag, ftr = res[rk]
                y = {"H": 0, "D": 1, "A": 2}[ftr]
                esito = ["1", "X", "2"][y]
                risultato = f"{int(hg)}-{int(ag)}"
                ok = "✅" if pick == y else "❌"
                # verdict ✅/❌ (1X2 = pick, doppia chance = y nella coppia)
                if verdict in ("1", "X", "2"):
                    vok = "✅" if y == ["1", "X", "2"].index(verdict) else "❌"
                else:
                    pair = {"1X": (0, 1), "12": (1, 2), "X2": (0, 2)}[verdict]
                    vok = "✅" if y in pair else "❌"
                gg_real = (hg > 0 and ag > 0)
                gg_ok = "✅" if (gg_pron == "GG") == gg_real else "❌"
                ou_real = (hg + ag) > 2.5
                ou_ok = "✅" if (ou_pron == "O2.5") == ou_real else "❌"
                mkt_pick = ["1", "X", "2"][j_m] if j_m is not None else ""
                mkt_ok = "✅" if j_m == y else "❌" if j_m is not None else ""
                n_tot += 1
                n_ok += int(pick == y)
                rps_m.append(rps_one(P, y))
                if o_avg is not None:
                    inv = 1 / np.array(o_avg, float)
                    rps_k.append(rps_one(inv / inv.sum(), y))
            else:
                y, esito, risultato, ok = None, "", "in corso ⏳", "—"
                vok = gg_ok = ou_ok = mkt_ok = "—"
                mkt_pick = ["1", "X", "2"][j_m] if j_m is not None else ""
            if verdict != ["1", "X", "2"][pick]:
                verbale += (" Il verdetto analista copre «" + verdict + "» (doppia chance) perché modello e mercato "
                            "sono in disaccordo (conf. " + vconf + ").")
            row = {
                "lega": league, "giornata": int(f["matchday"]),
                "orario": f["Date"].strftime("%d/%m %H:%M"), "partita": f"{f['home']} - {f['away']}",
                "p1%": round(P[0] * 100, 1), "pX%": round(P[1] * 100, 1), "p2%": round(P[2] * 100, 1),
                "pronostico": ["1", "X", "2"][pick], "conf%": round(P.max() * 100, 1),
                "Over2.5%": round(p_over * 100, 1), "BTTS%": round(p_btts * 100, 1),
                "risultato": risultato, "esito_reale": esito, "✅/❌": ok,
                "verdict": verdict, "verdict_conf": vconf, "verdict_ok": vok,
                "gg_pron": gg_pron, "gg_ok": gg_ok, "ou_pron": ou_pron, "ou_ok": ou_ok,
                "mercato_pick": mkt_pick, "mercato_ok": mkt_ok,
                "rps_modello": round(rps_m[-1], 3) if rps_m and y is not None else "",
                "rps_mercato": round(rps_k[-1], 3) if rps_k and y is not None else "",
                "motivo": motivo, "motivo_verbale": verbale,
            }
            rows.append(row)
        if n_tot:
            print(f"  {league}: modello {n_ok}/{n_tot} ({100*n_ok/n_tot:.1f}%) | RPS modello {np.mean(rps_m):.4f}"
                  + (f" vs mercato {np.mean(rps_k):.4f}" if rps_k else ""))

    df = pd.DataFrame(rows)
    out = DATA / "report_weekend.csv"
    df.to_csv(out, index=False)
    print(f"\n💾 Salvato: {out} ({len(df)} partite)")


if __name__ == "__main__":
    main()
