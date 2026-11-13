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


PICK_SHORT = ["la vittoria della casa", "il pareggio", "la vittoria in trasferta"]


def perche_breve(home, away, date, played, lh, la, stand=None, last=None,
                 P=None, pick=None, quota_best=None, elo_raw=None):
    """🆕 13/11 — UNA frase diretta sul PERCHÉ del pronostico (max ~170 caratteri).
    Prende i 2 fattori più parlanti + il margine vs quota, in italiano semplice."""
    if pick is None:
        pick = int(np.argmax(P)) if P is not None else 0
    factors = []
    # forma: chi sta meglio in gol fatti/subiti
    nH, gfH, gaH = form_last(played, home, date)
    nA, gfA, gaA = form_last(played, away, date)
    if nH and nA:
        fh, fa = gfH / nH, gfA / nA
        sh, sa = gaH / nH, gaA / nA
        best = home if (fh - sh) > (fa - sa) else away
        worst = away if best == home else home
        diff = abs((fh - sh) - (fa - sa))
        if diff >= 0.6:
            bf, bs = (fh, sh) if best == home else (fa, sa)
            factors.append(f"{best} è in forma ({bf:.1f} gol/partita, solo {bs:.1f} subiti) contro {worst}")
    # gol attesi
    if lh > la + 0.25:
        factors.append(f"si aspettano più gol per {home} ({lh:.1f}-{la:.1f})")
    elif la > lh + 0.25:
        factors.append(f"si aspettano più gol per {away} ({la:.1f}-{lh:.1f})")
    # classifica
    pH, pA = _pos(stand, home), _pos(stand, away)
    if pH and pA and pH != pA:
        top, bp = (home, pH) if pH < pA else (away, pA)
        factors.append(f"in classifica {top} è {bp}°")
    # elo
    if elo_raw:
        eh, ea = elo_raw.get(home, 1500.0), elo_raw.get(away, 1500.0)
        if abs(eh - ea) >= 25:
            forte = home if eh > ea else away
            factors.append(f"{forte} parte favorita (forza Elo {abs(eh-ea):.0f} punti in più)")
    corpo = "; ".join(factors[:2]) if factors else "dati simili per le due squadre"
    # margine quota in parole semplici
    margine = ""
    if quota_best and P is not None:
        q = float(quota_best); p_mod = float(P[pick]); p_impl = 1.0 / q
        e = (p_mod - p_impl) * 100
        if e >= 2:
            margine = f" La quota {q:.2f} paga come se valesse {p_impl*100:.0f}%, il modello invece lo dà al {p_mod*100:.0f}%: c'è margine."
        elif e <= -2:
            margine = f" Attenzione: la quota {q:.2f} sembra alta rispetto al modello ({p_mod*100:.0f}%)."
    return f"Perché {PICK_SHORT[pick]}: {corpo}.{margine}"



def perche_mercato(mercato, esito, lh, la, q=None, p=None):
    """🆕 13/11 — frase breve "perché" per mercati O/U 2.5 e GG/NG (basata sui gol attesi)."""
    tot = lh + la
    if mercato in ("O2.5", "U2.5"):
        label = "Over 2.5" if mercato == "O2.5" else "Under 2.5"
        base = f"si aspettano {tot:.1f} gol in totale" + (", sopra la media delle leghe (~2.6)" if tot > 2.6 else ", sotto la media (~2.6)")
    elif mercato in ("GG", "NG"):
        label = esito
        if mercato == "GG":
            base = f"gol attesi per entrambe ({lh:.1f} e {la:.1f}): è plausibile che segnino tutte e due"
        else:
            base = f"gol attesi {lh:.1f} - {la:.1f}: difficile che segnino entrambe"
    else:
        label = esito
        base = f"gol attesi {lh:.1f} - {la:.1f}"
    margine = ""
    if q and p:
        impl = 100.0 / float(q)
        if p * 100 - impl >= 2:
            margine = f" La quota {float(q):.2f} paga come se valesse {impl:.0f}%, il modello invece dà {p*100:.0f}%: c'è margine."
    return f"Perché {label}: {base}.{margine}"
