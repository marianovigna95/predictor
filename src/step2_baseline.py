"""
STEP 2 — Baseline (controllo di realtà).

Domande a cui risponde:
  1. Quanto vince la squadra di casa? Quanto pareggiano? Quanto vincono gli ospiti?
  2. Quanto vince il "favorito" (quota di chiusura più bassa)?
  3. Quanto è frequente Over 2.5 gol?
  4. Quanto bene fa un modello "stupido" che assegna probabilità uniformi? (Brier/RPS di riferimento)

Uso:  python3 src/step2_baseline.py
Input:  data/matches.csv   (creato dallo step 1)
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def rps(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Ranked Probability Score medio (più basso = meglio). 0 = perfetto, ~0.33 = random."""
    # probs: (n, 3) colonne [H, D, A]; outcomes: 0=H, 1=D, 2=A
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs)
    cum_o[np.arange(len(outcomes)), outcomes] = 1.0
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    df = df.dropna(subset=["AvgCH", "AvgCD", "AvgCA"]).copy()
    print(f"Partite con quote di chiusura valide: {len(df)}\n")

    # --- 1. Distribuzione dei risultati ---
    print("📊 Distribuzione risultati (tutte le stagioni):")
    print(df["FTR"].value_counts(normalize=True).mul(100).round(1).to_string())

    print("\n📊 Per stagione:")
    print(df.groupby("Season")["FTR"].value_counts(normalize=True).mul(100).round(1).unstack().to_string())

    # --- 2. Quanto vince il favorito (quota di chiusura più bassa) ---
    odds = df[["AvgCH", "AvgCD", "AvgCA"]].to_numpy()
    fav_idx = np.argmin(odds, axis=1)          # 0=H, 1=D, 2=A
    outcome = df["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    fav_win_rate = (fav_idx == outcome).mean()
    print(f"\n⭐ Il favorito (quota chiusura minima) vince nel {fav_win_rate*100:.1f}% dei casi")
    for th, label in [(1.50, "quota < 1.50"), (2.00, "quota < 2.00"), (3.00, "quota < 3.00")]:
        fav_odds = odds[np.arange(len(df)), fav_idx]
        m = fav_odds < th
        print(f"   - favorito con {label}: vince nel {(fav_idx[m] == outcome[m]).mean()*100:.1f}% dei casi (n={m.sum()})")

    # --- 3. Over 2.5 ---
    over_rate = (df["FTHG"] + df["FTAG"] > 2.5).mean()
    print(f"\n⚽ Over 2.5 gol: {over_rate*100:.1f}% delle partite")
    btts = ((df["FTHG"] > 0) & (df["FTAG"] > 0)).mean()
    print(f"⚽ Entrambe segnano (BTTS): {btts*100:.1f}% delle partite")

    # --- 4. Modello "stupido" di riferimento: probabilità uniformi 1/3 ---
    naive = np.tile([1/3, 1/3, 1/3], (len(df), 1))
    print(f"\n🤖 Modello di riferimento (1/3 a testa): RPS = {rps(naive, outcome):.4f}")
    # Brier per il favorito come evento binario "vince il favorito sì/no"
    brier = np.mean((0.5 - (fav_idx == outcome).astype(float)) ** 2)  # p=0.5 vs risultato favorito
    print(f"🤖 Brier (p=50% sul favorito): {brier:.4f}  → il nostro modello devra battere questi numeri")

    # --- 5. Quanto paga il mercato? (margine) ---
    implied = 1 / odds
    margin = implied.sum(axis=1) - 1
    print(f"\n💰 Margine medio del mercato (overround sulle quote di chiusura): {margin.mean()*100:.1f}%")

if __name__ == "__main__":
    main()
