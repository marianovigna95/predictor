#!/usr/bin/env python3
"""step13_player_xg.py — xG mancante VERO dagli assenti (sostituisce il proxy n_out×λ/11).

1. Squadre con assenti = absences.csv + indisponibili_euro.csv (~36 squadre)
2. Match recientes (dal 2026-09-20) di quelle squadre → pageUrl da FotMob league fixtures
3. Per ogni match page: playerStats → xG per giocatore ("Expected goals (xG)")
4. Rolling per giocatore: xG/match ultime 6 partite (half-life 3)
5. missing_xg per squadra = somma xG/match degli assenti (match per cognome)

Output: data/player_xg_rolling.csv  (player, team, xg_match, n, last)
        data/missing_xg.csv         (team, xg_mancante, detail)
Uso:  python3 src/step13_player_xg.py [--since 2026-09-20]
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step9_fotmob_xg import get, next_data  # noqa: E402
from step1b_fixtures_leagues import LEAGUES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CUP_IDS = [42, 73, 10216]  # CL, EL, UECL


def norm_name(t):
    t = str(t).lower()
    t = re.sub(r"[^a-zàèéìciòù ]", " ", t)
    return " ".join(t.split())


def surname_key(t):
    """chiave cognome: ultimo token 'pulito' del nome (es. 'Bukayo Saka'→'saka', 'Cissè M.K.'→'cissè')."""
    n = norm_name(t)
    toks = [x for x in n.split() if len(x) > 2 and x not in ("jr", "sr", "am", "mk", "di", "da", "de", "van", "del")]
    return toks[-1] if toks else n.replace(" ", "")


def player_xg_from_page(html):
    """ritorna [(player_id, name, teamName, xg)] dalla pagina match FotMob."""
    try:
        pp = next_data(html)["props"]["pageProps"]["content"]["playerStats"]
    except Exception:
        return []
    out = []
    for pid, p in pp.items():
        xg = None
        for grp in p.get("stats", []):
            for s in grp.get("stats", {}).items() if isinstance(grp.get("stats"), dict) else []:
                pass
            st = grp.get("stats", [])
            if isinstance(st, dict):
                st = list(st.values())
            for s in st:
                title = str(s.get("title", "")).lower()
                if "expected goals (xg)" in title and "xgot" not in title and "non-penalty" not in title:
                    v = s.get("stats") or {}
                    if isinstance(v, dict):
                        val = v.get("value") or v.get("home") or list(v.values())[0] if v else None
                    else:
                        val = s.get("value")
                    try:
                        xg = float(val)
                    except Exception:
                        xg = None
        # fallback: somma shotmap expectedGoals
        if xg is None:
            xg = round(sum(float(s.get("expectedGoals") or 0) for s in p.get("shotmap", [])), 4)
        out.append((int(pid), p.get("name", ""), p.get("teamName", ""), xg))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-20")
    args = ap.parse_args()

    # squadre con assenti
    teams = set()
    for f in ["indisponibili_euro.csv", "absences.csv"]:
        p = DATA / f
        if p.exists():
            df = pd.read_csv(p)
            col = "team" if "team" in df.columns else df.columns[0]
            teams |= set(df[col].unique())
    print(f"👥 squadre con assenti: {len(teams)}")

    # matchId -> pageUrl da tutte le league fixtures (nazionali + coppe)
    id2url = {}
    for lid in list({v[0] for v in LEAGUES.values()}) + CUP_IDS:
        try:
            nd = next_data(get(f"https://fotmob.com/leagues/{lid}/fixtures"))
            stack = [nd]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    if "pageUrl" in o and "id" in o and str(o.get("notStarted")) == "False":
                        id2url[str(o["id"])] = "https://fotmob.com" + str(o["pageUrl"]).split("#")[0]
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
        except Exception as e:
            print(f"  ⚠️ league {lid}: {str(e)[:50]}")
    print(f"🗺️ matchId→url: {len(id2url)}")

    # match target
    xg = pd.read_csv(DATA / "xg_fotmob_all.csv")
    xg["date"] = pd.to_datetime(xg["date"])
    sel = xg[(xg["home"].isin(teams) | xg["away"].isin(teams)) & (xg["date"] >= args.since)]
    mids = sorted(set(sel["matchId"].astype(str)) & set(id2url))
    print(f"📥 match da scaricare: {len(mids)} (dal {args.since})")

    rows = []
    for i, mid in enumerate(mids):
        try:
            html = get(id2url[mid])
            # data match da next_data general
            nd = next_data(html)
            g = nd["props"]["pageProps"].get("general", {})
            dt = str(g.get("matchTimeUTC") or g.get("utcTime") or "")[:10]
            for pid, name, team, xgv in player_xg_from_page(html):
                if xgv is not None:
                    rows.append({"matchId": mid, "date": dt, "player_id": pid, "player": name,
                                 "team": team, "xg": xgv})
        except Exception as e:
            print(f"  ⚠️ {mid}: {str(e)[:50]}")
        if (i + 1) % 25 == 0:
            print(f"  … {i+1}/{len(mids)}")
        time.sleep(0.25)

    px = pd.DataFrame(rows)
    px.to_csv(DATA / "player_xg_raw.csv", index=False)
    print(f"💾 player_xg_raw.csv: {len(px)} righe giocatore-match")

    # rolling per giocatore: ultime 6 partite per data, half-life 3
    px = px.dropna(subset=["date"]).copy()
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px = px.dropna(subset=["date"]).sort_values("date")
    roll = []
    for (pid, name, team), g in px.groupby(["player_id", "player", "team"]):
        g = g.sort_values("date").tail(6)
        if len(g) == 0:
            continue
        w = 0.5 ** (np.arange(len(g))[::-1] / 3.0)  # type: ignore[name-defined]
        import numpy as np
        w = 0.5 ** (np.arange(len(g))[::-1] / 3.0)
        xgm = float((g["xg"] * w).sum() / w.sum())
        roll.append({"player": name, "team": team, "xg_match": round(xgm, 3),
                     "n": len(g), "last": g["date"].max().date().isoformat()})
    pr = pd.DataFrame(roll).sort_values("xg_match", ascending=False)
    pr.to_csv(DATA / "player_xg_rolling.csv", index=False)
    print(f"💾 player_xg_rolling.csv: {len(pr)} giocatori (top: {pr.head(3).to_dict('records')})")

    # missing xG per squadra dagli assenti
    ie = pd.read_csv(DATA / "indisponibili_euro.csv")
    out = []
    for team, g in ie.groupby("team"):
        tot = 0.0
        det = []
        prt = pr[pr["team"].str.lower() == str(team).lower()]
        for _, r in g.iterrows():
            key = surname_key(r["giocatore"])
            cand = prt[prt["player"].map(lambda n: surname_key(n) == key)]
            if len(cand):
                v = float(cand.iloc[0]["xg_match"])
            else:
                # fuzzy: token del giocatore presente nel nome
                cand = prt[prt["player"].map(lambda n: key in norm_name(n))]
                v = float(cand.iloc[0]["xg_match"]) if len(cand) else 0.0
            tot += v
            det.append(f"{r['giocatore']}→{v:.2f}")
        out.append({"team": team, "xg_mancante": round(tot, 3), "n_out": len(g), "detail": "; ".join(det)})
    mx = pd.DataFrame(out).sort_values("xg_mancante", ascending=False)
    mx.to_csv(DATA / "missing_xg.csv", index=False)
    print(f"💾 missing_xg.csv: {len(mx)} squadre — top: {mx.head(5).to_dict('records')}")


if __name__ == "__main__":
    main()
