"""
STEP 8 — Test retrospettivo sulla GIORNATA 10 (31/10 - 2/11/2026).

Addestra Elo + Dixon-Coles SOLO sulle partite giocate PRIMA del 31/10/2026
(cioè fino al 29/10, come se fossimo a sabato mattina), poi prevede le 10 partite
della giornata 10 e le confronta con:
  - i risultati reali
  - le quote di mercato (miglior quota trovata)

Output: tabella partita per partita + accuratezza/RPS di modello vs mercato.

Uso:  python3 src/step8_giornata10.py
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_elo import elo_to_probs, update_elo
from step4_dixon_coles import TeamHistory, score_matrix, matrix_to_markets, dc_weights

DATA = Path(__file__).resolve().parent.parent / "data"

ELO_K, ELO_HFA, SHRINK = 48.0, 60.0, 0.70
DC_HALF_LIFE = 180.0
TRAIN_CUTOFF = pd.Timestamp("2026-10-31")   # il modello "sa" solo fino al 29/10

# Giornata 10 — 2026/27: (data, casa, ospite, gol casa, gol ospite, quote 1/X/2 migliori trovate)
# Nota: Lecce-Genoa e Juventus-Napoli hanno fonti contrastanti; uso i valori più citati.
FIXTURES = [
    ("2026-10-31 15:00", "Bologna", "Monza",      2, 1, (1.67, 3.85, 4.85)),
    ("2026-10-31 18:00", "Udinese", "Roma",       2, 5, (5.55, 4.33, 1.53)),
    ("2026-10-31 20:45", "Milan", "Inter",        3, 1, (3.05, 3.70, 2.18)),
    ("2026-11-01 12:30", "Como", "Venezia",       1, 0, (1.29, 5.83, 8.58)),
    ("2026-11-01 15:00", "Frosinone", "Torino",  3, 1, (2.13, 3.76, 3.01)),
    ("2026-11-01 15:00", "Lazio", "Cagliari",    3, 1, (1.43, 4.42, 7.06)),
    ("2026-11-01 18:00", "Lecce", "Genoa",       0, 0, (3.21, 2.98, 2.35)),
    ("2026-11-01 20:45", "Juventus", "Napoli",   2, 2, (2.24, 3.22, 3.26)),
    ("2026-11-02 18:30", "Sassuolo", "Fiorentina", 3, 1, (2.80, 3.59, 2.35)),
    ("2026-11-02 20:45", "Atalanta", "Parma",    0, 0, (1.48, 4.51, 6.07)),
]

def rps_one(p, y):
    """RPS di una singola partita. p=[pH,pD,pA], y=0/1/2."""
    cum_p = np.cumsum(p)
    cum_o = np.cumsum([1 if i == y else 0 for i in range(3)])
    return float(np.sum((cum_p - cum_o) ** 2) / 2)

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    train = df[df["Date"] < TRAIN_CUTOFF].reset_index(drop=True)
    print(f"📚 Addestramento su {len(train)} partite (fino al {train['Date'].max().date()}) — il modello NON vede la giornata 10\n")

    # replay Elo + DC sul training set
    elo, dc_hist = {}, {}
    all_dates, all_hg, all_ag = [], [], []
    prev_season = None
    for _, m in train.iterrows():
        if m["Season"] != prev_season and prev_season is not None:
            for t in elo:
                elo[t] = 1500 + SHRINK * (elo[t] - 1500)
        prev_season = m["Season"]
        rh, ra = elo.get(m["HomeTeam"], 1500.0), elo.get(m["AwayTeam"], 1500.0)
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[m["FTR"]]
        elo[m["HomeTeam"]], elo[m["AwayTeam"]] = update_elo(rh, ra, score, ELO_K, ELO_HFA)
        dc_hist.setdefault(m["HomeTeam"], TeamHistory()).add(m["Date"], m["FTHG"], m["FTAG"], True)
        dc_hist.setdefault(m["AwayTeam"], TeamHistory()).add(m["Date"], m["FTAG"], m["FTHG"], False)
        all_dates.append(m["Date"]); all_hg.append(m["FTHG"]); all_ag.append(m["FTAG"])

    rows = []
    for when, home, away, hg, ag, odds in FIXTURES:
        date = pd.Timestamp(when)
        w = dc_weights((date - pd.DatetimeIndex(all_dates)).total_seconds() / 86400.0, DC_HALF_LIFE)
        mu_h = (w * np.array(all_hg)).sum() / w.sum()
        mu_a = (w * np.array(all_ag)).sum() / w.sum()
        rh, ra = elo.get(home, 1500.0), elo.get(away, 1500.0)
        P_elo = elo_to_probs(rh, ra, ELO_HFA)
        TH = dc_hist.get(home, TeamHistory()); TA = dc_hist.get(away, TeamHistory())
        ohH, dhH, _, daH = TH.rates(date, mu_h, mu_a, DC_HALF_LIFE)
        _, dhA, oaA, _ = TA.rates(date, mu_h, mu_a, DC_HALF_LIFE)
        lh = mu_h * ohH * daH
        la = mu_a * oaA * dhH
        M = score_matrix(lh, la)
        pH, pD, pA, p_over, p_btts = matrix_to_markets(M)
        P = (P_elo + np.array([pH, pD, pA])) / 2
        P = P / P.sum()

        y = 0 if hg > ag else (2 if hg < ag else 1)
        odd = np.array(odds, float)
        inv = 1 / odd
        P_mkt = inv / inv.sum()

        rows.append({
            "Partita": f"{home} - {away}",
            "p1%": round(P[0]*100, 1), "pX%": round(P[1]*100, 1), "p2%": round(P[2]*100, 1),
            "Pick modello": ["1", "X", "2"][int(P.argmax())],
            "conf%": round(P.max()*100, 1),
            "Risultato": f"{hg}-{ag}", "Esito": ["1", "X", "2"][y],
            "✅/❌ modello": "✅" if P.argmax() == y else "❌",
            "Pick mercato": ["1", "X", "2"][int(P_mkt.argmax())],
            "✅/❌ mercato": "✅" if P_mkt.argmax() == y else "❌",
            "Over2.5%": round(p_over*100, 1), "O/U reale": "Over" if hg + ag > 2 else "Under",
            "rps_modello": round(rps_one(P, y), 3), "rps_mercato": round(rps_one(P_mkt, y), 3),
        })

    out = pd.DataFrame(rows)
    print(out[["Partita", "p1%", "pX%", "p2%", "Pick modello", "conf%", "Risultato", "Esito",
               "✅/❌ modello", "Pick mercato", "✅/❌ mercato", "Over2.5%", "O/U reale"]].to_string(index=False))

    ym = out["Esito"].map({"1": 0, "X": 1, "2": 2}).to_numpy()
    Pm = out[["p1%", "pX%", "p2%"]].to_numpy() / 100
    odds_arr = np.array([r[5] for r in FIXTURES], dtype=float)
    inv = 1 / odds_arr
    Pk = inv / inv.sum(axis=1, keepdims=True)
    print(f"\n📊 RIEPILOGO GIORNADA 10 (10 partite):")
    print(f"   🤖 Modello:  {int((Pm.argmax(1) == ym).sum())}/10 corretti  |  RPS medio = {out['rps_modello'].mean():.4f}")
    print(f"   📈 Mercato:  {int((Pk.argmax(1) == ym).sum())}/10 corretti  |  RPS medio = {out['rps_mercato'].mean():.4f}")
    print(f"   ⚽ Over 2.5 reale: {(out['O/U reale'] == 'Over').sum()}/10 partite")

    out.to_csv(DATA / "predictions_giornata10.csv", index=False)
    print(f"\n💾 Salvato: {DATA/'predictions_giornata10.csv'}")

if __name__ == "__main__":
    main()
