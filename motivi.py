"""
🔍 MOTIVI — spiegazione leggibile (italiano) di ogni pronostico del modello.

Per ogni partita costruisce una stringa "motivo" con i fattori che hanno pesato:
  1. Elo delle due squadre (differenza punti)
  2. Forma recente (ultime 5 partite: gol fatti/subiti a testa)
  3. Gol attesi dal modello Dixon-Coles (attacco × difesa × media lega)
  4. Posizione in classifica
  5. Giorni di riposo dall'ultima partita (congestione)
  6. Assenze (penalità Elo, solo Serie A)
  7. Confronto quota di mercato vs probabilità del modello (edge in pp)

Non è una garanzia: è la "scatola trasparente" del perché il modello ha scelto un esito.
Uso:  from motivi import motivo_match
"""
import numpy as np
import pandas as pd

ESITI = ["1", "X", "2"]


def form_last(played, team, before, n=5):
    """Ultime n partite di `team` prima di `before` → (n, gol fatti, gol subiti)."""
    rows = []
    for _, m in played.iterrows():
        if m["Date"] >= before:
            continue
        if m["HomeTeam"] == team:
            rows.append((m["Date"], float(m["FTHG"]), float(m["FTAG"])))
        elif m["AwayTeam"] == team:
            rows.append((m["Date"], float(m["FTAG"]), float(m["FTHG"])))
    rows.sort(key=lambda r: r[0])
    last = rows[-n:]
    gf = sum(r[1] for r in last)
    ga = sum(r[2] for r in last)
    return len(last), gf, ga


def _pos(stand, team):
    if stand is not None and len(stand):
        s = stand.loc[stand["team"] == team, "pos"]
        if len(s):
            return int(s.iloc[0])
    return None


def motivo_match(home, away, date, played, rh, ra, lh, la, stand=None, last=None,
                 P=None, pick=None, quota_best=None, absences=None, elo_raw=None):
    """Ritorna la stringa-motivo per la partita home-vs-away alla data `date`.

    rh/ra: Elo (già con aggiustamenti classifica/riposo/assenze usati dal modello)
    lh/la: gol attesi Dixon-Coles · P: array [p1,pX,p2] · pick: indice 0/1/2
    quota_best: quota best-price dell'esito scelto (se disponibile)
    """
    seg = []
    # 1) Elo base (senza aggiustamenti di classifica/riposo)
    if elo_raw:
        eh, ea = elo_raw.get(home, 1500.0), elo_raw.get(away, 1500.0)
        d = eh - ea
        if abs(d) >= 20:
            lato = "casa" if d >= 0 else "trasferta"
            seg.append(f"Elo {lato} {'+' if d >= 0 else ''}{d:.0f} ({eh:.0f} vs {ea:.0f})")
    # 2) forma recente
    nH, gfH, gaH = form_last(played, home, date)
    nA, gfA, gaA = form_last(played, away, date)
    if nH and nA:
        seg.append(f"ultime {max(nH, nA)}: {home} {gfH / nH:.1f} gol fatti / {gaH / nH:.1f} subiti · "
                   f"{away} {gfA / nA:.1f} / {gaA / nA:.1f}")
    # 3) gol attesi dal modello
    seg.append(f"gol attesi (modello): {lh:.1f} - {la:.1f}")
    # 4) classifica
    pH, pA = _pos(stand, home), _pos(stand, away)
    if pH and pA:
        seg.append(f"classifica: {pH}° {home} vs {pA}° {away}")
    # 5) riposo / congestione
    if last is not None:
        dH = (date - last.get(home, date - pd.Timedelta(days=7))).days
        dA = (date - last.get(away, date - pd.Timedelta(days=7))).days
        if dH != dA:
            seg.append(f"riposo: {dH} gg {home} vs {dA} gg {away}")
    # 6) assenze
    if absences:
        ah, aa = absences.get(home), absences.get(away)
        bits = []
        if ah:
            bits.append(f"{home} −{ah} Elo")
        if aa:
            bits.append(f"{away} −{aa} Elo")
        if bits:
            seg.append("assenze: " + ", ".join(bits))
    # 7) edge vs quota di mercato
    if quota_best and P is not None and pick is not None:
        p_mod = float(P[pick])
        p_impl = 1.0 / float(quota_best)
        seg.append(f"quota {float(quota_best):.2f} (mercato {p_impl * 100:.1f}%) "
                   f"vs modello {p_mod * 100:.1f}% → edge {(p_mod - p_impl) * 100:+.1f}pp")
    return " · ".join(seg) if seg else "dati limitati"


PICK_LABEL = ["vittoria della casa", "pareggio", "vittoria in trasferta"]


def frase_motivo(home, away, date, played, rh, ra, lh, la, stand=None, last=None,
                 P=None, pick=None, quota_best=None, absences=None, elo_raw=None):
    """Spiegazione IN PAROLE (frase leggibile) del perché il modello ha scelto `pick`.
    Ritorna una frase in italiano, es.:
    "Il modello punta sulla vittoria della casa (Sassuolo) perché ... Resta una stima con incertezza."
    """
    if pick is None:
        pick = int(np.argmax(P)) if P is not None else 0
    label = PICK_LABEL[pick]
    frasi = []
    # Elo in parole
    if elo_raw:
        eh, ea = elo_raw.get(home, 1500.0), elo_raw.get(away, 1500.0)
        d = eh - ea
        if abs(d) >= 20:
            forte, debole = (home, away) if d > 0 else (away, home)
            frasi.append(f"secondo l'Elo {forte} è più forte di circa {abs(d):.0f} punti "
                         f"({max(eh, ea):.0f} contro {min(eh, ea):.0f})")
    # forma in parole
    nH, gfH, gaH = form_last(played, home, date)
    nA, gfA, gaA = form_last(played, away, date)
    if nH and nA:
        frasi.append(f"nelle ultime {max(nH, nA)} partite {home} ha fatto {gfH / nH:.1f} gol a partita "
                     f"subendone {gaH / nH:.1f}, {away} {gfA / nA:.1f} fatti e {gaA / nA:.1f} subiti")
    # gol attesi in parole
    if lh > la + 0.15:
        frasi.append(f"il modello si aspetta più gol per {home} ({lh:.1f} contro {la:.1f} di {away})")
    elif la > lh + 0.15:
        frasi.append(f"il modello si aspetta più gol per {away} ({la:.1f} contro {lh:.1f} di {home})")
    else:
        frasi.append(f"gol attesi quasi pari ({lh:.1f} - {la:.1f})")
    # classifica in parole
    pH, pA = _pos(stand, home), _pos(stand, away)
    if pH and pA:
        if pH < pA:
            frasi.append(f"in classifica {home} è sopra ({pH}° contro {pA}°)")
        elif pA < pH:
            frasi.append(f"in classifica {away} è sopra ({pA}° contro {pH}°), e questo pesa a sfavore di {home}")
    # riposo in parole
    if last is not None:
        dH = (date - last.get(home, date - pd.Timedelta(days=7))).days
        dA = (date - last.get(away, date - pd.Timedelta(days=7))).days
        if dH < dA:
            frasi.append(f"{home} arriva da soli {dH} giorni di riposo contro {dA} di {away} (più stanca)")
        elif dA < dH:
            frasi.append(f"{away} arriva da soli {dA} giorni di riposo contro {dH} di {home} (più stanca)")
    # assenze in parole
    if absences:
        ah, aa = absences.get(home), absences.get(away)
        if ah:
            frasi.append(f"{home} ha assenze pesanti (penalità −{ah} punti Elo)")
        if aa:
            frasi.append(f"{away} ha assenze (penalità −{aa} punti Elo)")
    # edge vs quota in parole
    edge_txt = ""
    if quota_best and P is not None:
        p_mod = float(P[pick])
        p_impl = 1.0 / float(quota_best)
        e = (p_mod - p_impl) * 100
        if e > 3:
            edge_txt = (f"La quota di {float(quota_best):.2f} fa sembrare l'esito meno probabile "
                        f"({p_impl * 100:.1f}%) di quanto lo stimi il modello ({p_mod * 100:.1f}%): "
                        f"c'è un margine (edge +{e:.1f} punti %) a favore della scelta.")
        elif e < -3:
            edge_txt = (f"La quota di {float(quota_best):.2f} è più alta di quanto il modello reputi giusto "
                        f"(mercato {p_impl * 100:.1f}% vs modello {p_mod * 100:.1f}%, edge {e:.1f} pp): "
                        f"il mercato la sopravvaluta.")
        else:
            edge_txt = (f"Quota {float(quota_best):.2f} (mercato {p_impl * 100:.1f}%) e modello "
                        f"({p_mod * 100:.1f}%) sono in linea (edge {e:+.1f} pp).")
    corpo = "; ".join(frasi[:4]) if frasi else "i dati disponibili sono pochi"
    return (f"Il modello punta su «{label}» ({home} - {away}). Perché: {corpo}. {edge_txt} "
            f"Resta una stima con incertezza, non una certezza.")
