#!/usr/bin/env python3
"""step11_clv.py — CLV (Closing Line Value) delle giocate archiviate.

CLV = quota a cui abbiamo quotato la giocata (quota_best al forecast) − quota di chiusura media
(AvgH/D/A per 1X2, Avg>2.5 / Avg<2.5 per O/U). CLV > 0 = battuto il mercato di chiusura.

Uso: python3 src/step11_clv.py   →  data/clv_report.csv + stampa riepilogo
Nota: le coppe non hanno chiusure in football-data (Div senza UCL/UEL) → escluse.
Mercati GG/NG non hanno colonna di chiusura dedicata → escluse (solo 1X2, O2.5, U2.5).
"""
import glob
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "src"))
from step1b_fixtures_leagues import LEAGUES  # noqa: E402

LEAGUE2DIV = {name: code for code, (lid, name) in LEAGUES.items()}
# mercato giocata -> colonna chiusura in fixtures_all
MKT2CLOSE = {"1X2": None, "O2.5": "Avg>2.5", "U2.5": "Avg<2.5"}  # chiusure in matches.csv


def main():
    # 🆕 06/11 chiusure da matches.csv (football-data): TUTTE le leghe, AvgCH/CD/CA + Avg>2.5/Avg<2.5 (coppe escluse: non in football-data)
    fa = pd.read_csv(os.path.join(DATA, "matches.csv"), low_memory=False)
    fa["Date"] = pd.to_datetime(fa["Date"], errors="coerce")
    fa = fa.dropna(subset=["Date"])
    for c in ["AvgCH", "AvgCD", "AvgCA", "Avg>2.5", "Avg<2.5"]:
        if c in fa.columns:
            fa[c] = pd.to_numeric(fa[c], errors="coerce")
    nn = lambda t: "".join(c for c in str(t).lower() if c.isalnum())
    close = {}
    for _, r in fa.iterrows():
        close[(r["League"], r["Date"].normalize(), nn(r["HomeTeam"]), nn(r["AwayTeam"]))] = r

    fx = pd.read_csv(os.path.join(DATA, "fixtures_leagues.csv"))
    fx["Date"] = pd.to_datetime(fx["date"], errors="coerce")

    rows = []
    for vf in sorted(glob.glob(os.path.join(DATA, "verifica_*.csv"))):
        v = pd.read_csv(vf)
        for _, r in v.iterrows():
            if str(r.get("vinto")) not in ("✅", "❌"):
                continue
            d = pd.Timestamp(r["data"])
            legs = re.findall(r"(.+?) \[([^\]]+)\]", str(r["partita"]))
            if not legs:  # singola: partita dritta
                legs = [(str(r["partita"]), f'{r.get("mercato")} {r.get("esito")}')]
            for part, tag in legs:
                part = part.strip().lstrip("+").strip()
                m = re.match(r"(.+?) - (.+)$", part)
                if not m:
                    continue
                h, a = m.group(1), m.group(2)
                mkt = tag.split()[0]
                if mkt not in MKT2CLOSE:
                    continue
                cand = fx[(fx["Date"].dt.normalize() == d.normalize()) &
                          (fx["home"].str.strip() == h) & (fx["away"].str.strip() == a)]
                if cand.empty:
                    continue
                cr = cand.iloc[0]
                cl = close.get((cr["league"], d.normalize(), nn(cr["home"]), nn(cr["away"])))
                if cl is None:
                    continue
                if mkt == "1X2":
                    pick = str(r.get("esito")).strip()
                    col = {"1": "AvgCH", "X": "AvgCD", "2": "AvgCA"}.get(pick)
                    if col is None or pd.isna(cl.get(col)):
                        continue
                    q_close = float(cl[col])
                else:
                    col = MKT2CLOSE[mkt]
                    if pd.isna(cl.get(col)):
                        continue
                    q_close = float(cl[col])
                # quota della giocata su quel mercato: per simplicity usa quota_best della riga (singola) —
                # per i raddoppi approssimiamo con la quota del leg non disponibile: saltare se raddoppio multi-leg
                if len(legs) > 1:
                    continue
                qb = pd.to_numeric(pd.Series([r.get("quota_best")]), errors="coerce").iloc[0]
                if pd.isna(qb):
                    continue
                rows.append({"verifica": os.path.basename(vf), "data": r["data"], "partita": f"{h} - {a}",
                             "mercato": mkt, "esito": tag, "quota_pick": float(qb),
                             "quota_chiusura": round(q_close, 3),
                             "CLV": round(float(qb) - q_close, 3), "vinto": r["vinto"]})
    # 🆕 06/11 CLV manuale: l'utente incolla le quote di CHIUSURA lette a mano da Pinnacle/oddsportal
    # in data/clv_manuale.csv con colonne: data,partita,quota_chiusura  (partita = "Casa - Ospite" della giocata)
    man = os.path.join(DATA, "clv_manuale.csv")
    if os.path.exists(man):
        mv = pd.read_csv(man)
        gfiles = sorted(glob.glob(os.path.join(DATA, "giocata_*.csv"))) + sorted(glob.glob(os.path.join(DATA, "verifica_*.csv")))
        g = pd.concat([pd.read_csv(gf) for gf in gfiles], ignore_index=True) if gfiles else pd.DataFrame()
        for _, m in mv.iterrows():
            d = str(m["data"])
            cand = g[g["data"].astype(str).str.startswith(d)]
            qb = None
            for _, gr in cand.iterrows():
                if str(m["partita"]).split(" [")[0].strip().lower() in str(gr["partita"]).lower():
                    qb = pd.to_numeric(pd.Series([gr.get("quota_best")]), errors="coerce").iloc[0]
                    mkt = str(m.get("mercato") or gr.get("mercato") or "")
                    if mkt not in ("1X2", "O2.5", "U2.5", "GG", "NG"):
                        mkt = str(gr.get("mercato"))
                    esito = gr.get("esito"); vero = gr.get("vinto", "")
                    break
            if qb is None or pd.isna(qb):
                continue
            qc = float(m["quota_chiusura"])
            rows.append({"verifica": "manuale(Pinnacle/oddsportal)", "data": d,
                         "partita": str(m["partita"]), "mercato": mkt, "esito": esito,
                         "quota_pick": float(qb), "quota_chiusura": round(qc, 3),
                         "CLV": round(float(qb) - qc, 3), "vinto": vero if 'vero' in dir() else ""})
        print(f"✍️ CLV manuali aggiunti: {len(mv)} righe da clv_manuale.csv")

    # 🆕 06/11 CLV automatico da Hugging Face (minmaxxxer/premier-league-odds-2026-27): chiusure fair (no-vig) PL
    # refresh: curl -L -o data/hf_pl_closing_2627.csv "https://huggingface.co/datasets/minmaxxxer/premier-league-odds-2026-27/resolve/main/premier_league_2026_27_odds.csv"
    hf = os.path.join(DATA, "hf_pl_closing_2627.csv")
    if os.path.exists(hf):
        hfd = pd.read_csv(hf)
        hfd["d"] = pd.to_datetime(hfd["date_uk"], errors="coerce").dt.normalize()
        nn = lambda t: "".join(c for c in str(t).lower() if c.isalnum())
        hmap = {}
        for _, r in hfd.iterrows():
            hmap[(r["d"], nn(r["home_team"]), nn(r["away_team"]))] = r
        gfiles = sorted(glob.glob(os.path.join(DATA, "giocata_*.csv")))
        g = pd.concat([pd.read_csv(gf) for gf in gfiles], ignore_index=True) if gfiles else pd.DataFrame()
        added = 0
        for _, gr in g.iterrows():
            if str(gr.get("lega")) != "Premier League":
                continue
            d = pd.Timestamp(gr["data"])
            m = re.match(r"(.+?)\s*-\s*(.+?)(?:\s*\[|$)", str(gr["partita"]))
            if not m:
                continue
            key = (d.normalize(), nn(m.group(1)), nn(m.group(2)))
            r = hmap.get(key)
            if r is None:
                continue
            qb = pd.to_numeric(pd.Series([gr.get("quota_best")]), errors="coerce").iloc[0]
            if pd.isna(qb):
                continue
            mkt = str(gr.get("mercato"))
            if mkt == "1X2":
                col = {"1": "close_fair_home_odds", "X": "close_fair_draw_odds", "2": "close_fair_away_odds"}.get(str(gr.get("esito")).strip())
            elif mkt == "O2.5":
                col = None
                if pd.notna(r.get("close_over25_prob")):
                    qc_ou = round(1.0 / float(r["close_over25_prob"]), 3)
                    rows.append({"verifica": "HF-closing-fair", "data": gr["data"], "partita": f'{m.group(1)} - {m.group(2)}',
                                 "mercato": mkt, "esito": gr.get("esito"), "quota_pick": float(qb),
                                 "quota_chiusura": qc_ou, "CLV": round(float(qb) - qc_ou, 3), "vinto": gr.get("vinto", "")})
                    added += 1
                    continue
            elif mkt == "U2.5":
                if pd.notna(r.get("close_over25_prob")):
                    qc_ou = round(1.0 / (1.0 - float(r["close_over25_prob"])), 3)
                    rows.append({"verifica": "HF-closing-fair", "data": gr["data"], "partita": f'{m.group(1)} - {m.group(2)}',
                                 "mercato": mkt, "esito": gr.get("esito"), "quota_pick": float(qb),
                                 "quota_chiusura": qc_ou, "CLV": round(float(qb) - qc_ou, 3), "vinto": gr.get("vinto", "")})
                    added += 1
                    continue
                col = None
            elif mkt == "GG":
                if pd.notna(r.get("close_btts_prob")):
                    qc_gg = round(1.0 / float(r["close_btts_prob"]), 3)
                    rows.append({"verifica": "HF-closing-fair", "data": gr["data"], "partita": f'{m.group(1)} - {m.group(2)}',
                                 "mercato": mkt, "esito": gr.get("esito"), "quota_pick": float(qb),
                                 "quota_chiusura": qc_gg, "CLV": round(float(qb) - qc_gg, 3), "vinto": gr.get("vinto", "")})
                    added += 1
                    continue
                col = None
            else:
                col = None
            if col is None or pd.isna(r.get(col)):
                continue
            qc = float(r[col])
            rows.append({"verifica": "HF-closing-fair", "data": gr["data"], "partita": f'{m.group(1)} - {m.group(2)}',
                         "mercato": mkt, "esito": gr.get("esito"), "quota_pick": float(qb),
                         "quota_chiusura": round(qc, 3), "CLV": round(float(qb) - qc, 3), "vinto": gr.get("vinto", "")})
            added += 1
        print(f"🇬🇧 CLV da HF closing-fair (PL): {added} giocate")

    # 🆕 06/11 CLV automatico da BetArchives (closing odds, TUTTE le leghe + COPPE) — step15_betarchives.py
    ba_p = os.path.join(DATA, "betarchives_closing.csv")
    if os.path.exists(ba_p):
        ba = pd.read_csv(ba_p)
        nn = lambda t: "".join(c for c in str(t).lower() if c.isalnum())
        bmap = {}
        for _, r in ba.iterrows():
            bmap[(str(r["data"])[:10], nn(r["home"]), nn(r["away"]))] = r
            bmap[(str(r["data"])[:10], nn(r["away"]), nn(r["home"]))] = r
        gfiles = sorted(glob.glob(os.path.join(DATA, "giocata_*.csv"))) + sorted(glob.glob(os.path.join(DATA, "verifica_*.csv")))
        g = pd.concat([pd.read_csv(gf) for gf in gfiles], ignore_index=True) if gfiles else pd.DataFrame()
        added = 0
        for _, gr in g.iterrows():
            d = str(gr["data"])[:10]
            raw = str(gr.get("partita", ""))
            for part in re.split(r" \+ ", raw):
                part = re.sub(r"\s*\[[^\]]*\]", "", part).strip()
                m = re.match(r"(.+?) - (.+)$", part)
                if not m:
                    continue
                r = bmap.get((d, nn(m.group(1)), nn(m.group(2))))
                if r is None:
                    continue
                mkt = str(gr.get("mercato") or "")
                if "[" in raw:  # raddoppio: mercato combinato → usa il mercato del leg dal tag
                    tag = re.search(re.escape(part) + r"\s*\[([^\]]+)\]", raw)
                    if tag:
                        mkt = tag.group(1).split()[0]
                qb = pd.to_numeric(pd.Series([gr.get("quota_best")]), errors="coerce").iloc[0]
                if pd.isna(qb):
                    continue
                # 🆕 raddoppio: CLV sul PRODOTTO delle chiusure dei leg (quota_best è la combinata)
                if "+" in raw:
                    legs = []
                    ok = True
                    for part in re.split(r" \+ ", raw):
                        partc = re.sub(r"\s*\[[^\]]*\]", "", part).strip()
                        mm = re.match(r"(.+?) - (.+)$", partc)
                        tag = re.search(re.escape(partc) + r"\s*\[([^\]]+)\]", raw)
                        if not mm or not tag:
                            ok = False; break
                        rr = bmap.get((d, nn(mm.group(1)), nn(mm.group(2))))
                        if rr is None:
                            ok = False; break
                        lmkt = tag.group(1).split()[0]
                        if lmkt == "1X2":
                            lcol = {"1": "close_1", "X": "close_X", "2": "close_2"}.get(tag.group(1).split()[1] if len(tag.group(1).split()) > 1 else "")
                        elif lmkt.startswith("C_O"):
                            lcol = "corner_over"
                        elif lmkt.startswith("C_U"):
                            lcol = "corner_under"
                        else:
                            lcol = {"O2.5": "close_O25", "U2.5": "close_U25", "GG": "close_GG", "NG": "close_NG"}.get(lmkt)
                        if lcol is None or pd.isna(rr.get(lcol)):
                            ok = False; break
                        legs.append(float(rr[lcol]))
                    if ok and legs:
                        qc_combo = 1.0
                        for lv in legs:
                            qc_combo *= lv
                        rows.append({"verifica": "BetArchives-closing", "data": d, "partita": raw,
                                     "mercato": "RADD(combo)", "esito": gr.get("esito"), "quota_pick": float(qb),
                                     "quota_chiusura": round(qc_combo, 3), "CLV": round(float(qb) - qc_combo, 3), "vinto": gr.get("vinto", "")})
                        added += 1
                    continue
                colmap = {"1X2": None, "O2.5": "close_O25", "U2.5": "close_U25", "GG": "close_GG", "NG": "close_NG"}
                if mkt == "1X2":
                    col = {"1": "close_1", "X": "close_X", "2": "close_2"}.get(str(gr.get("esito")).strip())
                elif mkt.startswith("C_O"):
                    col = "corner_over"
                elif mkt.startswith("C_U"):
                    col = "corner_under"
                else:
                    col = colmap.get(mkt)
                if col is None or pd.isna(r.get(col)):
                    continue
                qc = float(r[col])
                rows.append({"verifica": "BetArchives-closing", "data": d, "partita": f"{m.group(1)} - {m.group(2)}",
                             "mercato": mkt, "esito": gr.get("esito"), "quota_pick": float(qb),
                             "quota_chiusura": round(qc, 3), "CLV": round(float(qb) - qc, 3), "vinto": gr.get("vinto", "")})
                added += 1
        print(f"📦 CLV da BetArchives (tutte leghe + coppe): {added} giocate")

    df = pd.DataFrame(rows)
    if len(df):
        # riempi 'vinto' dai file verifica_* (match fuzzy su data+partita)
        import glob as _glob
        vmap = {}
        for vf in _glob.glob(os.path.join(DATA, "verifica_*.csv")):
            try:
                vv = pd.read_csv(vf)
            except Exception:
                continue
            for _, vr in vv.iterrows():
                if str(vr.get("vinto")) in ("✅", "❌"):
                    vmap[(str(vr["data"]), nn(vr["partita"]))] = vr["vinto"]
        if vmap:
            df["vinto"] = [vmap.get((str(r["data"]), nn(r["partita"])), r.get("vinto", "")) for _, r in df.iterrows()]
        df = df.drop_duplicates(subset=["verifica", "data", "partita", "mercato"]).reset_index(drop=True)
    out = os.path.join(DATA, "clv_report.csv")
    df.to_csv(out, index=False)
    if len(df):
        print(f"💾 {out}: {len(df)} giocate con CLV")
        print(f"   CLV medio: {df['CLV'].mean():+.3f}  |  % CLV>0: {(df['CLV']>0).mean()*100:.0f}%  |  mediana: {df['CLV'].median():+.3f}")
        print(df.to_string(index=False))
    else:
        print("Nessuna riga CLV calcolabile (pochi leg 1X2/O/U archiviati finora).")


if __name__ == "__main__":
    main()
