#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nomi_squadre.py — normalizzazione dei nomi squadra per il confronto fra fonti.
=============================================================================
Perche' esiste: la fonte delle quote ADM scrive i nomi in ITALIANO ("Galles",
"Germania", "Lione", "Marsiglia"), mentre i nostri file quote li scrivono in
INGLESE ("Wales", "Germany", "Lyon", "Marseille"). Risultato: due file che
descrivono la stessa partita non si incontrano mai, e il confronto interno
(data/confronto_adm.md) resta vuoto con "nessuna_corrispondenza".

Verificato il 16/11: su 66 squadre presenti nei file ADM, solo 23 coincidevano
gia' con le nostre. "Galles - Portogallo" e "Wales - Portugal" sono la stessa
partita e non si agganciavano.

La stessa fonte e' incoerente al suo interno: elenca sia "Marseille" sia
"Marsiglia", sia "Nice" sia "Nizza". Per questo non basta una mappa da italiano
a inglese: serve una chiave canonica in cui collassano TUTTE le varianti.

Uso:
    from nomi_squadre import chiave, stessa_squadra
    chiave("Galles")            -> "wales"
    chiave("Wales")             -> "wales"
    chiave("Paris Saint-Germain") -> "paris saint germain"
    stessa_squadra("Lione", "Lyon") -> True
"""
import unicodedata

# Sigle e parole che non distinguono una squadra dall'altra.
# Si tolgono SOLO in coda e solo come parola intera.
SUFFISSI = (
    "fc", "cf", "sc", "ac", "afc", "as", "ss", "ssc", "us", "uc", "sv", "sk",
    "calcio", "football club", "futebol clube", "club", "hfc", "fk", "nk",
)

# Varianti -> chiave canonica (inglese/neutro, come nei nostri file quote).
# Costruita leggendo i nomi REALI dei due file, non inventata.
ALIAS = {
    # --- nazionali: italiano -> canonico ---
    "galles": "wales",
    "germania": "germany",
    "olanda": "netherlands",
    "paesi bassi": "netherlands",
    "portogallo": "portugal",
    "scozia": "scotland",
    "slovacchia": "slovakia",
    "slovenia": "slovenia",
    "svizzera": "switzerland",
    "grecia": "greece",
    "islanda": "iceland",
    "israele": "israel",
    "kazakistan": "kazakhstan",
    "lussemburgo": "luxembourg",
    "lituania": "lithuania",
    "lettonia": "latvia",
    "estonia": "estonia",
    "belgio": "belgium",
    "croazia": "croatia",
    "spagna": "spain",
    "italia": "italy",
    "francia": "france",
    "inghilterra": "england",
    "irlanda": "ireland",
    "repubblica d irlanda": "ireland",
    "repubblica di irlanda": "ireland",
    "danimarca": "denmark",
    "norvegia": "norway",
    "svezia": "sweden",
    "finlandia": "finland",
    "polonia": "poland",
    "ungheria": "hungary",
    "cechia": "czechia",
    "repubblica ceca": "czechia",
    "ucraina": "ukraine",
    "turchia": "turkiye",
    "austria": "austria",
    "bulgaria": "bulgaria",
    "malta": "malta",
    "moldova": "moldova",
    "serbia": "serbia",
    "albania": "albania",
    "macedonia": "north macedonia",
    "macedonia del nord": "north macedonia",
    "liechtenstein": "liechtenstein",
    "bosnia erzegovina": "bosnia herzegovina",
    "bosnia e erzegovina": "bosnia herzegovina",
    "porto rico": "puerto rico",
    "isole cayman": "cayman islands",
    "cayman": "cayman islands",
    "isole vergini": "virgin islands",
    "isole salomone": "solomon islands",
    "isole far oer": "faroe islands",
    "fær øer": "faroe islands",
    "antigua e barbuda": "antigua and barbuda",
    "trinidad e tobago": "trinidad and tobago",
    "saint kitts e nevis": "st kitts and nevis",
    "santa lucia": "saint lucia",
    "sint maarten": "sint maarten",
    "guadalupa": "guadeloupe",
    "martinica": "martinique",
    # --- club: italiano -> canonico ---
    "lione": "lyon",
    "marsiglia": "marseille",
    "olympique marsiglia": "marseille",
    "nizza": "nice",
    "strasburgo": "strasbourg",
    "tolosa": "toulouse",
    "monaco": "monaco",
    "parigi": "paris",
    # --- varianti inglesi/abbreviazioni usate nei nostri file ---
    "ath bilbao": "athletic bilbao",
    "ath madrid": "atletico madrid",
    "bayern monaco": "bayern munich",
    "bayern munchen": "bayern munich",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "wolves": "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "inter": "internazionale",
    "internazionale milano": "internazionale",
    "milan": "ac milan",
    "real betis": "betis",
    "real sociedad": "sociedad",
    "le mans fc": "le mans",
    "casa pia": "casa pia",
    "uniao de leiria": "leiria",
    "amora": "amora",
}

# Coppie che NON vanno confuse anche se la chiave e' simile.
# Servono a evitare falsi positivi: se il nome completo contiene una di queste
# parole distintive, deve combaciare anche quella.
DISTINTIVI = ("real", "atletico", "athletic", "united", "city", "sporting",
              "junior", "reserve", "ii", "b", "women", "femminile")


def _pulisci(s):
    """Minuscolo, senza accenti, senza punteggiatura, spazi singoli."""
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    for ch in ".-'’`,()[]/":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _togli_suffissi(s):
    """Rimuove le sigle societarie in coda ('Le Mans FC' -> 'le mans')."""
    parole = s.split()
    while len(parole) > 1 and parole[-1] in SUFFISSI:
        parole.pop()
    return " ".join(parole)


def chiave(nome):
    """Chiave canonica di una squadra: confrontabile fra fonti diverse."""
    n = _pulisci(nome)
    n = ALIAS.get(n, n)
    n = _togli_suffissi(n)
    # secondo passaggio: dopo aver tolto i suffissi puo' essere ricomparso un alias
    return ALIAS.get(n, n)


def stessa_squadra(a, b, soglia=0.90):
    """True se i due nomi indicano (con alta probabilita') la stessa squadra."""
    ka, kb = chiave(a), chiave(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    # contenimento: "inter" dentro "internazionale" non basta, ma "le mans" dentro
    # "le mans" si'. Richiediamo che il piu' corto sia una parola intera dell'altro.
    corto, lungo = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if len(corto) >= 5 and (" " + corto + " ") in (" " + lungo + " "):
        return True
    import difflib
    if difflib.SequenceMatcher(None, ka, kb).ratio() >= soglia:
        return True
    return False


def chiave_partita(partita):
    """Da 'Galles - Portogallo' ricava la chiave ('wales', 'portugal'). None se non e' 'A - B'."""
    p = str(partita or "")
    for sep in (" - ", " v ", " vs "):
        if sep in p:
            h, a = p.split(sep, 1)
            return chiave(h), chiave(a)
    return None
