"""
🔮 PREVISIONI MULTI-LEGA (Top 5: Serie A, Premier League, LaLiga, Bundesliga, Ligue 1)
per la prossima finestra temporale (weekend), con giocata unica (Singola + Raddoppio ≈ 2.00).

Uso:
  python3 src/weekly_multi.py --from 2026-11-06 --to 2026-11-10
  python3 src/weekly_multi.py            # finestra automatica MOBILE: oggi → +7 giorni (10→17, 11→18, …)

Input:  data/matches.csv (multi-lega, step 1) · data/fixtures_leagues.csv (step 1b)
        data/fixtures_all_2627.csv (quote football-data, tutte le leghe)
        data/absences*.csv (solo Serie A)
Output: data/forecast_multi.csv   (una riga per partita non giocata nella finestra, tutte le leghe)
        data/giocata_multi.csv    (Singola del giorno + Raddoppio 2-3 eventi quota combinata ≈ 2.00)

Regole giocata (da README): Singola = partita con p modello più alta; Raddoppio = 2 o 3 partite
distinte, una per match, quota combinata (prodotto best-price) più vicina a 2.00, pareggio → EV maggiore.
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import itertools
import os
# 🆕 06/11 pesi ensemble configurabili via env (tuning: step12_tune_weights.py)
# 🆕 06/11 default = best da tuning walk-forward (step12_tune_weights.py, g6-g10, 496 match): RPS 0.1992
W_ELO = float(os.environ.get("W_ELO", 0.5))
W_DC = float(os.environ.get("W_DC", 0.3))
W_MKT = float(os.environ.get("W_MKT", 0.2))
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import re


def pois_cdf(k, lam):
    # 🆕 06/11 CDF Poisson senza scipy
    if lam is None or lam <= 0:
        return 1.0
    import math
    t = math.exp(-lam)
    sm = t
    for i in range(1, int(k) + 1):
        t *= lam / i
        sm += t
    return min(1.0, sm)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_elo import update_elo
from step4_dixon_coles import TeamHistory, score_matrix, matrix_to_markets, dc_weights
from motivi import motivo_match, frase_motivo, perche_breve, perche_mercato

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 🆕 leghe extra con storico gratis football-data (04/11/2026) — vanno nella pagina "Altre leghe"
EXTRA = ["Serie B", "Championship", "Eredivisie", "Primeira Liga", "Süper Lig", "Bundesliga 2", "LaLiga 2", "Ligue 2"]
LEAGUES = ["Serie A", "Premier League", "LaLiga", "Bundesliga", "Ligue 1",
           "Champions League", "Europa League", "Conference League"] + EXTRA  # 🏆 coppe + 🆕 extra dal 04/11
DIV2LEAGUE = {"I1": "Serie A", "E0": "Premier League", "SP1": "LaLiga", "D1": "Bundesliga", "F1": "Ligue 1",
              "UCL": "Champions League", "UEL": "Europa League", "UECL": "Conference League",
              "I2": "Serie B", "E1": "Championship", "N1": "Eredivisie", "P1": "Primeira Liga",
              "T1": "Süper Lig", "D2": "Bundesliga 2", "SP2": "LaLiga 2", "F2": "Ligue 2"}
CUPS = {"Champions League", "Europa League", "Conference League"}

# 🆕 13/11 meteo (open-meteo) + derby via coordinate —uckland popolate da load_weather() (storico+forecast)
WX = {}       # (team, "YYYY-MM-DD") -> factor (<1 = meteo avverso, meno gol)
CITY = {}     # team -> city
DERBY = set() # frozenset({home, away}) con distanza < 100 km
COORD = {}    # team -> (lat, lon)

def travel_km(home, away):
    """🆕 13/11 distanza trasferta (km) dalle coordinate; 0 se mancante."""
    a, b = COORD.get(home), COORD.get(away)
    if not a or not b:
        return 0.0
    return haversine_km(a[0], a[1], b[0], b[1])

def haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def load_weather():
    """Carica team_coords.csv + weather_hist/fore.csv in WX/CITY/DERBY (se presenti)."""
    global WX, CITY, DERBY
    try:
        cd = pd.read_csv(DATA / "team_coords.csv")
        for _, r in cd.iterrows():
            CITY[r["team"]] = r["city"]
        coord = {(r["team"]): (r["lat"], r["lon"]) for _, r in cd.iterrows() if pd.notna(r.get("lat"))}
        COORD.update(coord)
        for fn in ("weather_hist.csv", "weather_fore.csv"):
            fp = DATA / fn
            if not fp.exists():
                continue
            w = pd.read_csv(fp)
            for _, r in w.iterrows():
                city = r["city"]; d = str(r["date"])
                for t, c in CITY.items():
                    if c == city:
                        WX[(t, d)] = float(r["factor"])
        # derby: coppie di squadre con stade a < 100 km
        teams = list(coord.items())
        for i in range(len(teams)):
            for j in range(i+1, len(teams)):
                (t1, (la1, lo1)), (t2, (la2, lo2)) = teams[i], teams[j]
                if haversine_km(la1, lo1, la2, lo2) < 100:
                    DERBY.add(frozenset((t1, t2)))
        print(f"🌦️ meteo caricato: {len(WX)} (team,giorno), derby: {len(DERBY)} coppie")
    except Exception as e:
        print(" meteo non disponibile:", e)
# 🆕 10/11 NAZIONALI (sosta FIFA): storico da kaggle in fixtures_intl.csv, calendario da ESPN
INTL = ["Nations League", "WC Qual. UEFA", "Friendlies"]
LEAGUES = LEAGUES + INTL
DIV2LEAGUE.update({"UNL": "Nations League", "WCQ": "WC Qual. UEFA", "FRD": "Friendlies"})

ELO_K, ELO_HFA, SHRINK = 48.0, 60.0, 0.70
DC_HALF_LIFE = 180.0


def xg_proxy(goals, sot, shots):
    if pd.isna(sot) or pd.isna(shots):
        return float(goals)
    return 0.05 * shots + 0.20 * sot


def elo_to_probs_draw(rh, ra, draw_base, hfa=ELO_HFA):
    diff = rh - ra + hfa
    p_home_raw = 1.0 / (1.0 + 10 ** (-diff / 400.0))
    p_draw = draw_base * (1 + np.exp(-abs(diff) / 200.0)) / 2
    p_draw = min(p_draw, 0.45)
    rest = 1 - p_draw
    return np.array([p_home_raw * rest, p_draw, (1 - p_home_raw) * rest])


# 🆕 13/11 CALIBRAZIONE ISOTONIC walk-forward: fitta su partite DOPO un cut (no leakage),
# corregge over/under-confidence -> RPS/Brier migliori e EV/Kelly onesti.
try:
    from sklearn.isotonic import IsotonicRegression as _IR
    class Calib:
        def __init__(self):
            self.irs = None
            self.se = None          # ⚠️ DEPRECATO: era il Brier, NON un errore standard (bug 13/11-b)
            self.brier_k = None     # Brier per classe: solo diagnostica
            self.n = 0              # partite usate per fittare la calibrazione
        def fit(self, Ps, ys, min_n=60):
            Ps = np.asarray(Ps, float); ys = np.asarray(ys, int)
            if len(Ps) < min_n:
                return
            self.irs = [_IR(out_of_bounds="clip", y_min=0.02, y_max=0.98).fit(Ps[:, k], (ys == k).astype(float)) for k in range(3)]
            Y = np.eye(3)[ys]
            self.brier_k = np.sqrt(np.mean((Ps - Y) ** 2, axis=0))  # 🆕 13/11-b diagnostica, mai usato come se
            self.n = int(len(Ps))
        def se_for(self, p, n_eff=None):
            """🆕 13/11-b errore standard della probabilità p (≈ IC 68%): binomiale con n_eff = coda di
            calibrazione (clamp 30…250). Prima qui si usava il Brier (0.2-0.5) come se: margine enorme,
            stake azzerato sempre. Ora il margine è 2-7 punti percentuali, come deve essere."""
            n = int(n_eff or self.n or 50)
            n = max(30, min(n, 250))
            se = float(np.sqrt(max(p * (1 - p), 1e-9) / n))
            return float(min(0.10, max(0.02, se)))
        def apply(self, P):
            if not self.irs:
                return P
            Q = np.array([ir.predict(np.atleast_1d(float(P[k])))[0] for k, ir in enumerate(self.irs)])
            t = Q.sum()
            return Q / t if t > 1e-9 else P
except Exception:
    class Calib:
        def fit(self, *a, **k): pass
        def apply(self, P): return P

class Stacker:
    """🆕 13/11 meta-learner: logistic regression sui 3 membri (Elo, DC, mercato) -> P stackate."""
    def __init__(self):
        self.clf = None
    def fit(self, X, y, min_n=80):
        try:
            from sklearn.linear_model import LogisticRegression
            X = np.asarray(X, float); y = np.asarray(y, int)
            if len(X) < min_n:
                return
            self.clf = LogisticRegression(max_iter=2000, C=1.0).fit(X, y)
        except Exception:
            self.clf = None
    def apply(self, members):
        if self.clf is None:
            return None
        parts = []
        for m in members:
            if m is None:
                continue
            parts.append(np.asarray(m, float))
        pe, pdc = members[0], members[1]
        pm = members[2] if members[2] is not None else (pe + pdc) / 2.0
        x = np.concatenate([pe, pdc, pm] + parts[3:]).reshape(1, -1)
        return self.clf.predict_proba(x)[0]

def fit_calibrator(m_all, n=60, gap=45):
    """m_all: tutte le partite giocate della lega (ordine qualsiasi). Ritorna Calib o None."""
    try:
        pa = m_all.sort_values("Date")
        if len(pa) < 160:
            return None
        mx = pa["Date"].max()
        cut = mx - pd.Timedelta(days=gap)
        tr = pa[pa["Date"] < cut]
        if len(tr) < 120:
            return None
        elo, dc_hist, ad, ahg, aag, draw_base, hfa = train_league(tr)
        stand = standings(tr); last = last_match(tr, mx)
        tail = pa[pa["Date"] >= cut].tail(n)
        Ps, ys, Xs, Fs, r_po, r_pg = [], [], [], [], [], []
        for _, m in tail.iterrows():
            y = 0 if m["FTHG"] > m["FTAG"] else (2 if m["FTHG"] < m["FTAG"] else 1)
            odds = (m["AvgCH"], m["AvgCD"], m["AvgCA"]) if "AvgCH" in m.index and pd.notna(m.get("AvgCH")) else None
            r = predict_match_full(elo, dc_hist, ad, ahg, aag, draw_base, m["Date"] + pd.Timedelta(days=1),
                                   m["HomeTeam"], m["AwayTeam"], stand=stand, last=last, odds=odds, hfa=hfa,
                                   wx=WX.get((m["HomeTeam"], m["Date"].date().isoformat()), 1.0),
                                   derby=frozenset((m["HomeTeam"], m["AwayTeam"])) in DERBY)
            P = r[0]; Ps.append(P); ys.append(y)
            r_po.append(float(r[1])); r_pg.append(float(r[2]))
            pmk = r[11] if r[11] is not None else (r[9] + r[10]) / 2.0
            Xs.append(np.concatenate([r[9], r[10], pmk]))
            Fs.append(r[12])
        # 🆕 13/11 stacker binari per O/U 2.5 e GG/NG (membri: DC + mercato)
        Xou, You, Xgg, Ygg = [], [], [], []
        for i, (_, m) in enumerate(tail.iterrows()):
            yo = 1 if (m["FTHG"] + m["FTAG"]) > 2.5 else 0
            yg = 1 if (m["FTHG"] > 0 and m["FTAG"] > 0) else 0
            pm_ou = None
            if "AvgC>2.5" in m.index and pd.notna(m.get("AvgC>2.5")) and m["AvgC>2.5"] > 1.05:
                pm_ou = 1.0 / float(m["AvgC>2.5"])
            pm_gg = None
            if "AvgCBTTS" in m.index and pd.notna(m.get("AvgCBTTS")) and m["AvgCBTTS"] > 1.05:
                pm_gg = 1.0 / float(m["AvgCBTTS"])
            po_dc = float(r_po[i]) if False else None
            Xou.append([r_po[i], pm_ou if pm_ou is not None else r_po[i]]); You.append(yo)
            Xgg.append([r_pg[i], pm_gg if pm_gg is not None else r_pg[i]]); Ygg.append(yg)
        st_ou = st_gg = None
        try:
            from sklearn.linear_model import LogisticRegression as _LR
            if len(Xou) >= 80:
                st_ou = _LR(max_iter=1000).fit(np.array(Xou), np.array(You))
                st_gg = _LR(max_iter=1000).fit(np.array(Xgg), np.array(Ygg))
        except Exception:
            pass
        c = Calib(); c.fit(Ps, ys)
        # 🆕 13/11 4° membro: GBM su feature tabellari (elo diff, lambda diff, log-ratio)
        gbm = None
        try:
            from sklearn.ensemble import HistGradientBoostingClassifier
            F = np.array(Fs); Y = np.array(ys)
            if len(F) >= 80:
                gbm = HistGradientBoostingClassifier(max_iter=120, learning_rate=0.06, max_leaf_nodes=15,
                                                     random_state=7).fit(F, Y)
        except Exception:
            gbm = None
        # stacker sui membri + P_gbm (12 input)
        Xs2 = []
        for i, x in enumerate(Xs):
            pg = gbm.predict_proba(Fs[i].reshape(1, -1))[0] if gbm is not None else None
            if pg is None:
                Xs2.append(np.concatenate([x, (np.array([1/3,1/3,1/3]))]))
            else:
                Xs2.append(np.concatenate([x, pg]))
        st = Stacker(); st.fit(Xs2, ys)
        return (c if c.irs else None), (st if st.clf is not None else None), gbm, st_ou, st_gg
    except Exception:
        return None, None, None, None, None


def train_league(played: pd.DataFrame, elo0=None):
    """Elo + Dixon-Coles replay su una sola lega. Ritorna stati finali + draw_base della lega.
    elo0: Elo iniziale (usato per le coppe: semi = Elo della lega nazionale della squadra)."""
    draw_base = float((played["FTR"] == "D").mean()) if len(played) else 0.25
    # calibrazione xG-proxy (dove manca HxG/AxG)
    ph = played.apply(lambda m: xg_proxy(m["FTHG"], m.get("HST"), m.get("HS")), axis=1)
    pa = played.apply(lambda m: xg_proxy(m["FTAG"], m.get("AST"), m.get("AS")), axis=1)
    mask = played["HxG"].isna() if "HxG" in played else pd.Series(False, index=played.index)
    scale_h = played.loc[mask, "FTHG"].sum() / ph[mask].sum() if mask.any() else 1.0
    scale_a = played.loc[mask, "FTAG"].sum() / pa[mask].sum() if mask.any() else 1.0

    # 🆕 13/11 HFA stimato per lega dai dati: share vittorie casa vs trasferta (no pareggi)
    if len(played) >= 60:
        hw = int((played["FTR"] == "H").sum()); aw = int((played["FTR"] == "A").sum())
        if hw + aw > 0:
            ph = hw / (hw + aw)
            hfa = float(np.clip(400.0 * np.log10(ph / max(1e-6, 1 - ph)), 15.0, 110.0))
        else:
            hfa = ELO_HFA
    else:
        hfa = ELO_HFA
    elo = dict(elo0) if elo0 else {}
    dc_hist = {}
    ad, ahg, aag = [], [], []
    prev_season = None
    for _, m in played.iterrows():
        if m["Season"] != prev_season and prev_season is not None:
            for t in elo:
                elo[t] = 1500 + SHRINK * (elo[t] - 1500)
        prev_season = m["Season"]
        rh, ra = elo.get(m["HomeTeam"], 1500.0), elo.get(m["AwayTeam"], 1500.0)
        score = {"H": 1.0, "D": 0.5, "A": 0.0}[m["FTR"]]
        elo[m["HomeTeam"]], elo[m["AwayTeam"]] = update_elo(rh, ra, score, ELO_K, hfa)
        if "HxG" in m.index and pd.notna(m["HxG"]):
            gf, ga = float(m["HxG"]), float(m["AxG"])
        else:
            gf = xg_proxy(m["FTHG"], m.get("HST"), m.get("HS")) * scale_h
            ga = xg_proxy(m["FTAG"], m.get("AST"), m.get("AS")) * scale_a
        dc_hist.setdefault(m["HomeTeam"], TeamHistory()).add(m["Date"], gf, ga, True)
        dc_hist.setdefault(m["AwayTeam"], TeamHistory()).add(m["Date"], ga, gf, False)
        ad.append(m["Date"]); ahg.append(gf); aag.append(ga)
    return elo, dc_hist, ad, ahg, aag, draw_base, hfa


def standings(played):
    pts, n, gd, gf = {}, {}, {}, {}
    for _, m in played.iterrows():
        h, a = m["HomeTeam"], m["AwayTeam"]
        if pd.isna(m.get("FTHG")) or pd.isna(m.get("FTAG")):
            continue
        for t in (h, a):
            pts.setdefault(t, 0); n.setdefault(t, 0); gd.setdefault(t, 0); gf.setdefault(t, 0)
        n[h] += 1; n[a] += 1
        gf[h] += m["FTHG"]; gf[a] += m["FTAG"]
        gd[h] += m["FTHG"] - m["FTAG"]; gd[a] += m["FTAG"] - m["FTHG"]
        if m["FTHG"] > m["FTAG"]: pts[h] += 3
        elif m["FTHG"] < m["FTAG"]: pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
    df = pd.DataFrame([{"team": t, "pts": p, "n": n[t], "gd": gd[t], "gf": gf[t]} for t, p in pts.items()])
    if df.empty:
        return df
    df = df.sort_values(["pts", "gd", "gf"], ascending=[False, False, False]).reset_index(drop=True)  # 🛠 09/11 pari a punti: pari-testa (GD) e gol fatti, come le classifiche reali
    df["pos"] = df.index + 1
    return df


def form_weighted(played, elo, team, before, n=5):
    """Forma ultime n partite pesata per la FORZA (Elo) dell'avversario.
    Ritorna punteggio in [-1, 1]: vittorie vs squadre forti pesano di più."""
    tm = played[(played["Date"] < before) & ((played["HomeTeam"] == team) | (played["AwayTeam"] == team))]
    tm = tm.sort_values("Date").tail(n)
    if len(tm) == 0:
        return 0.0
    tot_w, tot_s = 0.0, 0.0
    for _, m in tm.iterrows():
        home = m["HomeTeam"] == team
        opp = m["AwayTeam"] if home else m["HomeTeam"]
        opp_elo = elo.get(opp, 1500.0)
        w = max(0.4, min(1.6, opp_elo / 1500.0))  # avversario forte pesa di più
        if (home and m["FTHG"] > m["FTAG"]) or (not home and m["FTAG"] > m["FTHG"]):
            s_ = 1.0
        elif m["FTHG"] == m["FTAG"]:
            s_ = 0.33
        else:
            s_ = 0.0
        tot_w += w
        tot_s += s_ * w
    return (tot_s / tot_w) * 2 - 1  # normalizza a [-1,1]


def last_match(played, before):
    last = {}
    for _, m in played[played["Date"] < before].iterrows():
        for t in (m["HomeTeam"], m["AwayTeam"]):
            if t not in last or m["Date"] > last[t]:
                last[t] = m["Date"]
    return last


def predict_match(*a, **k):
    return predict_match_full(*a, **k)[:9]

def predict_match_full(elo, dc_hist, ad, ahg, aag, draw_base, date, home, away, stand=None, last=None, odds=None, h2h=None, ref_factor=1.0, out_counts=None, out_xg=None, form=None, hfa=ELO_HFA, xgf=None, wx=1.0, derby=False, travel=0.0):
    w = dc_weights((date - pd.DatetimeIndex(ad)).total_seconds() / 86400.0, DC_HALF_LIFE)
    mu_h = (w * np.array(ahg)).sum() / w.sum()
    mu_a = (w * np.array(aag)).sum() / w.sum()
    rh, ra = elo.get(home, 1500.0), elo.get(away, 1500.0)
    if form:  # 🆕 08/11 forma pesata per forza avversario (Elo)
        rh += 30.0 * form.get(home, 0.0)
        ra += 30.0 * form.get(away, 0.0)
    if xgf:  # 🆕 13/11 forma-xG ultime 5 partite (tutte le leghe, da HxG/AxG): diff xG -> punti Elo
        dh = max(-40.0, min(40.0, 20.0 * xgf.get(home, 0.0)))
        da = max(-40.0, min(40.0, 20.0 * xgf.get(away, 0.0)))
        rh += dh; ra += da
    n_teams = 20 if draw_base > 0 else 18
    if stand is not None and len(stand):
        for t in (home, away):
            pos = stand.loc[stand.team == t, "pos"]
            pos = int(pos.iloc[0]) if len(pos) else len(stand) // 2 + 1
            adj = 15.0 if (pos <= 4 or pos >= len(stand) - 2) else (-5.0 if 8 <= pos <= 14 else 0.0)
            if t == home: rh += adj
            else: ra += adj
    if last is not None:
        for t in (home, away):
            d = (date - last.get(t, date - pd.Timedelta(days=7))).days
            adj = 20.0 * max(0, 4 - d) if d < 4 else 0.0
            if t == home: rh -= adj
            else: ra -= adj
    db = min(0.45, draw_base + (0.03 if derby else 0.0))  # 🆕 13/11 derby: più pareggio atteso
    P_elo = elo_to_probs_draw(rh, ra, db, hfa=hfa)
    TH = dc_hist.get(home, TeamHistory()); TA = dc_hist.get(away, TeamHistory())
    ohH, dhH, _, daH = TH.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    _, dhA, oaA, _ = TA.rates(date, mu_h, mu_a, DC_HALF_LIFE)
    lh = mu_h * ohH * daH
    la = mu_a * oaA * dhH
    # 🆕 06/11 H2H: ultimi 4 precedenti, diff gol medio (cap ±0.25)
    if h2h:
        diffs = [d for _, d in sorted(h2h, key=lambda x: x[0])[-4:]]
        if diffs:
            adj = max(-0.25, min(0.25, 0.15 * sum(diffs) / len(diffs)))
            lh += adj; la -= adj
    # 🆕 06/11 bias arbitro: factor da media gol dell'arbitro vs media overall (shrink 50%, applico 25%)
    if ref_factor and abs(ref_factor - 1.0) > 0.01:
        f = 1.0 + 0.25 * (ref_factor - 1.0)
        lh *= f; la *= f
    # 🆕 06/11 xG mancante degli assenti (proxy: n_out × lambda/11 × 0.8)
    if out_counts:
        lh -= 0.8 * out_counts.get(home, 0) * lh / 11.0
        la -= 0.8 * out_counts.get(away, 0) * la / 11.0
    if out_xg:  # 🆕 06/11 xG vero mancante (step13_player_xg.py → missing_xg.csv)
        lh -= out_xg.get(home, 0.0)
        la -= out_xg.get(away, 0.0)
    if wx != 1.0:  # 🆕 13/11 meteo avverso: scala i gol attesi di entrambe
        lh *= wx; la *= wx
    if travel >= 1000:  # 🆕 13/11 trasferta lunga (>1000 km): fatigue -> meno gol in trasferta
        la *= 0.97
    M = score_matrix(lh, la)
    pH, pD, pA, p_over, p_btts = matrix_to_markets(M)
    P_dc = np.array([pH, pD, pA])
    if odds is not None:
        inv = 1 / np.array(odds, float)
        P_mkt = inv / inv.sum()
        P = W_ELO * P_elo + W_DC * P_dc + W_MKT * P_mkt
    else:
        P_mkt = None
        P = 0.5 * P_elo + 0.5 * P_dc
    P = P / P.sum()
    idx = np.unravel_index(np.argmax(M), M.shape)
    # 🆕 13/11 membri separati per lo stacking (meta-learner) + feature tabellari per il 4° membro (GBM)
    feat = np.array([rh - ra, lh - la, lh + la, float(np.log(max(lh, 1e-3) / max(la, 1e-3)))])
    return P, p_over, p_btts, f"{idx[0]}-{idx[1]}", M[idx], rh, ra, lh, la, P_elo, P_dc, P_mkt, feat


def load_absences():
    import unicodedata
    def _norm(s):
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
        return " ".join(s.split())
    p = DATA / "absences.csv"
    if p.exists():
        d = pd.read_csv(p)
        return dict(zip(d["team"], d["elo_penalty"]))
    return {}


def _formazione_str(f, league, lineups):
    """Stringa formazione per la riga forecast (solo Serie A con lineups)."""
    if league != "Serie A":
        return ""
    parts = []
    for t in (f["home"], f["away"]):
        lu = lineups.get(t)
        if lu:
            parts.append(f"{t}: modulo {lu['modulo']} ({lu['allenatore']}), out: {lu['out']}")
    return " | ".join(parts)


def _verbale_con_formazione(f, league, lineups, verbale, absences):
    """Aggiunge al motivo verbale il contesto formazione (modulo + indisponibili)."""
    if league != "Serie A":
        return verbale
    ctx = []
    for t in (f["home"], f["away"]):
        lu = lineups.get(t)
        if lu:
            ctx.append(f"{t} scenderà con modulo {lu['modulo']}" +
                       (f" e senza {lu['out']}" if lu["out"] and lu["out"] != "nessuno segnalato" else " senza indisponibili segnalati"))
    if ctx:
        return verbale + " Contesto formazione (fantacalcio-online): " + "; ".join(ctx) + "."
    return verbale


def corners_exp(played, date, home, away, n=6, hl=3.0):
    """Corners attesi dal modello: rolling (ultime n, half-life) calci d'angolo fatti/subiti."""
    if "HC" not in played.columns or played["HC"].isna().all():
        return ""
    p = played[played["Date"] < date]
    mu = (p["HC"].mean() + p["AC"].mean()) / 2 or 5.0
    def roll(team):
        h = p[(p["HomeTeam"] == team) | (p["AwayTeam"] == team)].sort_values("Date").tail(n)
        if len(h) == 0:
            return None
        ws = [2.0 ** (-(len(h) - 1 - i) / hl) for i in range(len(h))]
        gf = sum(w * (row["HC"] if row["HomeTeam"] == team else row["AC"]) for w, (_, row) in zip(ws, h.iterrows())) / sum(ws)
        ga = sum(w * (row["AC"] if row["HomeTeam"] == team else row["HC"]) for w, (_, row) in zip(ws, h.iterrows())) / sum(ws)
        return gf, ga
    rh, ra = roll(home), roll(away)
    if rh is None or ra is None:
        return ""
    lh = (rh[0] + ra[1]) / 2   # corner casa attesi
    la = (ra[0] + rh[1]) / 2   # corner ospite attesi
    return round(lh + la, 1)


def corners_exp(played, date, home, away, n=6, hl=3.0):
    """Corners attesi dal modello: rolling (ultime n, half-life) calci d'angolo fatti/subiti."""
    if "HC" not in played.columns or played["HC"].isna().all():
        return ""
    p = played[played["Date"] < date]
    def roll(team):
        h = p[(p["HomeTeam"] == team) | (p["AwayTeam"] == team)].sort_values("Date").tail(n)
        if len(h) == 0:
            return None
        ws = [2.0 ** (-(len(h) - 1 - i) / hl) for i in range(len(h))]
        gf = sum(w * (row["HC"] if row["HomeTeam"] == team else row["AC"]) for w, (_, row) in zip(ws, h.iterrows())) / sum(ws)
        ga = sum(w * (row["AC"] if row["HomeTeam"] == team else row["HC"]) for w, (_, row) in zip(ws, h.iterrows())) / sum(ws)
        return gf, ga
    rh, ra = roll(home), roll(away)
    if rh is None or ra is None:
        return ""
    lh = (rh[0] + ra[1]) / 2
    la = (ra[0] + rh[1]) / 2
    return round(lh + la, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default=None)
    ap.add_argument("--to", dest="to", default=None)
    args = ap.parse_args()

    matches = pd.read_csv(DATA / "matches.csv", parse_dates=["Date"])
    # 🆕 06/11: xG match-level FotMob per le COPPE (le leghe nazionali hanno già HxG/AxG in matches.csv,
    # e train_league li usa già come gol del DC). Qui riempiamo HxG/AxG anche per le coppe.
    XG_FOTMOB = {}
    xgp = DATA / "xg_fotmob_all.csv"
    if xgp.exists():
        for _, r in pd.read_csv(xgp).iterrows():
            if pd.notna(r.get("xgH")):
                XG_FOTMOB[(str(r["date"]), r["home"], r["away"])] = (float(r["xgH"]), float(r["xgA"]))
    globals()["XG_FOTMOB"] = XG_FOTMOB
    fx = pd.read_csv(DATA / "fixtures_leagues.csv")
    fi = DATA / "fixtures_intl.csv"
    if fi.exists():  # 🆕 10/11 nazionali: calendario+storico da step1f
        fx = pd.concat([fx, pd.read_csv(fi)], ignore_index=True)
        print(f"🚩 nazionali: +{len(pd.read_csv(fi))} righe da fixtures_intl.csv")
    fx["Date"] = pd.to_datetime(fx["date"])
    fa = pd.read_csv(DATA / "fixtures_all_2627.csv", encoding="utf-8-sig")
    fa["Date"] = pd.to_datetime(fa["Date"], format="%d/%m/%Y", errors="coerce")
    fa = fa.dropna(subset=["Date"])

    # quote per (div, data, casa, ospite): media (per ensemble) e MAX = best price (per giocata)
    odds_avg, odds_max, odds_extra = {}, {}, {}
    corner_max = {}  # 🆕 06/11 quote corner (O/U 9.5) best da football-data: MaxC>2.5 / MaxC<2.5
    def _nk(div, date, h, a):
        n = lambda t: "".join(c for c in str(t).lower() if c.isalnum())
        return (div, date, n(h), n(a))
    for _, r in fa.iterrows():
        k = _nk(r["Div"], r["Date"].normalize(), r["HomeTeam"], r["AwayTeam"])
        if pd.notna(r.get("AvgH")):
            odds_avg[k] = (r["AvgH"], r["AvgD"], r["AvgA"])
        elif pd.notna(r.get("B365H")):  # 🆕 fallback apertura B365 (sempre presente) per calcolo movimento
            odds_avg[k] = (r["B365H"], r["B365D"], r["B365A"])
        if pd.notna(r.get("MaxC>2.5")) and pd.notna(r.get("MaxC<2.5")):
            corner_max[k] = (float(r["MaxC>2.5"]), float(r["MaxC<2.5"]))
        if pd.notna(r.get("MaxH")):
            odds_max[k] = (r["MaxH"], r["MaxD"], r["MaxA"])
        # mercati extra best-price: GG/Sì (MaxCH), NG/No (MaxCD), Over 2.5 (Max>2.5), Under 2.5 (Max<2.5)
        ex = {}
        if pd.notna(r.get("MaxCH")): ex["GG"] = float(r["MaxCH"])
        if pd.notna(r.get("MaxCD")): ex["NG"] = float(r["MaxCD"])
        if pd.notna(r.get("Max>2.5")): ex["O2.5"] = float(r["Max>2.5"])
        if pd.notna(r.get("Max<2.5")): ex["U2.5"] = float(r["Max<2.5"])
        if ex: odds_extra[k] = ex

    # 💰 best-price wincomparator per la finestra (tutti i file odds_window_*_bestprice.csv)
    win_odds = {}   # (lega, data, home, away) -> dict(1X2 best, extra)
    for wf in sorted(DATA.glob("odds_window_*_bestprice.csv")):
        wd = pd.read_csv(wf)
        for _, r in wd.iterrows():
            k = (r["lega"], pd.Timestamp(r["data"]), r["home"], r["away"])
            win_odds[k] = {"1X2": (r["best_1"], r["best_X"], r["best_2"]),
                           "GG": r.get("best_GG"), "NG": r.get("best_NG"),
                           "O2.5": r.get("best_O25"), "U2.5": r.get("best_U25")}
        print(f"💰 best-price wincomparator caricate: {wf.name} ({len(wd)} partite)")

    # 🆕 06/11 bias arbitro: media gol/partita per referee (min 20 partite), shrink 50%
    mt = matches.dropna(subset=["Referee", "FTHG", "FTAG"]).copy()
    mt["tot"] = mt["FTHG"] + mt["FTAG"]
    overall = mt["tot"].mean()
    rb = mt.groupby("Referee")["tot"].agg(["mean", "count"])
    ref2factor = {r: round(1.0 + 0.5 * (row["mean"] / overall - 1.0), 4) for r, row in rb.iterrows() if row["count"] >= 20}
    fa_idx = {}
    if "Referee" in fa.columns:
        for _, r in fa.iterrows():
            if pd.notna(r.get("Referee")):
                fa_idx[_nk(r["Div"], r["Date"].normalize(), r["HomeTeam"], r["AwayTeam"])] = r["Referee"]
    # 🆕 06/11 conteggio assenti per squadra (xG mancante proxy)
    out_counts = {}
    iep2 = DATA / "indisponibili_euro.csv"
    if iep2.exists():
        for t, n in pd.read_csv(iep2).groupby("team").size().items():
            out_counts[t] = int(n)
    for t in load_absences():
        out_counts[t] = out_counts.get(t, 0) + 2
    # 🆕 06/11 xG mancante vero per squadra (player-xG FotMob); queste escono dal proxy a conteggio
    out_xg = {}
    mxp = DATA / "missing_xg.csv"
    if mxp.exists():
        for _, r in pd.read_csv(mxp).iterrows():
            out_xg[r["team"]] = float(r["xg_mancante"])
            out_counts.pop(r["team"], None)
        print(f"🩹 xG mancante (player-xG) per {len(out_xg)} squadre")

    # 🆕 10/11 finestra MOBILE: default = OGGI → +7 giorni (10→17, domani 11→18, …; i giorni giocati vanno in archivio via step20)
    unplayed = fx[~fx["played"]]
    if args.frm:
        frm, to = pd.Timestamp(args.frm), pd.Timestamp(args.to)
    else:
        frm = pd.Timestamp(datetime.now(ZoneInfo("Europe/Rome")).date()).normalize()  # oggi ora italiana
        to = frm + pd.Timedelta(days=7, hours=23)
    window = unplayed[(unplayed["Date"] >= frm) & (unplayed["Date"] <= to + pd.Timedelta(hours=23, minutes=59))]
    print(f"🪟 Finestra mobile: {frm.date()} → {(frm + pd.Timedelta(days=7)).date()} | partite non giocate: {len(window)}")
    print(window.groupby("league")["matchday"].agg(["min", "max", "count"]).to_string(), "\n")

    absences = load_absences()  # solo squadre Serie A
    # 🆕 06/11: assenze per TUTTE le leghe da fantacalcio EuroLeghe (indisponibili_euro.csv)
    abs_all = dict(absences)
    iep = DATA / "indisponibili_euro.csv"
    if iep.exists():
        for _, r in pd.read_csv(iep).iterrows():
            pen = 6.0 if r.get("tipo") == "Squalificati" else 8.0
            abs_all[r["team"]] = min(40.0, abs_all.get(r["team"], 0.0) + pen)
        print(f"📋 assenze EuroLeghe: {len(pd.read_csv(iep))} out, {len(abs_all)} squadre con penalita")

    # 📋 probabili formazioni (squadre tipo + indisponibili g11) — solo Serie A
    lineups = {}
    for md in sorted(set(window["matchday"])):
        lp = DATA / f"lineups_giornata{int(md)}.csv"
        if lp.exists():
            ldf = pd.read_csv(lp)
            # 🛠 08/11 sanifica: un giocatore che è nella XI di un'altra squadra NON può essere "out" (es. Pavlovic al Milan, non all'Inter)
            xi_players = set()
            for _, rr in ldf.iterrows():
                for nm in re.split(r"[;,]", str(rr["xi_probabile"])):
                    nm = nm.strip().split("(")[0].strip().lower()
                    if nm:
                        xi_players.add(nm)
            for _, r in ldf.iterrows():
                outs = [o for o in str(r["indisponibili"]).split(",")
                        if o.strip() and o.strip().split("(")[0].strip().lower() not in xi_players]
                lineups[r["team"]] = {"modulo": r["modulo"], "allenatore": r.get("allenatore", ""),
                                      "xi": r["xi_probabile"], "out": ", ".join(outs), "giornata": int(r["giornata"])}

    # pre-addestra le 5 leghe nazionali (servono anche come seed Elo per le coppe)
    domestic = {}
    for league in LEAGUES:
        if league in CUPS or league in INTL:
            continue  # 🆕 10/11: le nazionali non hanno storico in matches.csv
        played = matches[(matches["League"] == league) & (matches["Season"].astype(str).str.contains("2026/2027"))].sort_values("Date")  # 🛠 08/11 solo stagione corrente per standings/Elo
        elo, dc_hist, ad, ahg, aag, draw_base, hfa_l = train_league(played)
        _use_gbm = os.environ.get("USE_GBM", "0") == "1"  # 🆕 13/11 GBM validato: non migliora (0.2915 vs 0.1918) → default OFF
        cal, st, gbm, st_ou, st_gg = fit_calibrator(matches[matches["League"] == league])  # isotonic + stacker + O/U + GG
        if not _use_gbm:
            gbm = None
        domestic[league] = (elo, dc_hist, ad, ahg, aag, draw_base, hfa_l, cal, st, gbm, st_ou, st_gg)
    seed = {}
    for le, (elo, *_rest) in domestic.items():
        for t, e in elo.items():
            seed[t] = e

    fxall = pd.read_csv(DATA / "fixtures_leagues.csv")
    fi2 = DATA / "fixtures_intl.csv"
    if fi2.exists():  # 🆕 10/11 storico nazionali per Elo (come le coppe)
        fxall = pd.concat([fxall, pd.read_csv(fi2)], ignore_index=True)
    fxall["Date"] = pd.to_datetime(fxall["date"])

    load_weather()  # 🆕 13/11 meteo + derby
    # 🆕 13/11 ensemble temporale: media con la previsione precedente (0.65新/0.35旧) -> meno varianza
    PREV = {}
    try:
        pf = DATA / "forecast_multi.csv"
        if pf.exists():
            pv = pd.read_csv(pf)
            for _, r in pv.iterrows():
                PREV[(r["lega"], r["partita"], r["orario"])] = np.array([float(r["p1%"]), float(r["pX%"]), float(r["p2%"])]) / 100.0
    except Exception:
        pass
    rows = []
    for league in LEAGUES:
        sub = window[window["league"] == league]
        if sub.empty:
            continue
        if league in CUPS or league in INTL:
            # 🏆 coppe / 🚩 nazionali: storico = match già giocati del calendario (FotMob / ESPN+kaggle); Elo seminato dalle leghe nazionali
            cp = fxall[(fxall["league"] == league) & (fxall["played"]) & (fxall["hg"] != "")]
            prows = []
            for _, m in cp.iterrows():
                hg, ag = float(m["hg"]), float(m["ag"])
                prows.append({"Season": "2026/2027", "Date": m["Date"], "HomeTeam": m["home"], "AwayTeam": m["away"],
                              "FTHG": hg, "FTAG": ag, "FTR": "H" if hg > ag else ("A" if hg < ag else "D")})
            xgf = globals().get("XG_FOTMOB", {})
            for pr in prows:
                kk = (str(pr["Date"].date()), pr["HomeTeam"], pr["AwayTeam"])
                if kk in xgf:
                    pr["HxG"], pr["AxG"] = xgf[kk]
            played = pd.DataFrame(prows)
            elo, dc_hist, ad, ahg, aag, draw_base, hfa_l = train_league(played, elo0=seed)
            cal, st, gbm, st_ou, st_gg = None, None, None, None, None
            print(f"  🏆 {league}: {len(played)} match storici (Elo seminato da leghe nazionali)")
        else:
            elo, dc_hist, ad, ahg, aag, draw_base, hfa_l, cal, st, gbm, st_ou, st_gg = domestic[league]
            played = matches[(matches["League"] == league) & (matches["Season"].astype(str).str.contains("2026/2027"))].sort_values("Date")  # 🛠 08/11 solo stagione corrente per standings/Elo
        if league == "Serie A":
            for t, pen in absences.items():
                elo[t] = elo.get(t, 1500.0) - pen
            # 📋 penalità rotazione dagli indisponibili della probable-formazione (se non già in assenze)
            lineup_pen = {}
            for t, lu in lineups.items():
                if lu["out"] and lu["out"] != "nessuno segnalato":
                    n_out = len([x for x in lu["out"].split(",") if x.strip()])
                    extra = max(0, n_out - len([p for p in absences if p == t]))  # approssimazione: conta out non coperti
                    if t not in absences and n_out:
                        lineup_pen[t] = min(36, 12 * n_out)
            for t, pen in lineup_pen.items():
                elo[t] = elo.get(t, 1500.0) - pen
            if lineup_pen:
                print(f"  📋 penalità rotazione da indisponibili g11: {lineup_pen}")
        for t, pen in abs_all.items():
            if t in elo:
                elo[t] = elo.get(t, 1500.0) - pen
        for t, pen in abs_all.items():
            if t in elo:
                elo[t] = elo.get(t, 1500.0) - pen
        h2h_map = {}
        if {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "Date"} <= set(played.columns):
            for _, m in played.iterrows():
                h2h_map.setdefault((m["HomeTeam"], m["AwayTeam"]), []).append((m["Date"], m["FTHG"] - m["FTAG"]))
        stand = standings(played)
        first_date = sub["Date"].min()
        last = last_match(played, first_date)
        form = {t: form_weighted(played, elo, t, first_date) for t in set(played["HomeTeam"]) | set(played["AwayTeam"])}
        # 🆕 13/11 forma-xG ultime 5 partite (tutte le leghe, da HxG/AxG): diff media xG -> aggiustamento Elo
        xgf_map = {}
        if "HxG" in played.columns:
            for t in set(played["HomeTeam"]) | set(played["AwayTeam"]):
                hm = played[(played["HomeTeam"] == t) & (played["Date"] < first_date)].tail(5)
                am = played[(played["AwayTeam"] == t) & (played["Date"] < first_date)].tail(5)
                xrows = [(r["HxG"] - r["AxG"]) for _, r in hm.iterrows() if pd.notna(r.get("HxG"))] + \
                        [(r["AxG"] - r["HxG"]) for _, r in am.iterrows() if pd.notna(r.get("AxG"))]
                xgf_map[t] = float(np.mean(xrows)) if xrows else 0.0
        div = next(d for d, l in DIV2LEAGUE.items() if l == league)
        for _, f in sub.sort_values("Date").iterrows():
            k = _nk(div, f["Date"].normalize(), f["home"], f["away"])
            o_avg = odds_avg.get(k)
            o_max = odds_max.get(k)
            o_ex = odds_extra.get(k, {})
            wk = win_odds.get((league, f["Date"].normalize(), f["home"], f["away"]))
            if wk is not None:
                if o_max is None:
                    o_max = tuple(wk["1X2"])
                else:
                    o_max = tuple(max(a, b) for a, b in zip(o_max, wk["1X2"]))
                for m, key in (("GG", "GG"), ("NG", "NG"), ("O2.5", "O2.5"), ("U2.5", "U2.5")):
                    if pd.notna(wk.get(key)):
                        o_ex[m] = max(o_ex.get(m, 0), float(wk[key]))
            c_att = corners_exp(played, f["Date"], f["home"], f["away"])
            c_o95 = round((1 - pois_cdf(9, c_att or 10)) * 100, 1) if c_att else ""
            ck = corner_max.get(k) or ("", "")
            ref = fa_idx.get(k)
            rf = ref2factor.get(ref, 1.0) if ref else 1.0
            r = predict_match_full(
                elo, dc_hist, ad, ahg, aag, draw_base, f["Date"], f["home"], f["away"],
                stand=stand, last=last, odds=o_avg,
                h2h=h2h_map.get((f["home"], f["away"])), ref_factor=rf, out_counts=out_counts, out_xg=out_xg,
                form={f["home"]: form.get(f["home"], 0.0), f["away"]: form.get(f["away"], 0.0)}, hfa=hfa_l,
                xgf={f["home"]: xgf_map.get(f["home"], 0.0), f["away"]: xgf_map.get(f["away"], 0.0)},
                wx=WX.get((f["home"], f["Date"].date().isoformat()), 1.0),
                derby=frozenset((f["home"], f["away"])) in DERBY,
                travel=travel_km(f["home"], f["away"]))
            P, p_over, p_btts, top, top_p, rh, ra, lh, la = r[:9]
            if st is not None:  # 🆕 13/11 stacking: meta-learner su membri + GBM (4° membro)
                pg = gbm.predict_proba(r[12].reshape(1, -1))[0] if gbm is not None else None
                Ps = st.apply((r[9], r[10], r[11], pg))
                if Ps is not None:
                    P = Ps
            if cal is not None:  # 🆕 13/11 calibrazione isotonic sulle P finali
                P = cal.apply(P)
            _pv = PREV.get((league, f"{f['home']} - {f['away']}", f["Date"].strftime("%d/%m %H:%M")))
            if _pv is not None:  # 🆕 13/11 ensemble temporale con run precedente
                P = 0.65 * P + 0.35 * _pv
                P = P / P.sum()
            # 🆕 13/11 stacker binari O/U 2.5 e GG/NG (membri: DC + mercato)
            # 🆕 13/11-b niente NaN nelle feature dello stacker: se la quota mercato manca o è NaN,
            #    si passa il modello DC come fallback (prima NaN → stacker in errore o p_ou/p_gg NaN → stake 0)
            def _num(x):
                try:
                    v = float(x)
                    return v if np.isfinite(v) and v > 1.05 else None
                except Exception:
                    return None
            _qou, _qgg = _num(o_ex.get("O2.5")), _num(o_ex.get("GG"))
            pm_ou = (1.0 / _qou) if _qou else None
            p_over = float(p_over) if np.isfinite(float(p_over)) else 0.5
            if st_ou is not None:
                _x1 = pm_ou if pm_ou is not None else p_over
                p_over = float(st_ou.predict_proba(np.array([[p_over, _x1]]))[0][1])
            pm_gg = (1.0 / _qgg) if _qgg else None
            p_btts = float(p_btts) if np.isfinite(float(p_btts)) else 0.5
            if st_gg is not None:
                _x2 = pm_gg if pm_gg is not None else p_btts
                p_btts = float(st_gg.predict_proba(np.array([[p_btts, _x2]]))[0][1])
            pick = int(P.argmax())
            row = {
                "lega": league, "giornata": int(f["matchday"]),
                "orario": f["Date"].strftime("%d/%m %H:%M"),
                "partita": f"{f['home']} - {f['away']}",
                "p1%": round(P[0] * 100, 1), "pX%": round(P[1] * 100, 1), "p2%": round(P[2] * 100, 1),
                "pronostico": ["1", "X", "2"][pick], "conf%": round(P.max() * 100, 1),
                "Over2.5%": round(p_over * 100, 1), "BTTS%": round(p_btts * 100, 1),
                "corners_attesi": c_att, "CornersO95%": c_o95,
                "quota_C_O95_best": ck[0], "quota_C_U95_best": ck[1],
                "steam1": (round((o_max[0] / o_avg[0] - 1) * 100, 1) if (o_max and o_avg and o_avg[0]) else ""),
                "risultato+prob%": f"{top} ({top_p*100:.0f}%)",
                "quota_best": round(o_max[pick], 2) if o_max else "",
                "quota_media": round(o_avg[pick], 2) if o_avg else "",
                "quota_GG_best": o_ex.get("GG", ""), "quota_NG_best": o_ex.get("NG", ""),
                "quota_O25_best": o_ex.get("O2.5", ""), "quota_U25_best": o_ex.get("U2.5", ""),
                "motivo": motivo_match(f["home"], f["away"], f["Date"], played, rh, ra, lh, la,
                                       stand=stand, last=last, P=P, pick=pick,
                                       quota_best=(o_max[pick] if o_max else None),
                                       absences=(absences if league == "Serie A" else None),
                                       elo_raw=elo),
                "xg_h": round(float(lh), 3), "xg_a": round(float(la), 3),
                "perche": perche_breve(f["home"], f["away"], f["Date"], played, lh, la,
                                       stand=stand, last=last, P=P, pick=pick,
                                       quota_best=(o_max[pick] if o_max else None), elo_raw=elo),
                "motivo_verbale": _verbale_con_formazione(f, league, lineups, frase_motivo(
                                               f["home"], f["away"], f["Date"], played, rh, ra, lh, la,
                                               stand=stand, last=last, P=P, pick=pick,
                                               quota_best=(o_max[pick] if o_max else None),
                                               absences=(absences if league == "Serie A" else None),
                                               elo_raw=elo), absences),
                "formazione": _formazione_str(f, league, lineups),
            }
            if o_avg is not None:
                inv = 1 / np.array(o_avg, float)
                Pm = inv / inv.sum()
                edge = P - Pm
                j = int(np.argmax(np.abs(edge)))
                row["edge_vs_mercato"] = f"{edge[j]*100:+.1f}pp su {['1','X','2'][j]}"
                row["⚠️"] = "🚨" if abs(edge[j]) > 0.03 else ""
            rows.append(row)
        print(f"  ✅ {league}: {len(sub)} partite pronosticate (addestramento su {len(played)}, draw_base {draw_base:.3f})")

    fc = pd.DataFrame(rows)
    out = DATA / "forecast_multi.csv"
    fc.to_csv(out, index=False)
    # 🆕 06/11: salva separatamente le righe coppa (la finestra può non averne → coppe.html resta aggiornata)
    cups = fc[fc["lega"].isin(["Champions League", "Europa League", "Conference League"])]
    if len(cups):
        cups.to_csv(DATA / "forecast_coppe.csv", index=False)
        print(f"🏆 forecast_coppe.csv: {len(cups)} partite di coppa")
    print(f"\n💾 Salvato: {out} ({len(fc)} partite)")
    print(fc.sort_values("conf%", ascending=False).head(15).to_string(index=False))

    # 🎯 GIOCATA PER OGNI GIORNO della finestra (regola aggiornata dall'utente 03/11):
    #   per ogni data: SINGOLA = max probabilità del modello su TUTTI i mercati (qualsiasi quota)
    #   RADDOPPIO = 2-3 eventi su partite DIVERSE, qualsiasi mercato, quota combinata ≈ 2.00 (tie-break: EV più alta)
    g = fc[fc["quota_best"] != ""].copy()
    if g.empty:
        print("\n⚠️ Nessuna quota trovata nella finestra: giocata rimandata — le quote best-price vanno recuperate da wincomparator.")
        return
    g["quota_best"] = g["quota_best"].astype(float)
    pmap = {"1": "p1%", "X": "pX%", "2": "p2%"}
    g["p_pick"] = g.apply(lambda r: float(r[pmap[r["pronostico"]]]) / 100.0, axis=1)
    g["giorno"] = g["orario"].str.split(" ").str[0]          # dd/mm
    g["data"] = g["giorno"].apply(lambda d: f"2026-{d[3:5]}-{d[:2]}")  # ISO

    def build_pool(sub):
        pool = []
        for _, r in sub.iterrows():
            # motivo verbale del match su TUTTI i mercati (prima era solo 1X2 → mancavano i motivi su O/U/GG)
            mv = r.get("motivo_verbale") or r.get("motivo", "")
            legs = [("1X2", r["pronostico"], r["p_pick"], r["quota_best"], mv)]
            if str(r.get("quota_O25_best")) not in ("", "nan") and float(r["Over2.5%"]) > 0:
                legs.append(("O2.5", "Over 2.5", float(r["Over2.5%"]) / 100.0, float(r["quota_O25_best"]), mv))
            if str(r.get("quota_U25_best")) not in ("", "nan"):
                legs.append(("U2.5", "Under 2.5", 1 - float(r["Over2.5%"]) / 100.0, float(r["quota_U25_best"]), mv))
            if str(r.get("quota_GG_best")) not in ("", "nan"):
                legs.append(("GG", "GG", float(r["BTTS%"]) / 100.0, float(r["quota_GG_best"]), mv))
            if str(r.get("quota_NG_best")) not in ("", "nan"):
                legs.append(("NG", "NG", 1 - float(r["BTTS%"]) / 100.0, float(r["quota_NG_best"]), mv))
            # 🆕 06/11 mercato corner O/U 9.5 (quote football-data MaxC>2.5/MaxC<2.5, prob da Poisson su corners_attesi)
            if str(r.get("quota_C_O95_best")) not in ("", "nan") and str(r.get("CornersO95%")) not in ("", "nan"):
                legs.append(("C_O9.5", "Corner Over 9.5", float(r["CornersO95%"]) / 100.0, float(r["quota_C_O95_best"]), mv + f" · corner attesi {r.get('corners_attesi')}"))
                legs.append(("C_U9.5", "Corner Under 9.5", 1 - float(r["CornersO95%"]) / 100.0, float(r["quota_C_U95_best"]), mv + f" · corner attesi {r.get('corners_attesi')}"))
            for mercato, esito, p_leg, q_leg, mot in legs:
                ev = (p_leg * (q_leg - 1) - (1 - p_leg)) * 100
                # 🆕 13/11 "perché" parlante anche per O/U e GG/NG (dai gol attesi), non solo 1X2
                if mercato == "1X2":
                    p_leg_breve = (r.get("perche") or "")
                else:
                    p_leg_breve = "💬 " + perche_mercato(mercato, str(esito), float(r.get("xg_h") or 1.3), float(r.get("xg_a") or 1.3), q=q_leg, p=p_leg)
                if ev > 50:  # 🚨 quota anomala (es. 10.60 su un favorito): EV irrealistico → fuori dal pool
                    print(f"     🚨 quota anomala ignorata: {r['partita']} {mercato} {esito} @ {q_leg} (EV {ev:+.0f}%)")
                    continue
                pool.append({"lega": r["lega"], "partita": r["partita"], "mercato": mercato,
                             "esito": esito, "p": p_leg, "q": q_leg, "EV%": ev, "motivo": mot,
                             "perche": p_leg_breve})
        return pool

    # 🆕 13/11-b incertezza di p: oggetto Calib per lega → Calib.se_for(p)
    CALSE = {}
    try:
        for le, tup in domestic.items():
            c = tup[7]
            CALSE[le] = c if (c is not None and getattr(c, "irs", None)) else None
    except Exception:
        pass

    def se_pick(lega, p):
        """errore standard di p per la lega (None → fallback binomiale n_eff=50 dentro kelly_stake)."""
        c = CALSE.get(lega)
        try:
            return c.se_for(p) if c is not None else None
        except Exception:
            return None

    # 🆕 13/11 correlazione esiti stessa giornata (stimata dai dati, anti-correlata ~ -0.26):
    # EV del raddoppio usa p_eff = prod(p) + rho*... invece di prod(p) ingenua
    RHO = {"1X2": -0.276, "O/U": -0.279, "GG/NG": -0.230, "misto": -0.262}
    try:
        _rr = pd.read_csv(DATA / "rho_raddoppio.csv")
        RHO = {k: float(_rr.iloc[0][k]) for k in RHO}
    except Exception:
        pass
    def rho_for(combo):
        mk = {c["mercato"] for c in combo}
        if mk == {"1X2"}: return RHO["1X2"]
        if mk <= {"O2.5", "U2.5"}: return RHO["O/U"]
        if mk <= {"GG", "NG"}: return RHO["GG/NG"]
        return RHO["misto"]
    def p_eff(combo):
        ps = [c["p"] for c in combo]; r = rho_for(combo)
        pr = float(np.prod(ps))
        if len(ps) == 2:
            return pr + r * np.sqrt(ps[0]*(1-ps[0])*ps[1]*(1-ps[1]))
        t = [np.sqrt(x*(1-x)) for x in ps]
        return pr + r * (t[0]*t[1]*ps[2] + t[0]*t[2]*ps[1] + t[1]*t[2]*ps[0])

    def kelly_stake(p, O, se=None, n_eff=50, ev=None):
        """🆕 13/11 ¼ Kelly con incertezza di p (se da Brier/bootstrap, altrimenti sqrt(p(1-p)/n_eff)).
        🆕 13/11-b REGOLA D'ORDINE: lo stake parte SOLO se EV > +2% (prima bastava EV>0, quindi
        uno stake positivo poteva comparire sotto la soglia dichiarata sul sito)."""
        if ev is not None and ev <= 2.0:
            return 0.0                      # sotto +2% di EV: stake 0 per regola
        if se is None or (isinstance(se, float) and np.isnan(se)):
            se = np.sqrt(max(p*(1-p), 1e-9) / n_eff)   # 🆕 13/11-b NaN-safe (prima NaN azzerava lo stake)
        pl = max(0.0, p - se)
        f = (pl * O - 1.0) / (O - 1.0) if O > 1.0 else 0.0
        return min(max(0.0, f) / 4.0, 0.05)   # 🆕 13/11-b tetto 5% bankroll per voce (sanity cap)

    def pick(pool):
        # 🎯 regola utente 04/11: SOLO giocate con EV > 0 nei consigli del giorno
        #    (niente pronostici con EV negativa: se non ci sono, riga NESSUNA e stake 0)
        # 🆕 13/11-b FILTRO CALIBRAZIONE: se il modello è più "sicuro" del mercato di oltre
        #    10 punti percentuali, nella pratica è più spesso errore del modello che valore
        #    (misurato: 42% dei pick 1X2 della finestra superava i 10pp, con casi a +40pp).
        #    Le giocate pubblicate hanno ora gap 0-10pp → probabilità credibili.
        GAP_MAX = 10.0
        _gapped = []
        for c in pool:
            try:
                gap = c["p"] * 100.0 - (100.0 / float(c["q"]))
            except Exception:
                gap = 0.0
            c["gap_pp"] = round(gap, 1)
            if gap <= GAP_MAX:
                _gapped.append(c)
        pool = _gapped
        pos = [c for c in pool if c["EV%"] > 0]
        if not pos:
            return None, None, None, None, None
        singola = max(pos, key=lambda c: c["p"])
        best = None
        for size in (2, 3):
            for combo in itertools.combinations(pos, size):
                if len({c["partita"] for c in combo}) != size:
                    continue
                q = 1.0
                for c in combo:
                    q *= c["q"]
                p = p_eff(list(combo))  # 🆕 13/11 con correlazione (rho) — più onesto di prod(p)
                ev = (p * (q - 1) - (1 - p)) * 100
                if ev <= 0:
                    continue
                key = (abs(q - 2.00), -ev)
                if best is None or key < best[0]:
                    best = (key, combo, q, p, ev)
        if best is None:
            return singola, None, None, None, None
        _, combo, q, p, ev = best
        return singola, combo, q, p, ev

    def verdetto(ev):
        if ev >= 15: return "✅ VAI — edge forte (EV ≥ +15%): il valore atteso copre bene il margine di stima. Stima, non garanzia."
        if ev >= 5:  return "👍 VAI — edge buono (EV +5%…+15%): valore atteso positivo, stake ¼ Kelly. Stima, non garanzia."
        return "⚠️ BORDERLINE — edge minimo (EV < +5%): si Gioca solo se l'EV resta >0 dopo il margine di sicurezza ~2%. Stima, non garanzia."

    rows = []
    for data in sorted(g["data"].unique()):
        sub = g[g["data"] == data]
        pool = build_pool(sub)
        singola, combo, q, p, ev = pick(pool)
        giorno = data[8:] + "/" + data[5:7] + "/2026"
        print(f"\n📅 {giorno} — {len(sub)} partite con quote")
        if singola is not None:
            print(f"  🎯 SINGOLA: {singola['partita']} ({singola['lega']}) → {singola['mercato']} {singola['esito']} p={singola['p']*100:.1f}% @ {singola['q']} EV {singola['EV%']:+.2f}%")
            se1 = se_pick(singola["lega"], singola["p"])
            rows.append({"data": data, "tipo": "SINGOLA", "lega": singola["lega"], "partita": singola["partita"],
                         "mercato": singola["mercato"], "esito": str(singola["esito"]),
                         "p_modello%": round(singola["p"] * 100, 1), "quota_best": round(singola["q"], 2),
                         "EV%": round(singola["EV%"], 2), "motivo": singola["motivo"],
                         "perche": "💬 " + (singola.get("perche") or ""),
                         "gap_pp": singola.get("gap_pp", ""),
                         "stake%": round(kelly_stake(singola["p"], singola["q"], se=se1, ev=singola["EV%"]) * 100, 2),
                         "verdetto": verdetto(singola["EV%"])})
        if singola is None and combo is None:
            print("  ⛔ NESSUNA giocata con EV > 0: stake 0 (assenza di valore atteso, non un consiglio)")
            rows.append({"data": data, "tipo": "NESSUNA", "lega": "—",
                         "partita": f"{len(sub)} partite del giorno, nessuna Singola/Raddoppio con EV > 0",
                         "mercato": "—", "esito": "—", "p_modello%": "", "quota_best": "", "EV%": "",
                         "motivo": "Nessuna giocata del giorno ha EV positiva: per la regola EV>0 lo stake resta 0. Analisi statistica, non un consiglio di gioco.",
                         "verdetto": "⛔ NESSUNA — nessun EV>0 oggi: stake 0 per regola. Non è un consiglio di astensione dal gioco, è assenza di valore atteso."})
        if combo is not None:
            print(f"  🎯 RADDOPPIO: quota {q:.2f}, p {p*100:.1f}%, EV {ev:+.2f}%")
            for c in combo:
                print(f"     - {c['partita']} ({c['lega']}) → {c['mercato']} {c['esito']} p={c['p']*100:.1f}% @ {c['q']}")
            sem = float(np.mean([se_pick(c["lega"], c["p"]) or 0.03 for c in combo]))
            rows.append({"data": data, "tipo": "RADDOPPIO", "lega": " + ".join(sorted({c["lega"] for c in combo})),
                         "partita": " + ".join(f"{c['partita']} [{c['mercato']} {c['esito']}]" for c in combo),
                         "mercato": "/".join(c["mercato"] for c in combo), "esito": "/".join(str(c["esito"]) for c in combo),
                         "p_modello%": round(p * 100, 1), "quota_best": round(q, 2), "EV%": round(ev, 2),
                         "stake%": round(kelly_stake(p, q, se=sem, ev=ev) * 100, 2),
                         "motivo": " | ".join((f"{c['partita']} [{c['mercato']} {c['esito']}] p={c['p']*100:.1f}% @ {c['q']} — " + (c["motivo"][:240] + "…" if len(c["motivo"]) > 240 else c["motivo"])) for c in combo),
                         "perche": "💬 " + " · ".join((c.get("perche") or "").replace("💬 ","") for c in combo),
                         "verdetto": verdetto(ev)})

    gj = pd.DataFrame(rows)
    gout = DATA / "giocata_multi.csv"
    gj.to_csv(gout, index=False)
    print(f"\n💾 Salvato: {gout} ({len(gj)} righe: Singola+Raddoppio per ogni giorno)")


if __name__ == "__main__":
    main()
