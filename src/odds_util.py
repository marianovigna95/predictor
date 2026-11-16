#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odds_util.py — utilita' condivise per trattare le quote in modo corretto.
=======================================================================
Perche' esiste: il sito mostrava la "probabilita' implicita" come 1/quota, che
include il MARGINE del bookmaker (overround). Confrontare il modello con quella
probabilita' gonfia l'edge e fa scattare allarmi che non esistono.

Misurato sulle nostre quote (14/11, 96 partite):
  overround medio +1,59%
  scarto medio fra p grezza e p de-vig: 0,86 punti percentuali (fino a 1,6)

Contiene anche il CONTROLLO OVERROUND: un overround molto negativo significa che
le tre migliori quote insieme pagano piu' del dovuto. O e' arbitraggio reale
(raro, dura minuti) o sono quote stantie che nessun book accetterebbe: in quel
caso l'EV calcolato e' finto. Su 96 partite ne abbiamo trovate 15 sotto zero,
una a -19,45% (Lille-Lyon): quasi certamente quote vecchie.

Uso:
    from odds_util import devig, overround, quota_plausibile
"""


def overround(quote):
    """Somma delle probabilita' implicite grezze. 1.00 = mercato equo, >1 = margine."""
    qs = [float(q) for q in quote if q and float(q) > 1.0]
    if len(qs) < 2:
        return None
    return sum(1.0 / q for q in qs)


def devig(quote, metodo="proporzionale"):
    """Rimuove il margine: restituisce le probabilita' FAIR (somma = 1).

    proporzionale: p_i = (1/q_i) / somma(1/q)   — semplice, standard, conservativo
    power:         risolve k tale che somma((1/q_i)^k) = 1 — tiene conto del
                   favourite-longshot bias (sovrastima gli sfavoriti). Usato solo
                   se richiesto esplicitamente.
    """
    qs = [float(q) for q in quote]
    if any(q is None or q <= 1.0 for q in qs):
        return None
    inv = [1.0 / q for q in qs]
    tot = sum(inv)
    if metodo == "proporzionale" or tot <= 0:
        return [x / tot for x in inv]
    # power method
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        s = sum(x ** k for x in inv)
        if s > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    vals = [x ** k for x in inv]
    s = sum(vals)
    return [v / s for v in vals]


def quota_plausibile(quote, soglia_overround=-0.02):
    """True se le quote sono coerenti. False se l'overround e' cosi' negativo
    da far sospettare quote stantie o non giocabili insieme.

    soglia_overround = -0.02  →  scarta se le quote pagano oltre il 2% in piu'
    del dovuto (arbitraggi veri esistono ma durano minuti: per un sito di analisi
    e' piu' prudente scartare).
    """
    ov = overround(quote)
    if ov is None:
        return False, None
    return ov >= (1.0 + soglia_overround), ov
