"""
🔮 PREVISIONI SETTIMANALI AUTOMATICHE — Serie A 2026/27

Fa tutto da solo:
  1. scarica l'ultimo CSV della stagione in corso da football-data.co.uk
  2. ricrea data/matches.csv (dataset pulito)
  3. sceglie la prossima giornata da pronosticare usando data/fixtures.csv
     (usa --date AAAA-MM-GG per forzare una giornata, es. --date 2026-11-06)
  4. addestra Elo + Dixon-Coles su TUTTE le partite giocate
  5. stampa i pronostici (1X2, Over 2.5, BTTS, risultato più probabile)
     e salva data/forecast_<data>.csv

Uso:
  python3 src/weekly_forecast.py                 # prossima giornata automatica
  python3 src/weekly_forecast.py --date 2026-11-06
"""
import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step1_load_data                      # step 1: rebuild matches.csv
from step3_elo import elo_to_probs, update_elo
from step4_dixon_coles import (TeamHistory, score_matrix, matrix_to_markets,
                               dc_weights)
from motivi import motivo_match, frase_motivo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SEASON = "2627"
URL = f"https://www.football-data.co.uk/mmz4281/{SEASON}/I1.csv"

ELO_K, ELO_HFA, SHRINK = 48.0, 60.0, 0.70      # migliori parametri trovati negli step 3-6
DC_HALF_LIFE = 180.0


def xg_proxy(goals, sot, shots):
    """xG-proxy dai tiri (calibrato perché la media sia ≈ ai gol reali di Serie A)."""
    if pd.isna(sot) or pd.isna(shots):
        return float(goals)
    return 0.05 * shots + 0.20 * sot


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def load_absences():
    """Penalità Elo per assenze.
    - data/absences_players.csv (team,player): calcolo SMART dagli xG dei giocatori
      (data/player_xg_fotmob.csv): penalty ∝ quota xG del giocatore mancante.
    - data/absences.csv (team,elo_penalty): fallback manuale."""
    px, ap = DATA / "player_xg_fotmob.csv", DATA / "absences_players.csv"
    if px.exists() and ap.exists():
        df = pd.read_csv(px, parse_dates=["date"])
        apd = pd.read_csv(ap)
        pens, detail = {}, []
        for team, grp in apd.groupby("team"):
            sub = df[df["team"].map(_norm) == _norm(team)]
            if sub.empty:
                continue
            cutoff = sub["date"].max() - pd.Timedelta(days=45)
            rec = sub[sub["date"] >= cutoff]
            n_matches = rec["date"].nunique()
            team_xg90 = rec["xg"].sum() / max(n_matches, 1)
            if team_xg90 <= 0:
                continue
            missing = 0.0
            for _, r in grp.iterrows():
                p = rec[rec["player"].map(_norm) == _norm(r["player"])]
                if len(p) and p["min"].sum() > 0:
                    missing += p["xg"].sum() / (p["min"].sum() / 90.0)  # xG/90 del giocatore
                    detail.append(f"{r['player']} ({p['xg'].sum():.1f}xG)")
                else:
                    missing += 0.10 * team_xg90  # nome non trovato: stima prudente
            pens[team] = int(round(min(70, 150 * missing / team_xg90)))
        if pens:
            print(f"🚑 Assenze da xG giocatori: {pens} | [{', '.join(detail[:8])}...]")
            return pens
    p = DATA / "absences.csv"
    if p.exists():
        d = pd.read_csv(p)
        return dict(zip(d["team"], d["elo_penalty"]))
    return {}


def download_latest_csv():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    (DATA / f"I1_{SEASON}.csv").write_bytes(urllib.request.urlopen(req, timeout=30).read())
    print(f"⬇️  Scaricato {URL}")


def load_understat_xg():
    """Mappa (date,home,away) -> (xgH, xgA) dagli xG REALI Understat (tutte le stagioni)."""
    p = DATA / "understat_xg.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p)
    return {(r["date"], r["home"], r["away"]): (r["xgH"], r["xgA"]) for _, r in d.iterrows()}


def train_on_played(played: pd.DataFrame):
    """Replay di Elo + Dixon-Coles su tutte le partite giocate. Ritorna gli stati finali."""
    uxg = load_understat_xg()
    # calibrazione xG-proxy (solo dove manca l'xG reale HxG/AxG): scala = somma gol / somma proxy
    ph = played.apply(lambda m: xg_proxy(m["FTHG"], m.get("HST"), m.get("HS")), axis=1)
    pa = played.apply(lambda m: xg_proxy(m["FTAG"], m.get("AST"), m.get("AS")), axis=1)
    mask = played["HxG"].isna() & ~(ph.isna() | pa.isna()) if "HxG" in played else ~(ph.isna() | pa.isna())
    scale_h = played.loc[mask, "FTHG"].sum() / ph[mask].sum() if mask.any() else 1.0
    scale_a = played.loc[mask, "FTAG"].sum() / pa[mask].sum() if mask.any() else 1.0
    print(f"⚙️  Calibrazione xG-proxy: scale casa x{scale_h:.2f}, trasferta x{scale_a:.2f} "
          f"(xG reali HxG/AxG usati dove presenti: {int(played['HxG'].notna().sum()) if 'HxG' in played else 0} partite)")

    elo, dc_hist = {}, {}
    all_dates, all_hg, all_ag = [], [], []
    prev_season = None
    for _, m in played.iterrows():
        if m["Season"] != prev_season and prev_season is not None:
            for t in elo:
                elo[t] = 1500 + SHRINK * (elo[t] - 1500)
        prev_season = m["Season"]
        rh, ra = elo.get(m["HomeTeam"], 1500.0), elo.get(m["AwayTeam"], 1500.0)
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[m["FTR"]]
        elo[m["HomeTeam"]], elo[m["AwayTeam"]] = update_elo(rh, ra, score, ELO_K, ELO_HFA)
        # xG REALE Understat (tutte le stagioni) → HxG/AxG football-data → xG-proxy dai tiri
        key = (m["Date"].strftime("%Y-%m-%d"), m["HomeTeam"], m["AwayTeam"])
        if key in uxg:
            gf, ga = uxg[key]
        elif "HxG" in m.index and pd.notna(m["HxG"]):
            gf, ga = float(m["HxG"]), float(m["AxG"])
        else:
            gf = xg_proxy(m["FTHG"], m.get("HST"), m.get("HS")) * scale_h
            ga = xg_proxy(m["FTAG"], m.get("AST"), m.get("AS")) * scale_a
        dc_hist.setdefault(m["HomeTeam"], TeamHistory()).add(m["Date"], gf, ga, True)
        dc_hist.setdefault(m["AwayTeam"], TeamHistory()).add(m["Date"], ga, gf, False)
        all_dates.append(m["Date"]); all_hg.append(gf); all_ag.append(ga)
    return elo, dc_hist, all_dates, all_hg, all_ag


def standings(played):
    """Classifica (punti, partite) dalle partite giocate — per la motivazione."""
    pts, n = {}, {}
    for _, m in played.iterrows():
        h, a = m["HomeTeam"], m["AwayTeam"]
        pts.setdefault(h, 0); pts.setdefault(a, 0); n.setdefault(h, 0); n.setdefault(a, 0)
        if m["FTR"] == "H": pts[h] += 3
        elif m["FTR"] == "A": pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
        n[h] += 1; n[a] += 1
    df = pd.DataFrame([{"team": t, "pts": p, "n": n[t]} for t, p in pts.items()],
                      columns=["team", "pts", "n"])
    if df.empty:
        return pd.DataFrame(columns=["team", "pts", "n", "pos"])
    df = df.sort_values(["pts", "n"], ascending=[False, True]).reset_index(drop=True)
    df["pos"] = df.index + 1
    return df


def last_match(played, before):
    """Ultima partita giocata da ogni squadra prima di `before` — per la congestione."""
    last = {}
    for _, m in played[played["Date"] < before].iterrows():
        for t in (m["HomeTeam"], m["AwayTeam"]):
            if t not in last or m["Date"] > last[t]:
                last[t] = m["Date"]
    return last


def predict_match(elo, dc_hist, all_dates, all_hg, all_ag, date, home, away,
                  stand=None, last=None, weights=(0.4, 0.4, 0.2), odds=None):
    w = dc_weights((date - pd.DatetimeIndex(all_dates)).total_seconds() / 86400.0, DC_HALF_LIFE)
    mu_h = (w * np.array(all_hg)).sum() / w.sum()
    mu_a = (w * np.array(all_ag)).sum() / w.sum()
    rh, ra = elo.get(home, 1500.0), elo.get(away, 1500.0)
    # 🏟️ motivazione da classifica (top4 / ultime3 → +15, centro-tabella → -5)
    if stand is not None:
        for t in (home, away):
            pos = stand.loc[stand.team == t, "pos"]
            pos = int(pos.iloc[0]) if len(pos) else 10
            adj = 15.0 if (pos <= 4 or pos >= 18) else (-5.0 if 8 <= pos <= 14 else 0.0)
            if t == home: rh += adj
            else: ra += adj
    # 😮‍💨 congestione: penalità se l'ultima partita è a < 4 giorni
    if last is not None:
        for t in (home, away):
            d = (date - last.get(t, date - pd.Timedelta(days=7))).days
            adj = 20.0 * max(0, 4 - d) if d < 4 else 0.0
            if t == home: rh -= adj
            else: ra -= adj
    P_elo = elo_to_probs(rh, ra, ELO_HFA)
    TH = dc_hist.get(home, TeamHistory()); TA = dc_hist.get(away, TeamHistory())
    ohH, dhH, _, daH = TH.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    _, dhA, oaA, _ = TA.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    lh = mu_h * ohH * daH
    la = mu_a * oaA * dhH
    M = score_matrix(lh, la)
    pH, pD, pA, p_over, p_btts = matrix_to_markets(M)
    P_dc = np.array([pH, pD, pA])
    # ensemble: Elo + DC + (se ci sono le quote) mercato — pesi da convalida step10
    w_elo, w_dc, w_mkt = weights
    parts, ws = [P_elo, P_dc], [w_elo, w_dc]
    if w_mkt > 0 and odds is not None:
        inv = 1 / np.array(odds, float)
        parts.append(inv / inv.sum()); ws.append(w_mkt)
    P = sum(wi * pi for wi, pi in zip(ws, parts))
    P = P / P.sum()
    idx = np.unravel_index(np.argmax(M), M.shape)
    return P, p_over, p_btts, f"{idx[0]}-{idx[1]}", M[idx], rh, ra, lh, la


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="forza la giornata, es. 2026-11-06")
    args = ap.parse_args()

    download_latest_csv()
    step1_load_data.main()                      # ricrea data/matches.csv

    played = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    # partite nuove prese da FotMob (xG reali + risultati recenti, es. g10)
    extra_p = DATA / "matches_extra.csv"
    if extra_p.exists():
        ex = pd.read_csv(extra_p, parse_dates=["Date"])
        ex["Season"] = "2026/2027"
        ex["FTR"] = ex.apply(lambda r: "H" if r["FTHG"] > r["FTAG"] else ("A" if r["FTHG"] < r["FTAG"] else "D"), axis=1)
        for col in played.columns:
            if col not in ex.columns:
                ex[col] = np.nan
        ex = ex[played.columns]
        played = pd.concat([played, ex]).drop_duplicates(
            subset=["Date", "HomeTeam", "AwayTeam"]).sort_values("Date")
        print(f"➕ Aggiunte {len(ex)} partite da matches_extra.csv (FotMob)")
    fixtures = pd.read_csv(DATA / "fixtures.csv")
    fixtures["Date"] = pd.to_datetime(fixtures["date"])
    # calendario automatico completo da FotMob (tutta la stagione, g1-g38)
    fx = DATA / "fixtures_fotmob.csv"
    if fx.exists():
        ff = pd.read_csv(fx)
        ff["Date"] = pd.to_datetime(ff["date"])
        fixtures = pd.concat([fixtures, ff], ignore_index=True).drop_duplicates(
            subset=["matchday", "home", "away"])
        print(f"📅 Calendario: {len(fixtures)} partite totali (fixtures.csv + FotMob fino a g{fixtures['matchday'].max()})")

    # risultati noti da TUTTE le fonti: matches.csv + extra + manuali + Understat
    played_keys = set(zip(played["Date"].dt.normalize(), played["HomeTeam"], played["AwayTeam"]))
    for src, dcol in (("understat_xg.csv", "date"), ("results_manual.csv", "date")):
        p = DATA / src
        if p.exists():
            d = pd.read_csv(p)
            played_keys |= set(zip(pd.to_datetime(d[dcol]).dt.normalize(), d["home"], d["away"]))
    if args.date:
        target_md = int(fixtures.loc[fixtures["Date"].dt.normalize() == pd.Timestamp(args.date).normalize(),
                                     "matchday"].iloc[0])
    else:
        # prossima giornata = la prima giornata (in ordine) con almeno una partita non ancora nei risultati
        def md_unplayed(m):
            sub = fixtures[fixtures["matchday"] == m]
            return not all((r["Date"].normalize(), r["home"], r["away"]) in played_keys
                           for _, r in sub.iterrows())
        candidates = [m for m in sorted(fixtures["matchday"].unique()) if md_unplayed(m)]
        if not candidates:
            print("✅ Tutte le partite di fixtures.csv risultano giocate: aggiorna data/fixtures.csv con le prossime giornate!")
            return
        target_md = candidates[0]

    md = fixtures[fixtures["matchday"] == target_md].sort_values("Date")
    print(f"\n🎯 Giornata da pronosticare: n.{target_md} (dal {md['Date'].min().date()}, {len(md)} partite)")
    print(f"📚 Addestramento su {len(played)} partite giocate (fino al {played['Date'].max().date()})\n")

    elo, dc_hist, ad, ahg, aag = train_on_played(played)

    # 4) applica le penalità per assenze (infortuni/squalifiche da news)
    absences = load_absences()
    for t, pen in absences.items():
        elo[t] = elo.get(t, 1500.0) - pen
    if absences:
        print(f"🚑 Assenze applicate: {absences}")

    # 3) quote attuali della giornata (se inserite a mano in data/odds_giornata<N>.csv) → report edge
    odds_file = DATA / f"odds_giornata{target_md}.csv"
    odds_map = {}
    if odds_file.exists():
        od = pd.read_csv(odds_file)
        for _, r in od.iterrows():
            odds_map[(r["home"], r["away"])] = (r["oddH"], r["oddD"], r["oddA"])
        print(f"📈 Quote trovate in {odds_file.name}: confronto modello vs mercato attivo")

    # 🏟️ classifica e ultime partite → motivazione + congestione (validati nello step 10)
    stand = standings(played)
    last = last_match(played, md["Date"].min())
    # per il MOTIVO mostro classifica/riposo della sola Serie A (matches.csv è multi-lega)
    played_sa = played[played["League"] == "Serie A"] if "League" in played else played
    stand_sa = standings(played_sa)
    last_sa = last_match(played_sa, md["Date"].min())

    rows = []
    for _, f in md.iterrows():
        key = (f["home"], f["away"])
        odds = odds_map.get(key)
        weights = (0.4, 0.4, 0.2) if odds is not None else (0.5, 0.5, 0.0)
        P, p_over, p_btts, top, top_p, rh, ra, lh, la = predict_match(
            elo, dc_hist, ad, ahg, aag, f["Date"], f["home"], f["away"],
            stand=stand, last=last, weights=weights, odds=odds)
        pick = ["1", "X", "2"][int(P.argmax())]
        pick_idx = int(P.argmax())
        quota_pick = odds[pick_idx] if odds is not None else None
        row = {
            "orario": f["Date"].strftime("%d/%m %H:%M"), "partita": f"{f['home']} - {f['away']}",
            "p1%": round(P[0]*100, 1), "pX%": round(P[1]*100, 1), "p2%": round(P[2]*100, 1),
            "pronostico": pick, "conf%": round(P.max()*100, 1),
            "Over2.5%": round(p_over*100, 1), "BTTS%": round(p_btts*100, 1),
            "risultato+prob%": f"{top} ({top_p*100:.0f}%)",
            "motivo": motivo_match(f["home"], f["away"], f["Date"], played_sa, rh, ra, lh, la,
                                   stand=stand_sa, last=last_sa, P=P, pick=pick_idx,
                                   quota_best=quota_pick, absences=absences, elo_raw=elo),
            "motivo_verbale": frase_motivo(f["home"], f["away"], f["Date"], played_sa, rh, ra, lh, la,
                                           stand=stand_sa, last=last_sa, P=P, pick=pick_idx,
                                           quota_best=quota_pick, absences=absences, elo_raw=elo),
        }
        key = (f["home"], f["away"])
        if key in odds_map:
            o = np.array(odds_map[key], float)
            inv = 1 / o
            Pm = inv / inv.sum()
            edge = P - Pm
            j = int(np.argmax(np.abs(edge)))
            row["edge_vs_mercato"] = f"{edge[j]*100:+.1f}pp su {['1','X','2'][j]}"
            row["⚠️" ] = "🚨" if abs(edge[j]) > 0.03 else ""
        rows.append(row)

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    csv = DATA / f"forecast_giornata{target_md}.csv"
    out.to_csv(csv, index=False)
    print(f"\n💾 Salvato: {csv}")


if __name__ == "__main__":
    main()
