"""
STEP 1 — Carica i CSV grezzi di football-data.co.uk (Top 5 + leghe extra) e crea un unico dataset pulito.

Uso:  python3 src/step1_load_data.py
Input:  data/I1_*.csv, E0_*.csv, SP1_*.csv, D1_*.csv, F1_*.csv  (football-data.co.uk)
Output: data/matches.csv  (una riga per partita, tutte le leghe e stagioni, colonna League)
"""
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SEASONS = ["2223", "2324", "2425", "2526", "2627"]

LEAGUES = {
    "I1": "Serie A",
    "E0": "Premier League",
    "SP1": "LaLiga",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
    # 🆕 leghe extra con storico gratis football-data (aggiunte 04/11/2026)
    "I2": "Serie B",
    "E1": "Championship",
    "N1": "Eredivisie",
    "P1": "Primeira Liga",
    "T1": "Süper Lig",
    "D2": "Bundesliga 2",
    "SP2": "LaLiga 2",
    "F2": "Ligue 2",
}

# Colonne che ci interessano (le teniamo se esistono nel file di quella stagione)
KEEP = [
    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
    "HxG", "AxG", "HS", "AS", "HST", "AST", "HC", "AC",
    # quote: AvgH/D/A = apertura media mercato, AvgCH/CD/CA = chiusura media (CLV)
    "AvgH", "AvgD", "AvgA", "MaxH", "MaxD", "MaxA",
    "AvgCH", "AvgCD", "AvgCA", "MaxCH", "MaxCD", "MaxCA",
    "Avg>2.5", "Avg<2.5", "AvgC>2.5", "AvgC<2.5",
    "B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA",
    "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA",  # Pinnacle (prezzo "sharp")
    "Referee",
]

def load_season(code: str, season: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{code}_{season}.csv", encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    df["Season"] = f"20{season[:2]}/20{season[2:]}"
    df["League"] = LEAGUES[code]
    df["Div"] = code
    # Date: formati diversi tra stagioni (gg/mm/aaaa oppure gg/mm/aa)
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce") \
                  .fillna(pd.to_datetime(df["Date"], format="%d/%m/%y", errors="coerce"))
    keep = ["League", "Div", "Season"] + [c for c in KEEP if c in df.columns]
    return df[keep]

def main():
    frames = [load_season(code, s) for code in LEAGUES for s in SEASONS]
    all_matches = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)

    # Solo partite con risultato valido
    all_matches = all_matches.dropna(subset=["FTHG", "FTAG", "HomeTeam", "AwayTeam"])
    all_matches[["FTHG", "FTAG"]] = all_matches[["FTHG", "FTAG"]].astype(int)

    out = DATA / "matches.csv"
    all_matches.to_csv(out, index=False)

    print(f"✅ Salvato: {out}")
    print(f"   Partite totali: {len(all_matches)}")
    print("\n📊 Partite per lega e stagione:")
    print(all_matches.pivot_table(index="League", columns="Season", values="FTHG", aggfunc="count").to_string())

if __name__ == "__main__":
    main()
