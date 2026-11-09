"""
STEP 10 — VERSIONE "MAX": convalida walk-forward delle migliorie sul dati reali.

Confronta, sulle ultime 3 giornate giocate (g8, g9, g10 della stagione 2026/27):
  V0  base        = Elo + Dixon-Coles (50/50), xG reali dove ci sono
  V1  + congestione = penalità Elo se la squadra ha riposato < 4 giorni
  V2  + motivazione = bonus Elo da posizione in classifica (top4 / ultime3 / centro)
  V3  + pesi walk-forward = pesi Elo/DC/mercato ottimizzati sulla giornata precedente
  (V3 applica V1+V2 e cerca i pesi migliori sulla giornata prima di quella target)

Metriche: RPS e % pronostici corretti, vs mercato (quote AvgC / quote g10 da step8).

Uso:  python3 src/step10_max.py
"""
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from step3_elo import update_elo, elo_to_probs
from step4_dixon_coles import TeamHistory, score_matrix, matrix_to_markets, dc_weights
from weekly_forecast import (train_on_played, xg_proxy, ELO_K, ELO_HFA, SHRINK,
                            DC_HALF_LIFE, DATA)

# quote g10 usate nello step 8 (da mercato)
G10_ODDS = {
    ("Bologna", "Monza"): (1.67, 3.85, 4.85), ("Udinese", "Roma"): (5.55, 4.33, 1.53),
    ("Milan", "Inter"): (3.05, 3.70, 2.18), ("Como", "Venezia"): (1.29, 5.83, 8.58),
    ("Frosinone", "Torino"): (2.13, 3.76, 3.01), ("Lazio", "Cagliari"): (1.43, 4.42, 7.06),
    ("Lecce", "Genoa"): (3.21, 2.98, 2.35), ("Juventus", "Napoli"): (2.24, 3.22, 3.26),
    ("Sassuolo", "Fiorentina"): (2.80, 3.59, 2.35), ("Atalanta", "Parma"): (1.48, 4.51, 6.07),
}
G10_RESULTS = {  # (hg, ag) — fonte step8/web
    ("Bologna", "Monza"): (2, 1), ("Udinese", "Roma"): (2, 5), ("Milan", "Inter"): (3, 1),
    ("Como", "Venezia"): (1, 0), ("Frosinone", "Torino"): (3, 1), ("Lazio", "Cagliari"): (3, 1),
    ("Lecce", "Genoa"): (0, 0), ("Juventus", "Napoli"): (2, 2), ("Sassuolo", "Fiorentina"): (3, 1),
    ("Atalanta", "Parma"): (0, 0),
}


def load_played():
    played = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    ex = pd.read_csv(DATA / "matches_extra.csv", parse_dates=["Date"])
    ex["Season"] = "2026/2027"
    ex["FTR"] = ex.apply(lambda r: "H" if r["FTHG"] > r["FTAG"] else ("A" if r["FTHG"] < r["FTAG"] else "D"), axis=1)
    for col in played.columns:
        if col not in ex.columns:
            ex[col] = np.nan
    played = pd.concat([played, ex[played.columns]]).drop_duplicates(
        subset=["Date", "HomeTeam", "AwayTeam"]).sort_values("Date").reset_index(drop=True)
    return played


def standings(played):
    pts, n = {}, {}
    for _, m in played.iterrows():
        h, a = m["HomeTeam"], m["AwayTeam"]
        pts.setdefault(h, 0); pts.setdefault(a, 0); n.setdefault(h, 0); n.setdefault(a, 0)
        if m["FTR"] == "H": pts[h] += 3
        elif m["FTR"] == "A": pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
        n[h] += 1; n[a] += 1
    df = pd.DataFrame([{"team": t, "pts": p, "n": n[t]} for t, p in pts.items()])
    df = df.sort_values(["pts", "n"], ascending=[False, True]).reset_index(drop=True)
    df["pos"] = df.index + 1
    return df


def last_match(played, before):
    last = {}
    for _, m in played[played["Date"] < before].iterrows():
        for t in (m["HomeTeam"], m["AwayTeam"]):
            if t not in last or m["Date"] > last[t]:
                last[t] = m["Date"]
    return last


def predict(elo, dc_hist, ad, ahg, aag, date, home, away,
            w=(0.5, 0.5, 0.0), stand=None, last=None, odds=None):
    """w = (peso_elo, peso_dc, peso_mercato). Ritorna P (3,) finale."""
    rh, ra = elo.get(home, 1500.0), elo.get(away, 1500.0)
    if stand is not None:
        for t, sgn in ((home, 1), (away, 1)):
            pos = stand.loc[stand.team == t, "pos"]
            pos = int(pos.iloc[0]) if len(pos) else 10
            adj = 15.0 if (pos <= 4 or pos >= 18) else (-5.0 if 8 <= pos <= 14 else 0.0)
            if t == home: rh += adj
            else: ra += adj
    if last is not None:
        for t in (home, away):
            d = (date - last.get(t, date - pd.Timedelta(days=7))).days
            adj = 20.0 * max(0, 4 - d) if d < 4 else 0.0
            if t == home: rh -= adj
            else: ra -= adj
    P_elo = elo_to_probs(rh, ra, ELO_HFA)
    wts = dc_weights((date - pd.DatetimeIndex(ad)).total_seconds() / 86400.0, DC_HALF_LIFE)
    mu_h = (wts * np.array(ahg)).sum() / wts.sum()
    mu_a = (wts * np.array(aag)).sum() / wts.sum()
    TH = dc_hist.get(home, TeamHistory()); TA = dc_hist.get(away, TeamHistory())
    ohH, dhH, _, daH = TH.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    _, dhA, oaA, _ = TA.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    M = score_matrix(mu_h * ohH * daH, mu_a * oaA * dhH)
    pH, pD, pA, _, _ = matrix_to_markets(M)
    P_dc = np.array([pH, pD, pA])
    parts = [P_elo, P_dc]
    ws = [w[0], w[1]]
    if w[2] > 0 and odds is not None:
        inv = 1 / np.array(odds, float)
        parts.append(inv / inv.sum()); ws.append(w[2])
    P = sum(wi * pi for wi, pi in zip(ws, parts))
    return P / P.sum()


def rps(P, y):
    cp = np.cumsum(P); co = np.zeros(3); co[y] = 1; co = np.cumsum(co)
    return float(np.sum((cp - co) ** 2) / 2)


def eval_matchday(played, fixtures, w=(0.5, 0.5, 0.0), use_stand=False, use_rest=False, label=""):
    """fixtures: DataFrame con Date, HomeTeam, AwayTeam, FTR(risultato), odds=(H,D,A) opzionale."""
    cutoff = fixtures["Date"].min()
    tr = played[played["Date"] < cutoff]
    elo, dc_hist, ad, ahg, aag = train_on_played(tr)
    stand = standings(tr) if use_stand else None
    last = last_match(tr, cutoff) if use_rest else None
    out = []
    for _, f in fixtures.iterrows():
        odds = f.get("odds")
        P = predict(elo, dc_hist, ad, ahg, aag, f["Date"], f["HomeTeam"], f["AwayTeam"],
                    w=w, stand=stand, last=last, odds=odds if isinstance(odds, tuple) else None)
        y = {"H": 0, "D": 1, "A": 2}[f["FTR"]]
        row = {"partita": f"{f['HomeTeam']}-{f['AwayTeam']}", "y": y, "P": P,
               "pick": int(P.argmax()) == y}
        if isinstance(odds, tuple):
            inv = 1 / np.array(odds, float); Pm = inv / inv.sum()
            row["mkt_pick"] = int(Pm.argmax()) == y
            row["rps_mkt"] = rps(Pm, y)
        out.append(row)
    rps_model = np.mean([rps(r["P"], r["y"]) for r in out])
    acc = np.mean([r["pick"] for r in out])
    mkt = [r for r in out if "rps_mkt" in r]
    rps_m = np.mean([r["rps_mkt"] for r in mkt]) if mkt else np.nan
    acc_m = np.mean([r["mkt_pick"] for r in mkt]) if mkt else np.nan
    print(f"  [{label}] RPS modello {rps_model:.4f} | acc {acc*100:.0f}% | "
          f"mercato RPS {rps_m:.4f} | acc {acc_m*100:.0f}%" if mkt else
          f"  [{label}] RPS modello {rps_model:.4f} | acc {acc*100:.0f}%")
    return out, rps_model, acc


def main():
    played = load_played()
    s27 = played[played["Season"] == "2026/2027"].sort_values("Date").reset_index(drop=True)
    # g8 = righe 60-69, g9 = 70-79 (stagione 2026/27 nel CSV arriva a g9); g10 da risultati manuali
    g8 = s27.iloc[60:70].copy()
    g9 = s27.iloc[70:80].copy()
    g10 = pd.DataFrame([{"Date": pd.Timestamp("2026-10-31") + pd.Timedelta(days=i // 5),
                         "HomeTeam": h, "AwayTeam": a,
                         "FTR": "H" if hg > ag else ("A" if hg < ag else "D"),
                         "odds": G10_ODDS[(h, a)]}
                        for (h, a), (hg, ag) in G10_RESULTS.items()
                        for i in [0]])  # date approssimativa, conta solo per rest/standings

    # aggiungi odds alle g8/g9 dalle colonne AvgC del CSV
    for g in (g8, g9):
        g["odds"] = list(zip(g["AvgCH"], g["AvgCD"], g["AvgCA"]))
    fixtures_list = [("g8", g8), ("g9", g9), ("g10", g10)]

    print("🏁 CONFRONTO walk-forward (ogni giornata: addestramento solo su partite PRIMA di essa)\n")
    variants = [
        ("V0 base 50/50", dict(w=(0.5, 0.5, 0.0)), False, False),
        ("V1 +congestione", dict(w=(0.5, 0.5, 0.0)), False, True),
        ("V2 +motivazione", dict(w=(0.5, 0.5, 0.0)), True, True),
    ]
    summary = {}
    for label, kw, us, ur in variants:
        print(f"🔹 {label}")
        tot_rps, tot_acc, n = 0, 0, 0
        for name, g in fixtures_list:
            rows, r, a = eval_matchday(played, g, w=kw["w"], use_stand=us, use_rest=ur, label=name)
            tot_rps += r * len(rows); tot_acc += a * len(rows); n += len(rows)
        summary[label] = (tot_rps / n, tot_acc / n)
        print(f"  → MEDIA {label}: RPS {tot_rps/n:.4f} acc {tot_acc/n*100:.1f}%\n")

    # V3: pesi walk-forward (ottimizzati sulla giornata precedente, con V1+V2 attivi)
    print("🔹 V3 pesi walk-forward (tuned su giornata precedente, grid 0.1) + congestione + motivazione")
    grid = [(a, b, 1 - a - b) for a in np.arange(0, 1.01, 0.1) for b in np.arange(0, 1.01 - a, 0.1)]
    tot_rps, tot_acc, n = 0, 0, 0
    for i, (name, g) in enumerate(fixtures_list):
        if i == 0:
            w = (0.5, 0.5, 0.0)
        else:
            prev = fixtures_list[i - 1][1]
            best_w, best_r = None, 1e9
            for w_c in grid:
                rows, r, _ = eval_matchday(played, prev, w=w_c, use_stand=True, use_rest=True, label="")
                if r < best_r:
                    best_r, best_w = r, w_c
            w = best_w
        print(f"  pesi scelti per {name}: elo {w[0]:.1f} / dc {w[1]:.1f} / mercato {w[2]:.1f}")
        rows, r, a = eval_matchday(played, g, w=w, use_stand=True, use_rest=True, label=name)
        tot_rps += r * len(rows); tot_acc += a * len(rows); n += len(rows)
    summary["V3 walk-forward"] = (tot_rps / n, tot_acc / n)
    print(f"  → MEDIA V3: RPS {tot_rps/n:.4f} acc {tot_acc/n*100:.1f}%\n")

    print("📊 RIEPILOGO (g8+g9+g10, 30 partite):")
    for k, (r, a) in summary.items():
        print(f"  {k:28s} RPS {r:.4f}  acc {a*100:.1f}%")
    print("\n(mercato sulle stesse 30 partite: vedi righe 'mercato' sopra)")


if __name__ == "__main__":
    main()
