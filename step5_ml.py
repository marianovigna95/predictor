"""
STEP 5 — Feature ricche + modello ML (HistGradientBoosting) in walk-forward.

FEATURE (tutte calcolate SOLO con partite precedenti alla data del match, niente leakage):
  - Elo delle due squadre (dallo step 3)
  - λ (gol attesi) e probabilità del modello Dixon-Coles (dallo step 4)
  - forma recente (ultime 5 partite nel rispettivo campo): gol, tiri, tiri in porta, corner, punti
  - giorni di riposo di ciascuna squadra
  - ultimi 5 precedenti diretti (differenza gol)

MODELLO: HistGradientBoostingClassifier ri-allenato ogni 30 giorni su finestra crescente
(expanding window). Confronto finale: ML vs Elo vs Dixon-Coles vs MERCATO.

Uso:  python3 src/step5_ml.py
Input:  data/matches.csv
Output: data/features.csv, data/predictions_ml.csv
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_elo import update_elo                      # riuso la logica Elo
from step4_dixon_coles import (TeamHistory, score_matrix, matrix_to_markets,
                               dc_weights, PRIOR_GAMES)

DATA = Path(__file__).resolve().parent.parent / "data"

ELO_K, ELO_HFA = 48.0, 60.0      # migliori dallo step 3
DC_HALF_LIFE = 180.0             # migliore dallo step 4
N_FORM = 5                       # partite di forma recente

FEATURES = [
    "elo_h", "elo_a", "elo_diff",
    "dc_lh", "dc_la", "dc_pH", "dc_pD", "dc_pA",
    "h5_gf", "h5_ga", "h5_sot", "h5_sh", "h5_corn", "h5_pts",
    "a5_gf", "a5_ga", "a5_sot", "a5_sh", "a5_corn", "a5_pts",
    "rest_h", "rest_a", "h2h_diff5",
]

class FormHistory:
    """Ultimi N match di una squadra, separati per campo."""
    def __init__(self, n=N_FORM):
        self.n = n; self.rec = []   # (date, is_home, gf, ga, sot, sh, corn, pts)
    def add(self, date, is_home, gf, ga, sot, sh, corn, pts):
        self.rec.append((date, is_home, gf, ga, sot, sh, corn, pts))
    def last(self, is_home):
        r = [x for x in self.rec if x[1] == is_home][-self.n:]
        if not r:
            return [np.nan] * 6
        arr = np.array([x[2:] for x in r], dtype=float)
        return arr.mean(axis=0)     # gf, ga, sot, sh, corn, pts

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    elo = {}                 # team -> rating
    dc_hist = {}             # team -> TeamHistory
    form = {}                # team -> FormHistory
    last_date = {}           # team -> ultima data giocata
    h2h = {}                 # (home, away) -> [(date, hg, ag)]
    all_dates, all_hg, all_ag = [], [], []

    for _, m in df.iterrows():
        date = m["Date"]
        # medie di campionato pesate (come nello step 4)
        if len(all_dates) > 30:
            w = dc_weights((pd.Timestamp(date) - pd.DatetimeIndex(all_dates)).total_seconds() / 86400.0, DC_HALF_LIFE)
            mu_h = (w * np.array(all_hg)).sum() / w.sum()
            mu_a = (w * np.array(all_ag)).sum() / w.sum()
        else:
            mu_h, mu_a = 1.45, 1.15

        H = m["HomeTeam"]; A = m["AwayTeam"]
        rh = elo.get(H, 1500.0); ra = elo.get(A, 1500.0)
        elo_diff = rh - ra

        TH = dc_hist.setdefault(H, TeamHistory()); TA = dc_hist.setdefault(A, TeamHistory())
        ohH, dhH, oaH, daH = TH.rates(date, mu_h, mu_a, DC_HALF_LIFE)
        ohA, dhA, oaA, daA = TA.rates(date, mu_h, mu_a, DC_HALF_LIFE)
        lh = mu_h * ohH * daA
        la = mu_a * oaA * dhH
        M = score_matrix(lh, la)
        pH, pD, pA, _, _ = matrix_to_markets(M)

        FH = form.setdefault(H, FormHistory()); FA = form.setdefault(A, FormHistory())
        h5 = FH.last(True); a5 = FA.last(False)

        rest_h = (pd.Timestamp(date) - last_date[H]).days if H in last_date else np.nan
        rest_a = (pd.Timestamp(date) - last_date[A]).days if A in last_date else np.nan

        hh = h2h.get((H, A), [])[-5:]
        h2h_diff5 = np.mean([x[1] - x[2] for x in hh]) if hh else 0.0

        pts = {"H": 3, "D": 1, "A": 0}[m["FTR"]]
        rows.append({
            "Date": date, "Season": m["Season"], "Home": H, "Away": A,
            "FTR": m["FTR"], "HG": m["FTHG"], "AG": m["FTAG"],
            "elo_h": rh, "elo_a": ra, "elo_diff": elo_diff,
            "dc_lh": lh, "dc_la": la, "dc_pH": pH, "dc_pD": pD, "dc_pA": pA,
            "h5_gf": h5[0], "h5_ga": h5[1], "h5_sot": h5[2], "h5_sh": h5[3], "h5_corn": h5[4], "h5_pts": h5[5],
            "a5_gf": a5[0], "a5_ga": a5[1], "a5_sot": a5[2], "a5_sh": a5[3], "a5_corn": a5[4], "a5_pts": a5[5],
            "rest_h": rest_h, "rest_a": rest_a, "h2h_diff5": h2h_diff5,
            "oddH": m["AvgCH"], "oddD": m["AvgCD"], "oddA": m["AvgCA"],
        })

        # aggiorna TUTTE le storie dopo aver calcolato le feature (point-in-time!)
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[m["FTR"]]
        elo[H], elo[A] = update_elo(rh, ra, score, ELO_K, ELO_HFA)
        TH.add(date, m["FTHG"], m["FTAG"], True)
        TA.add(date, m["FTAG"], m["FTHG"], False)
        FH.add(date, True, m["FTHG"], m["FTAG"], m.get("HST", np.nan), m.get("HS", np.nan), m.get("HC", np.nan), pts)
        FA.add(date, False, m["FTAG"], m["FTHG"], m.get("AST", np.nan), m.get("AS", np.nan), m.get("AC", np.nan), 3 - pts if m["FTR"] != "D" else 1)
        last_date[H] = date; last_date[A] = date
        h2h.setdefault((H, A), []).append((date, m["FTHG"], m["FTAG"]))
        all_dates.append(date); all_hg.append(m["FTHG"]); all_ag.append(m["FTAG"])

    return pd.DataFrame(rows)

# ---------- metriche ----------
def rps(probs, outcomes):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs); cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def logloss(probs, outcomes):
    p = np.clip(probs[np.arange(len(outcomes)), outcomes], 1e-9, 1)
    return float(-np.mean(np.log(p)))

def ml_walkforward(feat: pd.DataFrame):
    """Expanding window: ri-allena ogni 30 giorni, prevede le partite siguientes."""
    X = feat[FEATURES].to_numpy(float)
    y = feat["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    dates = feat["Date"].to_numpy()
    n = len(feat)
    probs = np.zeros((n, 3))
    model = None
    last_train = None
    for i in range(n):
        d = pd.Timestamp(dates[i])
        if model is None or i < 300 or (d - last_train).days >= 30:
            if i >= 300:
                model = HistGradientBoostingClassifier(
                    max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                    min_samples_leaf=40, l2_regularization=1.0, random_state=42)
                model.fit(X[:i], y[:i])
                last_train = d
        if model is not None and i >= 300:
            probs[i] = model.predict_proba(X[i:i+1])[0]
        else:
            probs[i] = [0.41, 0.27, 0.32]   # prior dalle frequenze storiche (step 2)
    return probs

def main():
    df = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    df = df.dropna(subset=["AvgCH", "AvgCD", "AvgCA"]).sort_values("Date").reset_index(drop=True)

    print("🔨 Costruisco le feature (walk-forward, point-in-time)...")
    feat = build_features(df)
    feat.to_csv(DATA / "features.csv", index=False)
    print(f"💾 Feature salvate: {DATA/'features.csv'}  ({len(feat)} righe x {len(FEATURES)} feature)")

    print("🤖 Alleno il modello ML in walk-forward (expanding window, retrain ogni 30gg)...")
    probs = ml_walkforward(feat)
    y = feat["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    # confronti dagli step precedenti: stesso ordine righe di feat (stesso df ordinato per data)
    elo_pred = pd.read_csv(DATA / "predictions_elo.csv", parse_dates=["Date"]).reset_index(drop=True)
    dc_pred = pd.read_csv(DATA / "predictions_dc.csv", parse_dates=["Date"]).reset_index(drop=True)
    assert len(elo_pred) == len(feat) and len(dc_pred) == len(feat)
    assert (elo_pred["Date"].values == feat["Date"].values).all() and (dc_pred["Date"].values == feat["Date"].values).all()
    cmp = feat[["Date", "oddH", "oddD", "oddA"]].reset_index(drop=True)
    cmp[["elo_pH", "elo_pD", "elo_pA"]] = elo_pred[["pH", "pD", "pA"]].to_numpy()
    cmp[["dc_pH", "dc_pD", "dc_pA"]] = dc_pred[["pH", "pD", "pA"]].to_numpy()
    odds = cmp[["oddH", "oddD", "oddA"]].to_numpy(float)
    inv = 1 / odds
    mkt = inv / inv.sum(axis=1, keepdims=True)

    rows = []
    for name, p in [("CASUALE", np.tile([1/3]*3, (len(cmp), 1))),
                    ("ELO", cmp[["elo_pH", "elo_pD", "elo_pA"]].to_numpy()),
                    ("DIXON-COLES", cmp[["dc_pH", "dc_pD", "dc_pA"]].to_numpy()),
                    ("ML (HGB)", probs),
                    ("MERCATO", mkt)]:
        rows.append({"modello": name, "RPS": rps(p, y), "logloss": logloss(p, y),
                     "acc%": round((p.argmax(axis=1) == y).mean() * 100, 1)})
    print("\n🏁 Confronto finale (1X2, walk-forward su 1.610 partite):")
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    out = feat[["Date", "Season", "Home", "Away", "FTR"]].copy()
    out[["ml_pH", "ml_pD", "ml_pA"]] = probs
    out.to_csv(DATA / "predictions_ml.csv", index=False)
    print(f"\n💾 Previsioni ML salvate in {DATA/'predictions_ml.csv'}")

if __name__ == "__main__":
    main()
