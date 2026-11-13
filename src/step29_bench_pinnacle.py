"""🏆 13/11-b BENCH: il nostro modello vs la quota PIÙ SHARP disponibile gratis (Pinnacle close).
Nel validation_multi.csv il "mercato" è la media dei book (AvgC*, include book da ricreativo):
battere la media è facile, battere Pinnacle molto meno. Qui misuriamo entrambe, walk-forward.

RPS = Regola di Brier/normalizzata per 3 esiti: RPS = 0.5 * (Brier su {1,X,2} vincitore)
Uso: python3 src/step29_bench_pinnacle.py
Output: data/bench_pinnacle.csv (per lega) + stampa confronto aggregato.
"""
import os, sys, glob
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
LEAGUES = ["E0", "E1", "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2", "P1", "N1", "T1"]
NAME = {"E0":"Premier League","E1":"Championship","D1":"Bundesliga","D2":"Bundesliga 2","SP1":"LaLiga",
        "SP2":"LaLiga 2","I1":"Serie A","I2":"Serie B","F1":"Ligue 1","F2":"Ligue 2","P1":"Primeira Liga",
        "N1":"Eredivisie","T1":"Super Lig"}


def rps3(P, y):
    """RPS per 3 esiti ordinati (1<X<2): media dei Brier cumulativi."""
    P = np.clip(np.asarray(P, float), 1e-6, 1)
    P = P / P.sum()
    cum_p = np.cumsum(P)[:2]
    oh = np.zeros(3); oh[y] = 1
    cum_o = np.cumsum(oh)[:2]
    return float(np.mean((cum_p - cum_o) ** 2))


def implied(oh, od, oa):
    inv = np.array([1.0 / oh, 1.0 / od, 1.0 / oa])
    return inv / inv.sum()


def load(code):
    rows = []
    for season in ["2526", "2627"]:
        p = os.path.join(DATA, f"{code}_{season}.csv")
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, low_memory=False)
        need = {"FTHG", "FTAG", "PSCH", "PSCD", "PSCA", "AvgCH", "AvgCD", "AvgCA"}
        if not need.issubset(df.columns):
            continue
        df = df.dropna(subset=["FTHG", "FTAG", "PSCH", "PSCD", "PSCA"]).copy()
        df["y"] = np.where(df.FTHG > df.FTAG, 0, np.where(df.FTHG < df.FTAG, 2, 1))
        for _, r in df.iterrows():
            rows.append({"lega": NAME.get(code, code), "season": season, "y": int(r.y),
                         "p_pin": implied(r.PSCH, r.PSCD, r.PSCA),
                         "p_avg": implied(r.AvgCH, r.AvgCD, r.AvgCA),
                         "q_pin": (r.PSCH, r.PSCD, r.PSCA)})
    return rows


def main():
    all_rows = []
    for c in LEAGUES:
        all_rows += load(c)
    if not all_rows:
        print("nessun dato: servono PSCH/PSCD/PSCA nei csv football-data"); return
    out = []
    for lega in sorted({r["lega"] for r in all_rows}):
        sub = [r for r in all_rows if r["lega"] == lega]
        n = len(sub)
        rps_pin = np.mean([rps3(r["p_pin"], r["y"]) for r in sub])
        rps_avg = np.mean([rps3(r["p_avg"], r["y"]) for r in sub])
        # valore atteso di un bet sistematico su Pinnacle (favorito del mercato): sanity
        out.append({"lega": lega, "partite": n,
                    "RPS_pinnacle_close": round(rps_pin, 4),
                    "RPS_media_book": round(rps_avg, 4),
                    "delta (media-pinnacle)": round(rps_avg - rps_pin, 4)})
    d = pd.DataFrame(out).sort_values("partite", ascending=False)
    tot = {"lega": "TOTALE", "partite": sum(o["partite"] for o in out),
           "RPS_pinnacle_close": round(float(np.mean([rps3(r["p_pin"], r["y"]) for r in all_rows])), 4),
           "RPS_media_book": round(float(np.mean([rps3(r["p_avg"], r["y"]) for r in all_rows])), 4)}
    tot["delta (media-pinnacle)"] = round(tot["RPS_media_book"] - tot["RPS_pinnacle_close"], 4)
    d = pd.concat([d, pd.DataFrame([tot])], ignore_index=True)
    print(d.to_string(index=False))
    d.to_csv(os.path.join(DATA, "bench_pinnacle.csv"), index=False)
    print("\n💾 data/bench_pinnacle.csv")
    print("📌 Lettura: se delta > 0, la media dei book è PEGGIORE (RPS più alto) di Pinnacle →")
    print("   il nostro benchmark attuale (media) è più facile da battere del benchmark vero.")


if __name__ == "__main__":
    main()
