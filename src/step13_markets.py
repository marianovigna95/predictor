"""
STEP 13 — TUTTI I MERCATI con probabilità, per una giornata:
  1X2 | GG/NG | Over/Under 2.5 | Marcatore (anytime + primo marcatore) | Ammonito (cartellini)

Dati usati:
  - 1X2 / GG-NG / O-U 2.5 : forecast_giornata<N>.csv (modello v4)
  - cartellini squadra   : colonne HY/AY dei CSV raw football-data (pesati con half-life 180g)
  - marcatore            : xG/90 giocatore (FotMob ultime 45g, fallback stagione Understat)
  - ammonito giocatore   : yellow cards per games (Understat 2026/27)
  - assenze              : data/absences_players.csv (xG → chi è out non può segnare)

Uso:  python3 src/step13_markets.py --giornata 11
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

DATA = Path(__file__).resolve().parent.parent / "data"
HALF_LIFE = 180.0


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def load_cards():
    """Cartellini gialli per squadra per partita (dai CSV raw), con pesi temporali."""
    rows = []
    for f in sorted(DATA.glob("I1_*.csv")):
        try:
            d = pd.read_csv(f, parse_dates=["Date"])
        except Exception:
            continue
        keep = [c for c in ("Date", "HomeTeam", "AwayTeam", "HY", "AY", "HR", "AR") if c in d.columns]
        if "HY" not in keep:
            continue
        rows.append(d[keep])
    c = pd.concat(rows).dropna(subset=["HY", "AY"]).sort_values("Date")
    return c


def team_card_lambda(cards, team, side, as_of):
    """λ cartellini attesi per la squadra (side='H'/'A') pesato nel tempo."""
    col = "HY" if side == "H" else "AY"
    sub = cards[((cards["HomeTeam"] == team) & (side == "H")) |
                ((cards["AwayTeam"] == team) & (side == "A"))]
    sub = sub[sub["Date"] < as_of]
    if len(sub) == 0:
        return 1.6
    days = (as_of - sub["Date"]).dt.days
    w = 0.5 ** (days / HALF_LIFE)
    return float((w * sub[col]).sum() / w.sum())


def player_xg90():
    """xG/90 BLEND per giocatore: 60% recente (FotMob 45g) + 40% stagione (Understat),
    moltiplicato per fattore di conversione del RUOLO (misurato: difensori convertono peggio)."""
    recent, season, role = {}, {}, {}
    px = DATA / "player_xg_fotmob.csv"
    if px.exists():
        df = pd.read_csv(px, parse_dates=["date"])
        cut = df["date"].max() - pd.Timedelta(days=45)
        rec = df[df["date"] >= cut]
        g = rec.groupby(["team", "player"]).agg(xg=("xg", "sum"), min=("min", "sum"))
        for (team, player), r in g.iterrows():
            if r["min"] >= 180:
                recent[(team, _norm(player))] = r["xg"] / (r["min"] / 90.0)
    up = DATA / "understat_players.csv"
    if up.exists():
        u = pd.read_csv(up)
        u26 = u[u["season"] == "2026/2027"]
        for _, r in u26.iterrows():
            k = (r["team"], _norm(r["player"]))
            if r["games"] >= 3:
                season[k] = float(r["xG"]) / r["games"]
            p = str(r.get("position", "")).upper()
            role[k] = 0.8 if p.startswith("D") else (0.05 if p.startswith("G") else 1.0)
    out = {}
    for k in set(recent) | set(season):
        xr = recent.get(k, season.get(k, 0))
        xs = season.get(k, recent.get(k, 0))
        out[k] = (0.6 * xr + 0.4 * xs) * role.get(k, 1.0)
    return out


def team_sot_lambda(as_of):
    """λ tiri in porta attesi per squadra (HST/AST di matches.csv, pesati 180g)."""
    m = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    m = m[m["Date"] < as_of].dropna(subset=["HST", "AST"])
    out = {}
    for team in set(m["HomeTeam"]) | set(m["AwayTeam"]):
        sub = m[((m["HomeTeam"] == team) | (m["AwayTeam"] == team))]
        vals, ws = [], []
        for _, r in sub.iterrows():
            v = r["HST"] if r["HomeTeam"] == team else r["AST"]
            w = 0.5 ** ((as_of - r["Date"]).days / HALF_LIFE)
            vals.append(v); ws.append(w)
        out[team] = float(np.average(vals, weights=ws)) if vals else 3.5
    return out


def player_sot90():
    """Tiri in porta /90 recenti per giocatore (FotMob 45g; fallback ~35% dei tiri Understat)."""
    out = {}
    px = DATA / "player_xg_fotmob.csv"
    if px.exists():
        df = pd.read_csv(px, parse_dates=["date"])
        cut = df["date"].max() - pd.Timedelta(days=45)
        rec = df[df["date"] >= cut]
        g = rec.groupby(["team", "player"]).agg(sot=("sot", "sum"), min=("min", "sum"))
        for (team, player), r in g.iterrows():
            if r["min"] >= 180:
                out[(team, _norm(player))] = r["sot"] / (r["min"] / 90.0)
    up = DATA / "understat_players.csv"
    if up.exists():
        u = pd.read_csv(up)
        if "shots" in u.columns:
            u26 = u[u["season"] == "2026/2027"]
            for _, r in u26.iterrows():
                k = (r["team"], _norm(r["player"]))
                if k not in out and r["games"] >= 3:
                    out[k] = 0.35 * float(r.get("shots", 0)) / r["games"]
    return out


def player_yellow_rate():
    up = DATA / "understat_players.csv"
    out = {}
    if up.exists():
        u = pd.read_csv(up)
        u26 = u[(u["season"] == "2026/2027") & (u.get("yellow", pd.Series(0, index=u.index)) > 0)]
        for _, r in u26.iterrows():
            if r["games"] >= 3:
                out[(r["team"], _norm(r["player"]))] = float(r["yellow"]) / r["games"]
    return out


def injured():
    """Ritorna lista (team, nome_normalizzato); il match è per SOTTOSTRINGA
    (es. 'Thorstvedt' trova 'kristian thorstvedt')."""
    ap = DATA / "absences_players.csv"
    if not ap.exists():
        return []
    d = pd.read_csv(ap)
    return list(zip(d["team"], d["player"].map(_norm)))


def is_out(out_list, team, player_norm):
    pn = _norm(player_norm)
    return any(t == team and (n in pn or pn in n) for t, n in out_list)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giornata", type=int, default=11)
    args = ap.parse_args()
    md = args.giornata

    fc = pd.read_csv(DATA / f"forecast_giornata{md}.csv")
    cards = load_cards()
    xg90 = player_xg90()
    yellow = player_yellow_rate()
    sot90 = player_sot90()
    out_players = injured()
    as_of = pd.Timestamp("2026-11-06")
    sot_lam = team_sot_lambda(as_of)

    # xG squadra recente (per primo marcatore) da FotMob match xG
    fx = pd.read_csv(DATA / "xg_fotmob_2627.csv", parse_dates=["date"])
    fx = fx.sort_values("date")
    cut = fx["date"].max() - pd.Timedelta(days=45)
    team_xg = {}
    for team in set(fx["home"]) | set(fx["away"]):
        sub = fx[((fx["home"] == team) | (fx["away"] == team)) & (fx["date"] >= cut)]
        vals = [r["xgH"] if r["home"] == team else r["xgA"] for _, r in sub.iterrows()]
        team_xg[team] = float(np.mean(vals)) if vals else 1.4

    print(f"\n📊 MERCATI GIORNATA {md} — stime con probabilità (mai certezze!)\n")
    rows = []
    for _, f in fc.iterrows():
        h, a = f["partita"].split(" - ")
        p1, pX, p2 = f["p1%"] / 100, f["pX%"] / 100, f["p2%"] / 100
        p_over = f["Over2.5%"] / 100
        p_gg = f["BTTS%"] / 100
        # cartellini
        as_of = pd.Timestamp("2026-11-06")  # approssima al primo giorno di giornata
        lam = team_card_lambda(cards, h, "H", as_of) + team_card_lambda(cards, a, "A", as_of)
        p_o25, p_o35, p_o45 = (1 - poisson.cdf(k, lam) for k in (2, 3, 4))
        # tiri in porta (SoT): totali e per squadra
        lam_sot = sot_lam.get(h, 3.5) + sot_lam.get(a, 3.5)
        p_sot_o45 = 1 - poisson.cdf(4, lam_sot)
        p_sot_o55 = 1 - poisson.cdf(5, lam_sot)
        p_sot_o65 = 1 - poisson.cdf(6, lam_sot)
        p_sot_h = 1 - poisson.cdf(2, sot_lam.get(h, 3.5))   # O2.5 SoT casa
        p_sot_a = 1 - poisson.cdf(2, sot_lam.get(a, 3.5))   # O2.5 SoT trasferta
        # marcatori: top 2 per squadra (esclusi infortunati)
        scorers = []
        for team in (h, a):
            cands = [(p, v) for (t, p), v in xg90.items() if t == team and not is_out(out_players, t, p)]
            cands.sort(key=lambda x: -x[1])
            txg = team_xg.get(team, 1.4)
            for p, v in cands[:2]:
                p_goal = 1 - np.exp(-v)
                scorers.append(f"{p.title()} ({team[:3]}) {p_goal*100:.0f}% anytime / {v/txg*100:.0f}% primo")
        # ammoniti giocatore: top 2 per partita
        bookers = []
        for team in (h, a):
            cands = [(p, v) for (t, p), v in yellow.items() if t == team and not is_out(out_players, t, p)]
            cands.sort(key=lambda x: -x[1])
            for p, v in cands[:1]:
                bookers.append(f"{p.title()} ({team[:3]}) { (1-np.exp(-v))*100:.0f}%")
        # tiri in porta giocatori: top 2 per partita
        shooters = []
        for team in (h, a):
            cands = [(p, v) for (t, p), v in sot90.items() if t == team and not is_out(out_players, t, p)]
            cands.sort(key=lambda x: -x[1])
            for p, v in cands[:1]:
                shooters.append(f"{p.title()} ({team[:3]}) {(1-np.exp(-v))*100:.0f}%")
        row = {
            "partita": f["partita"],
            "1X2": f"{p1*100:.0f}/{pX*100:.0f}/{p2*100:.0f}",
            "GG%": round(p_gg * 100), "NG%": round((1 - p_gg) * 100),
            "O2.5 gol%": round(p_over * 100), "U2.5 gol%": round((1 - p_over) * 100),
            "cart O4.5%": round(p_o45 * 100), "cart O3.5%": round(p_o35 * 100), "cart O2.5%": round(p_o25 * 100),
            "TiP tot O5.5%": round(p_sot_o55 * 100), "TiP tot O6.5%": round(p_sot_o65 * 100),
            "TiP casa O2.5%": round(p_sot_h * 100), "TiP ospite O2.5%": round(p_sot_a * 100),
            "marcatori": " | ".join(scorers[:4]),
            "tira in porta": " | ".join(shooters[:2]),
            "ammoniti probabili": " | ".join(bookers[:2]),
        }
        rows.append(row)
        print(f"⚽ {f['partita']}")
        print(f"   1X2: {row['1X2']}   GG {row['GG%']}% / NG {row['NG%']}%   O2.5 gol {row['O2.5 gol%']}% / U2.5 {row['U2.5 gol%']}%")
        print(f"   🎯 TIRO IN PORTA: tot O5.5 {row['TiP tot O5.5%']}% · O6.5 {row['TiP tot O6.5%']}% · casa O2.5 {row['TiP casa O2.5%']}% · ospite O2.5 {row['TiP ospite O2.5%']}%  |  giocatori: {row['tira in porta']}")
        print(f"   🟨 cartellini: O4.5 {row['cart O4.5%']}% · O3.5 {row['cart O3.5%']}% · O2.5 {row['cart O2.5%']}%   più probabili: {row['ammoniti probabili']}")
        print(f"   ⚽ marcatori: {row['marcatori']}")
        print()

    pd.DataFrame(rows).to_csv(DATA / f"markets_giornata{md}.csv", index=False)
    print(f"💾 Salvato: {DATA/f'markets_giornata{md}.csv'}")


if __name__ == "__main__":
    main()
