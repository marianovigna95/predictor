"""
STEP 6 — Ensemble + calibrazione + analisi EV/CLV + simulazione Kelly frazionario.

1. ENSEMBLE: combiniamo le probabilità di Elo, Dixon-Coles e ML
   (media semplice e "log-opinion pool" = media geometrica rinormalizzata).
2. CALIBRAZIONE: verifichiamo che "p=60%" vincа davvero ~60% delle volte (ECE),
   e applichiamo una correzione isotonica (allenata solo sul primo 60% dei dati,
   valutata sul restante 40% per non barare).
3. EV / CLV: per ogni partita, EV = p_modello * quota - 1. Scommettiamo solo se EV > soglia.
   CLV = (quota presa / quota di chiusura) - 1: il vero metro di giudizio.
4. SIMULAZIONE: bankroll con Kelly frazionario (1/4), tetto 5% a giocata.

Uso:  python3 src/step6_ensemble.py
Output: data/predictions_ensemble.csv, data/bets_1x2.csv + stampe a video
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.isotonic import IsotonicRegression

DATA = Path(__file__).resolve().parent.parent / "data"

def rps(probs, outcomes):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs); cum_o[np.arange(len(outcomes)), outcomes] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def logloss(probs, outcomes):
    p = np.clip(probs[np.arange(len(outcomes)), outcomes], 1e-9, 1)
    return float(-np.mean(np.log(p)))

def ece(conf, correct, n_bins=10):
    """Expected Calibration Error subins di confidenza."""
    bins = np.linspace(0, 1, n_bins + 1)
    e = 0.0
    for i in range(n_bins):
        m = (conf > bins[i]) & (conf <= bins[i + 1])
        if m.sum() > 0:
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)

def main():
    feat = pd.read_csv(DATA / "features.csv", parse_dates=["Date"])

    def _key(df, h="Home", a="Away"):
        return df["Date"].dt.strftime("%Y-%m-%d") + "|" + df[h] + "|" + df[a]

    feat["key"] = _key(feat)
    assert feat["key"].is_unique
    y = feat["FTR"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

    def load_pred(fname, cols):
        d = pd.read_csv(DATA / fname, parse_dates=["Date"])
        d["key"] = _key(d)
        assert d["key"].is_unique
        return d.set_index("key").loc[feat["key"], cols].to_numpy(float)

    P_elo = load_pred("predictions_elo.csv", ["pH", "pD", "pA"])
    P_dc = load_pred("predictions_dc.csv", ["pH", "pD", "pA"])
    P_ml = load_pred("predictions_ml.csv", ["ml_pH", "ml_pD", "ml_pA"])
    # quote di chiusura medie, già allineate con le righe di feat
    odds = feat[["oddH", "oddD", "oddA"]].to_numpy(float)
    inv = 1 / odds
    P_mkt = inv / inv.sum(axis=1, keepdims=True)

    def logpool(*ps):
        lp = np.log(np.clip(np.stack(ps), 1e-9, 1)).mean(axis=0)
        return np.exp(lp) / np.exp(lp).sum(axis=1, keepdims=True)

    ensembles = {
        "ELO+DC (media)": (P_elo + P_dc) / 2,
        "ELO+DC+ML (media)": (P_elo + P_dc + P_ml) / 3,
        "ELO+DC+ML (log-pool)": logpool(P_elo, P_dc, P_ml),
        "ELO+DC (log-pool)": logpool(P_elo, P_dc),
    }
    print("🏁 Ensemble vs singoli vs mercato (1X2, RPS più basso = meglio):")
    rows = [("CASUALE", np.tile([1/3]*3, (len(y), 1))), ("ELO", P_elo), ("DIXON-COLES", P_dc),
            ("ML", P_ml), ("MERCATO", P_mkt)] + list(ensembles.items())
    tab = pd.DataFrame([{"modello": n, "RPS": rps(p, y), "logloss": logloss(p, y),
                         "acc%": round((p.argmax(1) == y).mean()*100, 1)} for n, p in rows])
    print(tab.round(4).to_string(index=False))

    best_name = min(ensembles, key=lambda k: rps(ensembles[k], y))
    P_ens = ensembles[best_name]
    print(f"\n🏆 Ensemble migliore: {best_name}  (RPS={rps(P_ens, y):.4f})")

    # ---- calibrazione (isotonica allenata sul primo 60%, testata sul 40%) ----
    split = int(len(y) * 0.6)
    conf = P_ens.max(axis=1)
    correct = (P_ens.argmax(axis=1) == y).astype(float)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(conf[:split], correct[:split])
    conf_cal = iso.predict(conf[split:])
    print(f"\n📏 Calibrazione sul 40% finale: ECE prima = {ece(conf[split:], correct[split:]):.4f}  →  dopo isotonica = {ece(conf_cal, correct[split:]):.4f}")

    # ---- analisi EV / CLV su 1X2 con l'ensemble (metodo corretto) ----
    # Prezzo che otterremmo davvero: AvgC* (chiusura media). Benchmark CLV: Pinnacle closing (PSCC),
    # la linea più "sharp"; se manca, uso la stessa AvgC.
    raw = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    raw["key"] = _key(raw, "HomeTeam", "AwayTeam")
    raw_idx = raw.set_index("key")
    pinn = raw_idx.loc[feat["key"], ["PSCH", "PSCD", "PSCA"]].to_numpy(float)
    has_pinn = ~np.isnan(pinn).any(axis=1)
    closing_line = np.where(has_pinn[:, None], pinn, odds)
    bet_odds = odds.copy()                      # prezzo che otterremmo (chiusura media)

    print("\n💰 Analisi EDGE (ensemble − mercato de-vig), 1X2 — si scommette solo se il modello supera il mercato di almeno X punti %:")
    ev_rows = []
    bet_logs = []
    for thr in [0.01, 0.02, 0.03, 0.05]:
        picks, clvs, wins, rets, evs = [], [], [], [], []
        for i in range(len(y)):
            edge = P_ens[i] - P_mkt[i]          # quanto il modello "vede" in più del mercato
            j = int(np.argmax(edge))
            if edge[j] > thr:
                picks.append(i)
                clvs.append(bet_odds[i, j] / closing_line[i, j] - 1)
                w = 1 if j == y[i] else 0
                wins.append(w)
                rets.append((bet_odds[i, j] - 1) * w - (1 - w))
                evs.append(P_ens[i, j] * bet_odds[i, j] - 1)
        if picks:
            ev_rows.append({"edge >": f"{thr*100:.0f}pp", "n scommesse": len(picks),
                            "win rate%": round(np.mean(wins)*100, 1),
                            "ROI% (flat 1u)": round(np.mean(rets)*100, 1),
                            "EV medio%": round(np.mean(evs)*100, 1),
                            "CLV medio%": round(np.mean(clvs)*100, 2)})
            if thr == 0.02:
                bet_logs = [(feat["Date"].iloc[i], feat["Home"].iloc[i], feat["Away"].iloc[i],
                             ["H", "D", "A"][int(np.argmax(P_ens[i] - P_mkt[i]))],
                             float(bet_odds[i].max()), float(P_ens[i].max()), int(y[i])) for i in picks]
    print(pd.DataFrame(ev_rows).to_string(index=False) if ev_rows else "   nessuna scommessa a queste soglie")

    # scenario "price shopping": best price (MaxC) vs linea sharp Pinnacle closing (PSCC)
    maxc = raw_idx.loc[feat["key"], ["MaxCH", "MaxCD", "MaxCA"]].to_numpy(float)
    has_max = ~np.isnan(maxc).any(axis=1) & has_pinn
    if has_max.sum() > 0:
        clv_shop = (maxc[has_max] / pinn[has_max] - 1)
        print(f"\n🛒 Solo 'price shopping' (best price MaxC vs Pinnacle closing PSCC): "
              f"CLV medio = {clv_shop.mean()*100:.2f}% su {has_max.sum()} partite (senza alcun modello!)")

    # ---- simulazione bankroll con Kelly 1/4, tetto 2% bankroll, edge>2pp ----
    print("\n🎰 Simulazione bankroll (Kelly 1/4, tetto 2% bankroll a giocata, edge>2pp vs mercato):")
    bank = 1.0
    peak = 1.0; maxdd = 0.0
    n_bets = 0
    for i in range(len(y)):
        edge = P_ens[i] - P_mkt[i]
        j = int(np.argmax(edge))
        if edge[j] > 0.02:
            p = P_ens[i, j]; o = bet_odds[i, j]
            f_kelly = (p * o - 1) / (o - 1)
            stake = min(0.25 * max(f_kelly, 0), 0.02) * bank
            if j == y[i]:
                bank += stake * (o - 1)
            else:
                bank -= stake
            n_bets += 1
            peak = max(peak, bank); maxdd = max(maxdd, (peak - bank) / peak)
    print(f"   scommesse piazzate: {n_bets} su {len(y)} partite")
    print(f"   bankroll finale: x{bank:.3f}  → ROI totale = {(bank-1)*100:.1f}%  (max drawdown {maxdd*100:.1f}%)")

    # ---- salva ensemble ----
    out = feat[["Date", "Season", "Home", "Away", "FTR", "oddH", "oddD", "oddA"]].copy()
    out[["ens_pH", "ens_pD", "ens_pA"]] = P_ens
    out["ens_name"] = best_name
    out.to_csv(DATA / "predictions_ensemble.csv", index=False)
    if bet_logs:
        pd.DataFrame(bet_logs, columns=["Date", "Home", "Away", "pick", "quota", "p_modello", "esito"]).to_csv(
            DATA / "bets_1x2.csv", index=False)
    print(f"\n💾 Salvati: predictions_ensemble.csv, bets_1x2.csv")

if __name__ == "__main__":
    main()
