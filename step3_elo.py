"""
STEP 3 — Primo modello vero: ELO ratings + backtest walk-forward.

IDEA (semplice): ogni squadra ha un punteggio di "forza" (Elo, часть da 1500).
Dopo ogni partita il punteggio si aggiorna: vinci → sali, perdi → scendi,
di una quantità proporzionale a quanto il risultato era "sorpresa".
Prima di ogni partita, il modello converte la differenza Elo in probabilità 1X2.

BACKTEST WALK-FORWARD: scorriamo le partite in ordine cronologico e, per ognuna,
facciamo la previsione usando SOLO i punteggi Elo aggiornati fino a quel giorno,
poi aggiorniamo l'Elo col risultato vero. Così testiamo il modello "nel passato",
esattamente come lo useremmo davvero.

Uso:  python3 src/step3_elo.py
Input:  data/matches.csv
Output: data/predictions_elo.csv  +  stampa metriche a video
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# ---------- parametri del modello ----------
HFA = 100.0          # vantaggio casa in punti Elo (da calibrare)
K = 32.0             # velocità di aggiornamento Elo
SHRINK = 0.70        # a inizio stagione i punteggi tornano verso 1500 (nuove squadre, mercato)
DRAW_BASE = 0.27     # frequenza storica dei pareggi in Serie A (dallo step 2)

def elo_to_probs(rh: float, ra: float, hfa: float = HFA) -> np.ndarray:
    """Da differenza Elo a probabilità [P(casa), P(pareggio), P(ospite)]."""
    diff = rh - ra + hfa                       # casa favorita se diff > 0
    p_home_raw = 1.0 / (1.0 + 10 ** (-diff / 400.0))   # curva Elo standard
    # i pareggi sono più probabili quando le squadre sono equilibrate
    p_draw = DRAW_BASE * (1 + np.exp(-abs(diff) / 200.0)) / 2
    p_draw = min(p_draw, 0.45)
    rest = 1 - p_draw
    return np.array([p_home_raw * rest, p_draw, (1 - p_home_raw) * rest])

def update_elo(rh, ra, score_home, k, hfa):
    """Aggiorna i punteggi dopo la partita. score_home: 1, 0.5 o 0."""
    exp_home = 1.0 / (1.0 + 10 ** (-(rh - ra + hfa) / 400.0))
    rh_new = rh + k * (score_home - exp_home)
    ra_new = ra + k * ((1 - score_home) - (1 - exp_home))
    return rh_new, ra_new

# ---------- metriche ----------
def rps(probs, outcomes):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs); cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def logloss(probs, outcomes):
    p = np.clip(probs[np.arange(len(outcomes)), outcomes], 1e-9, 1)
    return float(-np.mean(np.log(p)))

def accuracy(probs, outcomes):
    return float(np.mean(np.argmax(probs, axis=1) == outcomes))

# ---------- backtest walk-forward ----------
def run_backtest(df, k, hfa, shrink):
    ratings = {}          # team -> elo
    rows = []
    prev_season = None
    for _, m in df.iterrows():
        if m["Season"] != prev_season and prev_season is not None:
            # inizio nuova stagione: regressione verso la media (promosse/retrocesse)
            for t in ratings:
                ratings[t] = 1500 + shrink * (ratings[t] - 1500)
        prev_season = m["Season"]

        rh = ratings.get(m["HomeTeam"], 1500.0)
        ra = ratings.get(m["AwayTeam"], 1500.0)
        probs = elo_to_probs(rh, ra, hfa)
        outcome = {"H": 0, "D": 1, "A": 2}[m["FTR"]]
        rows.append({"Date": m["Date"], "Season": m["Season"], "Home": m["HomeTeam"],
                     "Away": m["AwayTeam"], "FTR": m["FTR"],
                     "pH": probs[0], "pD": probs[1], "pA": probs[2],
                     "oddH": m["AvgCH"], "oddD": m["AvgCD"], "oddA": m["AvgCA"]})
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[m["FTR"]]
        ratings[m["HomeTeam"]], ratings[m["AwayTeam"]] = update_elo(rh, ra, score, k, hfa)
    return pd.DataFrame(rows)

def market_probs(df):
    """Probabilità implicite dalle quote di chiusura, senza margine (de-vig)."""
    odds = df[["AvgCH", "AvgCD", "AvgCA"]].to_numpy(float)
    inv = 1.0 / odds
    return inv / inv.sum(axis=1, keepdims=True)

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    df = df.dropna(subset=["AvgCH", "AvgCD", "AvgCA"]).sort_values("Date").reset_index(drop=True)
    outcomes = df["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    # --- baseline di confronto ---
    naive = np.tile([1/3, 1/3, 1/3], (len(df), 1))
    mkt = market_probs(df)
    print(f"📏 Riferimento  modello casuale (1/3):        RPS={rps(naive, outcomes):.4f}  logloss={logloss(naive, outcomes):.4f}")
    print(f"📏 Riferimento  MERCATO (quote chiusura):    RPS={rps(mkt, outcomes):.4f}  logloss={logloss(mkt, outcomes):.4f}  acc={accuracy(mkt, outcomes)*100:.1f}%")
    print(f"📏 Da battere: RPS < {rps(naive, outcomes):.4f} (casuale) e possibilmente < {rps(mkt, outcomes):.4f} (mercato)\n")

    # --- piccolo tuning di K e HFA (sempre in walk-forward) ---
    print("🔧 Tuning di K (velocità Elo) e HFA (vantaggio casa):")
    results = []
    for k in [20, 32, 48, 64]:
        for hfa in [60, 100, 140]:
            pred = run_backtest(df, k, hfa, SHRINK)
            p = pred[["pH", "pD", "pA"]].to_numpy()
            results.append({"K": k, "HFA": hfa, "RPS": rps(p, outcomes),
                            "logloss": logloss(p, outcomes), "acc": accuracy(p, outcomes)})
    res = pd.DataFrame(results).sort_values("RPS")
    print(res.round(4).to_string(index=False))

    best = res.iloc[0]
    print(f"\n🏆 Migliore: K={best['K']}, HFA={best['HFA']}  →  RPS={best['RPS']:.4f}, logloss={best['logloss']:.4f}, accuratezza={best['acc']*100:.1f}%")

    # --- backtest finale col best e salvataggio previsioni ---
    pred = run_backtest(df, float(best["K"]), float(best["HFA"]), SHRINK)
    pred["market_pH"] = mkt[:, 0]; pred["market_pD"] = mkt[:, 1]; pred["market_pA"] = mkt[:, 2]
    pred["outcome"] = outcomes
    out = DATA / "predictions_elo.csv"
    pred.to_csv(out, index=False)
    print(f"\n💾 Previsioni salvate in {out} ({len(pred)} partite)")

    # --- come si comporta vs il mercato, per stagione ---
    pred["ok"] = (pred[["pH", "pD", "pA"]].to_numpy().argmax(axis=1) == pred["outcome"])
    print("\n📅 Accuratezza del modello per stagione (walk-forward):")
    print(pred.groupby("Season")["ok"].mean().mul(100).round(1).to_string())

if __name__ == "__main__":
    main()
