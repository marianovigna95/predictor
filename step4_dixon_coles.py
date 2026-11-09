"""
STEP 4 — Modello Dixon-Coles (Poisson bivariata con correzione sui punteggi bassi).

IDEA: stimiamo quanti gol ci aspettiamo da ciascuna squadra (λ casa, λ ospite)
dai dati storici pesati nel tempo, poi calcoliamo la probabilità di OGNI possibile
punteggio esatto (0-0, 1-0, 2-1, ...). Sommando la matrice otteniamo:
  - probabilità 1X2
  - Over/Under 2.5
  - BTTS (entrambe segnano)
La correzione Dixon-Coles (parametro rho) sistema il fatto che 0-0, 1-0, 0-1, 1-1
succedono più spesso di quanto prevede un Poisson "indipendente" puro.

Tutto in walk-forward: per ogni partita usiamo solo le partite PRIMA di quella data.

Uso:  python3 src/step4_dixon_coles.py
Input:  data/matches.csv
Output: data/predictions_dc.csv + metriche a video
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import poisson

DATA = Path(__file__).resolve().parent.parent / "data"

MAX_GOALS = 7          # calcoliamo punteggi fino a 7 gol
RHO = -0.10            # correzione Dixon-Coles (valore classico per i top campionati)
PRIOR_GAMES = 5.0      # "partite fantasma" a media campionato per squadre nuove/poco viste

def dc_weights(days, half_life):
    """Peso esponenziale: una partita di 'half_life' giorni fa pesa la metà."""
    days = np.asarray(days, dtype=float)
    return 0.5 ** (np.maximum(days, 0) / half_life)

class TeamHistory:
    """Tiene la storia di una squadra e stima gol fatti/subiti (casa e trasferta)."""
    def __init__(self):
        self.dates, self.gf, self.ga, self.home = [], [], [], []

    def add(self, date, gf, ga, is_home):
        self.dates.append(date); self.gf.append(gf); self.ga.append(ga); self.home.append(is_home)

    def rates(self, date, mu_home, mu_away, half_life):
        """Ritorna (off_home, def_home, off_away, def_away): gol medi fatti/subiti,
        separati per campo, con prior verso la media di campionato."""
        if len(self.dates) == 0:
            return 1.0, 1.0, 1.0, 1.0   # squadra nuova: rating neutro (ratio 1)
        d = pd.DatetimeIndex(self.dates); gf = np.array(self.gf); ga = np.array(self.ga)
        hm = np.array(self.home, dtype=bool)
        w = dc_weights((pd.Timestamp(date) - d).total_seconds() / 86400.0, half_life)
        def rate(goals, mask, mu):
            num = (w[mask] * goals[mask]).sum() + PRIOR_GAMES * mu
            den = w[mask].sum() + PRIOR_GAMES
            return num / den
        off_home = rate(gf, hm, mu_home) / mu_home
        def_home = rate(ga, hm, mu_home) / mu_home
        off_away = rate(gf, ~hm, mu_away) / mu_away
        def_away = rate(ga, ~hm, mu_away) / mu_away
        return off_home, def_home, off_away, def_away

def score_matrix(lh, la, rho=RHO, max_g=MAX_GOALS):
    """Matrice P(h,a) con correzione Dixon-Coles, normalizzata."""
    ph = poisson.pmf(np.arange(max_g + 1), lh)
    pa = poisson.pmf(np.arange(max_g + 1), la)
    M = np.outer(ph, pa)
    # correzione sui punteggi bassi (rho negativo aumenta 0-0 e 1-1, diminuisce 1-0/0-1)
    M[0, 0] *= 1 - lh * la * rho
    M[0, 1] *= 1 + lh * rho
    M[1, 0] *= 1 + la * rho
    M[1, 1] *= 1 - rho
    return M / M.sum()

def matrix_to_markets(M):
    """Dalla matrice punteggi: 1X2, Over2.5, BTTS."""
    g = np.arange(M.shape[0])
    tot = g[:, None] + g[None, :]
    pH = M[np.tril_indices_from(M, -1)[0] if False else np.where(g[:, None] > g[None, :])].sum()
    pD = M[np.diag_indices_from(M)].sum()
    pA = 1 - pH - pD
    p_over = M[tot > 2].sum()
    p_btts = M[(g[:, None] > 0) & (g[None, :] > 0)].sum()
    return pH, pD, pA, p_over, p_btts

# ---------- metriche ----------
def rps(probs, outcomes):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs); cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def logloss(probs, outcomes):
    p = np.clip(probs[np.arange(len(outcomes)), outcomes], 1e-9, 1)
    return float(-np.mean(np.log(p)))

def bin_logloss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def bin_brier(p, y):
    return float(np.mean((p - y) ** 2))

# ---------- backtest walk-forward ----------
def run_backtest(df, half_life):
    teams = {}
    all_dates, all_hg, all_ag = [], [], []     # per le medie di campionato
    rows = []
    for _, m in df.iterrows():
        date = m["Date"]
        # medie di campionato (gol medi casa/trasferta) sulle partite passate, pesate nel tempo
        if len(all_dates) > 30:
            w = dc_weights((pd.Timestamp(date) - pd.DatetimeIndex(all_dates)).total_seconds() / 86400.0, half_life)
            mu_h = (w * np.array(all_hg)).sum() / w.sum()
            mu_a = (w * np.array(all_ag)).sum() / w.sum()
        else:
            mu_h, mu_a = 1.45, 1.15             # prior iniziale ragionevole per la Serie A

        H = teams.setdefault(m["HomeTeam"], TeamHistory())
        A = teams.setdefault(m["AwayTeam"], TeamHistory())
        ohH, dhH, oaH, daH = H.rates(date, mu_h, mu_a, half_life)
        ohA, dhA, oaA, daA = A.rates(date, mu_h, mu_a, half_life)

        # gol attesi: λ_casa = media_casa * attacco_casa(casa) * difesa_ospite(trasferta)
        lh = mu_h * ohH * daA
        la = mu_a * oaA * dhH
        M = score_matrix(lh, la)
        pH, pD, pA, p_over, p_btts = matrix_to_markets(M)

        rows.append({"Date": date, "Season": m["Season"], "Home": m["HomeTeam"], "Away": m["AwayTeam"],
                     "FTR": m["FTR"], "HG": m["FTHG"], "AG": m["FTAG"],
                     "pH": pH, "pD": pD, "pA": pA, "p_over25": p_over, "p_btts": p_btts,
                     "oddH": m["AvgCH"], "oddD": m["AvgCD"], "oddA": m["AvgCA"],
                     "odd_over": m.get("AvgC>2.5"), "odd_btts": np.nan})

        # aggiorna storia DOPO aver previsto
        H.add(date, m["FTHG"], m["FTAG"], True)
        A.add(date, m["FTAG"], m["FTHG"], False)
        all_dates.append(date); all_hg.append(m["FTHG"]); all_ag.append(m["FTAG"])
    return pd.DataFrame(rows)

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    df = df.dropna(subset=["AvgCH", "AvgCD", "AvgCA"]).sort_values("Date").reset_index(drop=True)
    outcomes = df["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    y_over = (df["FTHG"] + df["FTAG"] > 2.5).astype(float).to_numpy()

    # benchmark di mercato
    odds = df[["AvgCH", "AvgCD", "AvgCA"]].to_numpy(float)
    inv = 1 / odds; mkt = inv / inv.sum(axis=1, keepdims=True)
    print(f"📏 MERCATO (quote chiusura):  1X2 RPS={rps(mkt, outcomes):.4f}  logloss={logloss(mkt, outcomes):.4f}")
    naive = np.tile([1/3]*3, (len(df), 1))
    print(f"📏 CASUALE:                   1X2 RPS={rps(naive, outcomes):.4f}")
    if "AvgC>2.5" in df.columns and df["AvgC>2.5"].notna().any():
        d = df.dropna(subset=["AvgC>2.5", "AvgC<2.5"])
        io = 1 / d[["AvgC>2.5", "AvgC<2.5"]].to_numpy(float)
        mkt_over = (io / io.sum(axis=1, keepdims=True))[:, 0]
        y_o = (d["FTHG"] + d["FTAG"] > 2.5).astype(float).to_numpy()
        print(f"📏 MERCATO Over2.5:           logloss={bin_logloss(mkt_over, y_o):.4f}  brier={bin_brier(mkt_over, y_o):.4f}\n")

    print("🔧 Tuning dell'emivita (half_life, giorni):")
    results = []
    for hl in [90, 180, 365, 730, 1500]:
        pred = run_backtest(df, hl)
        p = pred[["pH", "pD", "pA"]].to_numpy()
        results.append({"half_life": hl,
                        "RPS_1X2": rps(p, outcomes), "logloss_1X2": logloss(p, outcomes),
                        "acc": (p.argmax(axis=1) == outcomes).mean(),
                        "logloss_OU": bin_logloss(pred["p_over25"].to_numpy(), y_over),
                        "brier_OU": bin_brier(pred["p_over25"].to_numpy(), y_over)})
    res = pd.DataFrame(results).sort_values("RPS_1X2")
    print(res.round(4).to_string(index=False))

    best_hl = float(res.iloc[0]["half_life"])
    pred = run_backtest(df, best_hl)
    p = pred[["pH", "pD", "pA"]].to_numpy()
    print(f"\n🏆 half_life migliore: {best_hl:.0f} giorni")
    print(f"   1X2 → RPS={rps(p, outcomes):.4f}  logloss={logloss(p, outcomes):.4f}  accuratezza={(p.argmax(axis=1)==outcomes).mean()*100:.1f}%")
    print(f"   Over2.5 → logloss={bin_logloss(pred['p_over25'].to_numpy(), y_over):.4f}  brier={bin_brier(pred['p_over25'].to_numpy(), y_over):.4f}")
    print(f"   BTTS   → brier={bin_brier(pred['p_btts'].to_numpy(), ((df['FTHG']>0)&(df['FTAG']>0)).astype(float).to_numpy()):.4f}")

    pred["market_pH"], pred["market_pD"], pred["market_pA"] = mkt[:, 0], mkt[:, 1], mkt[:, 2]
    pred["outcome"] = outcomes
    out = DATA / "predictions_dc.csv"
    pred.to_csv(out, index=False)
    print(f"\n💾 Previsioni salvate in {out}")

    pred["ok"] = p.argmax(axis=1) == outcomes
    print("\n📅 Accuratezza per stagione:")
    print(pred.groupby("Season")["ok"].mean().mul(100).round(1).to_string())

if __name__ == "__main__":
    main()
