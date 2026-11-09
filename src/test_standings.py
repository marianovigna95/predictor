#!/usr/bin/env python3
"""Test di regressione: standings() deve contare n = partite giocate e ordinare per pts/n.
Esegue: python3 src/test_standings.py  (exit 1 se fallisce)"""
import pandas as pd
from weekly_multi import standings

m = pd.DataFrame([
    {"HomeTeam": "A", "AwayTeam": "B", "FTHG": 2, "FTAG": 1},   # A vince
    {"HomeTeam": "B", "AwayTeam": "A", "FTHG": 0, "FTAG": 0},   # pari
    {"HomeTeam": "C", "AwayTeam": "A", "FTHG": 1, "FTAG": 3},   # A vince in trasferta
])
st = standings(m)
a = st[st.team == "A"].iloc[0]
assert a["n"] == 3, f"n errato: {a['n']} (atteso 3)"
assert a["pts"] == 7, f"pts errati: {a['pts']} (atteso 7)"
assert st.iloc[0]["team"] == "A", "A deve essere 1a"
# righe senza gol non devono contarle
m2 = m._append({"HomeTeam": "A", "AwayTeam": "B", "FTHG": None, "FTAG": None}, ignore_index=True)
st2 = standings(m2)
assert st2[st2.team == "A"].iloc[0]["n"] == 3, "partita senza gol contata!"
print("✅ test_standings OK: n e pts corretti, righe senza gol ignorate")
