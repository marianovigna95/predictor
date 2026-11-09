"""
🏆 SCOREBOARD — quanto indovina il modello, giornata per giornata.

Legge le previsioni salvate (data/forecast_giornata<N>.csv) e le confronta
con i risultati reali (da matches.csv, o da results_manual.csv se il CSV ufficiale
è indietro). Calcola: pronostici corretti, RPS del modello e (se ci sono le quote)
del mercato. Aggiorna data/scoreboard.csv.

Uso:  python3 src/scoreboard.py
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def rps(probs, y):
    cum_p = np.cumsum(probs, axis=1)
    cum_o = np.zeros_like(probs); cum_o[np.arange(len(y)), y] = 1
    cum_o = np.cumsum(cum_o, axis=1)
    return float(np.mean(np.sum((cum_p - cum_o) ** 2, axis=1)) / 2)

def main():
    played = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    manual = pd.read_csv(DATA / "results_manual.csv", parse_dates=["date"]) if (DATA / "results_manual.csv").exists() else pd.DataFrame()
    fixtures = pd.read_csv(DATA / "fixtures.csv")
    fixtures["Date"] = pd.to_datetime(fixtures["date"])
    md_lookup = {(r["Date"].normalize(), r["home"], r["away"]): r["matchday"] for _, r in fixtures.iterrows()}

    # risultati chiaveati per (giornata, casa, ospite) — così non si confondono stagioni diverse
    res = {}
    for _, m in played.iterrows():
        k3 = (m["Date"].normalize(), m["HomeTeam"], m["AwayTeam"])
        md = md_lookup.get(k3)
        if md is not None:
            res[(md, m["HomeTeam"], m["AwayTeam"])] = (m["FTHG"], m["FTAG"], m["AvgCH"], m["AvgCD"], m["AvgCA"])
    for _, m in manual.iterrows():
        k = (int(m["matchday"]), m["home"], m["away"])
        if k not in res:
            res[k] = (m["hg"], m["ag"], np.nan, np.nan, np.nan)
    # risultati anche da Understat (xG file contiene tutte le partite giocate con gol)
    ux = DATA / "understat_xg.csv"
    if ux.exists():
        u = pd.read_csv(ux)
        md_map = {}
        for (dd, h, a), mdv in md_lookup.items():
            md_map[(dd.strftime("%Y-%m-%d"), h, a)] = mdv
        for _, r in u.iterrows():
            k = (md_map.get((r["date"], r["home"], r["away"])), r["home"], r["away"])
            if k[0] is not None and k not in res:
                res[k] = (r["hg"], r["ag"], np.nan, np.nan, np.nan)

    rows = []
    for fc in sorted(DATA.glob("forecast_giornata*.csv")):
        md = int(fc.stem.split("giornata")[1])
        pred = pd.read_csv(fc)
        hits, n, rps_vals, mkt_hits, mkt_rps = 0, 0, [], 0, []
        for _, p in pred.iterrows():
            # abbina la partita ai risultati per squadre (casa - ospite)
            key = None
            for (dd, h, a), v in res.items():
                if h == p["partita"].split(" - ")[0] and a == p["partita"].split(" - ")[1]:
                    key = (dd, h, a); break
            if key is None:
                continue
            hg, ag, oh, od, oa = res[key]
            y = 0 if hg > ag else (2 if hg < ag else 1)
            P = np.array([p["p1%"], p["pX%"], p["p2%"]]) / 100
            n += 1
            if P.argmax() == y:
                hits += 1
            rps_vals.append(rps(P[None, :], np.array([y])))
            if not np.isnan(oh):
                inv = 1 / np.array([oh, od, oa], float)
                Pm = inv / inv.sum()
                if Pm.argmax() == y:
                    mkt_hits += 1
                mkt_rps.append(rps(Pm[None, :], np.array([y])))
        if n:
            rows.append({"giornata": md, "partite": n, "modello corretti": hits,
                         "acc%": round(hits / n * 100, 1),
                         "RPS modello": round(np.mean(rps_vals), 4),
                         "mercato corretti": mkt_hits if mkt_hits else "",
                         "RPS mercato": round(np.mean(mkt_rps), 4) if mkt_rps else ""})

    if not rows:
        print("Nessuna giornata con previsioni + risultati da confrontare.")
        return
    sb = pd.DataFrame(rows)
    print("🏆 SCOREBOARD — modello vs realtà (e mercato se disponibile):")
    print(sb.to_string(index=False))
    tot_n = sb["partite"].sum(); tot_h = sb["modello corretti"].sum()
    print(f"\n📊 Totale: {tot_h}/{tot_n} = {tot_h/tot_n*100:.1f}% di pronostici corretti")
    sb.to_csv(DATA / "scoreboard.csv", index=False)
    print(f"💾 Aggiornato: {DATA/'scoreboard.csv'}")

if __name__ == "__main__":
    main()
