"""
🎯 TiP 0.5 GIOCATORI — modello P(almeno 1 tiro in porta) per difensori/centrocampisti.

Idea (richiesta dall'utente): gli attaccanti tirano spesso in porta ma hanno quota bassa;
i difensori/centrocampisti tirano di meno ma a quota più alta → cerchiamo i D/M con
buona probabilità di fare almeno 1 tiro in porta (TiP Over 0.5).

Modello: λ = tasa di tiri in porta ogni 90' (media pesata, half-life 30 gg, ultime 60 gg);
minuti attesi = media minuti ultime 5 partite.  P(≥1 SoT) = 1 - exp(-λ · min/90)  (Poisson).

Uso:  python3 src/player_tip.py --giornata 11
Output: data/player_tip_giornataN.csv  (solo Serie A: i dati FotMob coprono le 20 squadre di A)
        con colonna motivo_verbale in parole + quota_best vuota (da prendere best-price su comparatore ADM).
⚠️ Solo analisi educativa: stime con incertezza, mai certezze. 18+ / ADM / autoesclusione.it / 800 558822.
"""
import argparse
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giornata", type=int, default=11)
    args = ap.parse_args()
    md = args.giornata

    px = pd.read_csv(DATA / "player_xg_fotmob.csv", parse_dates=["date"])
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fx["Date"] = pd.to_datetime(fx["date"])
    g = fx[(fx["league"] == "Serie A") & (fx["matchday"] == md) & (~fx["played"])]
    if g.empty:
        g = fx[(fx["league"] == "Serie A") & (fx["matchday"] == md)]
    teams = sorted(set(g["home"]) | set(g["away"]))
    print(f"🎯 Giornata {md} Serie A — squadre: {', '.join(teams)}")

    # ruolo da Understat (ultima stagione disponibile per giocatore)
    up = pd.read_csv(DATA / "understat_players.csv")
    up = up.sort_values("season")
    ruolo = {}
    for _, r in up.iterrows():
        ruolo[_norm(r["player"])] = (r["position"], r["team"])

    cutoff = px["date"].max()
    rows = []
    for team in teams:
        sub_t = px[px["team"].map(_norm) == _norm(team)]
        for player in sorted(sub_t["player"].unique()):
            sp = sub_t[sub_t["player"].map(_norm) == _norm(player)].sort_values("date")
            rec = sp[sp["date"] >= cutoff - pd.Timedelta(days=60)]
            if len(rec) < 2:
                continue
            days = (cutoff - rec["date"]).dt.days.values
            w = 0.5 ** (days / 30.0)
            lam = (w * rec["sot"].values).sum() / max((w * rec["min"].values / 90.0).sum(), 1e-9)  # SoT/90'
            last5 = sp.tail(5)
            min_exp = float(np.clip(last5["min"].mean(), 30, 90))
            p = 1.0 - np.exp(-lam * min_exp / 90.0)
            pos = ruolo.get(_norm(player), ("?", team))[0]
            # difensori/centrocampisti (no GK, no attaccanti puri F)
            is_dm = ("D" in pos or "M" in pos) and "F" not in pos and "GK" not in pos  # solo D/M puri
            sot_tot = int(rec["sot"].sum())
            motivo = (f"{player} ({team}, ruolo {pos}): nelle ultime {len(rec)} partite ha tirato in porta "
                      f"{sot_tot} volte ({lam:.2f} ogni 90'), giocando in media {min_exp:.0f}' a partita → "
                      f"il modello stima il {p*100:.1f}% che faccia almeno 1 tiro in porta (TiP O0.5). "
                      f"Quota tipica su D/M più alta che sugli attaccanti: prendi la best-price sul comparatore ADM. "
                      f"Stima con incertezza, non una certezza.")
            rows.append({
                "giornata": md, "team": team, "giocatore": player, "ruolo": pos,
                "solo_DM": is_dm, "p_TiP0.5%": round(p * 100, 1), "sot_ogni_90": round(lam, 2),
                "minuti_medi": round(min_exp, 0), "partite_ult60gg": len(rec),
                "sot_ult60gg": sot_tot, "quota_best": "", "motivo_verbale": motivo,
            })
    df = pd.DataFrame(rows).sort_values("p_TiP0.5%", ascending=False)
    out = DATA / f"player_tip_giornata{md}.csv"
    df.to_csv(out, index=False)
    print(f"\n💾 Salvato: {out} ({len(df)} giocatori)")
    dm = df[df["solo_DM"]]
    print(f"\n🎯 Top 12 difensori/centrocampisti per P(TiP O0.5):")
    print(dm.head(12)[["team", "giocatore", "ruolo", "p_TiP0.5%", "sot_ogni_90", "minuti_medi"]].to_string(index=False))


if __name__ == "__main__":
    main()
