"""
STEP 7 — Pronostici per la GIORNATA 11 di Serie A (6-8 novembre 2026).

Addestra Elo + Dixon-Coles su TUTTE le partite giocate (fino al 29/10/2026)
e genera le probabilità per le 10 partite della prossima giornata:
  - 1X2 (ensemble = media Elo + Dixon-Coles, come nello step 6)
  - Over/Under 2.5 e BTTS (dalla matrice Dixon-Coles)
  - punteggio esatto più probabile

Uso:  python3 src/step7_predict.py
Output: data/predictions_giornata11.csv + tabella a video
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_elo import elo_to_probs, update_elo
from step4_dixon_coles import TeamHistory, score_matrix, matrix_to_markets, dc_weights, PRIOR_GAMES

DATA = Path(__file__).resolve().parent.parent / "data"

ELO_K, ELO_HFA, SHRINK = 48.0, 60.0, 0.70
DC_HALF_LIFE = 180.0

# Giornata 11 di Serie A 2026/27 (da calendario ufficiale Lega)
FIXTURES = [
    ("2026-11-06 20:45", "Venezia", "Udinese"),
    ("2026-11-07 15:00", "Cagliari", "Frosinone"),
    ("2026-11-07 15:00", "Torino", "Lecce"),
    ("2026-11-07 18:00", "Parma", "Bologna"),
    ("2026-11-07 20:45", "Roma", "Sassuolo"),
    ("2026-11-08 12:30", "Napoli", "Lazio"),
    ("2026-11-08 15:00", "Genoa", "Milan"),
    ("2026-11-08 15:00", "Monza", "Atalanta"),
    ("2026-11-08 18:00", "Inter", "Como"),
    ("2026-11-08 20:45", "Fiorentina", "Juventus"),
]

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    print(f"📚 Dati usati per l'addestramento: {len(df)} partite, fino al {df['Date'].max().date()}")

    # ---- replay di Elo e Dixon-Coles su tutte le partite giocate ----
    elo, dc_hist = {}, {}
    all_dates, all_hg, all_ag = [], [], []
    prev_season = None
    for _, m in df.iterrows():
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

    teams_known = set(elo.keys())
    print(f"🏟️ Squadre con rating Elo noti: {len(teams_known)}\n")

    # ---- prévisions per la giornata 11 ----
    rows = []
    for when, home, away in FIXTURES:
        date = pd.Timestamp(when)
        for t in (home, away):
            if t not in teams_known:
                print(f"⚠️  Squadra '{t}' non presente nei dati storici!")
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
        P_dc = np.array([pH, pD, pA])

        P_ens = (P_elo + P_dc) / 2
        P_ens = P_ens / P_ens.sum()
        # punteggio più probabile
        idx = np.unravel_index(np.argmax(M), M.shape)
        top_score = f"{idx[0]}-{idx[1]}"
        pick = ["1", "X", "2"][int(np.argmax(P_ens))]

        rows.append({
            "Data": when, "Casa": home, "Ospite": away,
            "p1%": round(P_ens[0]*100, 1), "pX%": round(P_ens[1]*100, 1), "p2%": round(P_ens[2]*100, 1),
            "Pronostico": pick, "conf%": round(P_ens.max()*100, 1),
            "Over2.5%": round(p_over*100, 1), "BTTS%": round(p_btts*100, 1),
            "Risultato+prob%": f"{top_score} ({M[idx]*100:.0f}%)",
            "lambda_casa": round(lh, 2), "lambda_ospite": round(la, 2),
            "elo_casa": round(rh), "elo_ospite": round(ra),
        })

    out = pd.DataFrame(rows)
    print("⚽ PRONOSTICI GIORNATA 11 — Serie A 2026/27 (ensemble Elo+Dixon-Coles):\n")
    print(out[["Data", "Casa", "Ospite", "p1%", "pX%", "p2%", "Pronostico", "conf%",
               "Over2.5%", "BTTS%", "Risultato+prob%"]].to_string(index=False))

    csv = DATA / "predictions_giornata11.csv"
    out.to_csv(csv, index=False)
    print(f"\n💾 Salvato: {csv}")

if __name__ == "__main__":
    main()
