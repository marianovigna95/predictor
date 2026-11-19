#!/usr/bin/env python3
"""step30_meta.py — 🆕 13/11-b SEO/social: inietta meta description + OpenGraph in OGNI pagina di site/
che non le ha (index, diretta, ppa, schedina, bankroll, verifica, squadra, glossario, metodo, surebets, report...).
Idempotente: se una pagina ha già `name="description"`, non la tocca.
Uso: python3 src/step30_meta.py   (da eseguire DOPO tutti i generatori di pagine)
"""
import glob
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
BASE = "https://marianovigna95.github.io/predictor/"


def _clean(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    return t


def build_desc(s):
    m = re.search(r"<title>(.*?)</title>", s, re.S)
    title = _clean(m.group(1)) if m else "Predictor"
    title = title.replace(" — Serie A Predictor", "").strip()
    body = s
    for pat in (r'<p class="sub"[^>]*>(.*?)</p>', r"<h1[^>]*>(.*?)</h1>", r'<p[^>]*>(.*?)</p>'):
        mm = re.search(pat, body, re.S)
        if mm and len(_clean(mm.group(1))) > 40:
            body = _clean(mm.group(1))
            break
    else:
        body = "Analisi statistiche calcio 2026/27: pronostici con probabilità, quote, EV e archivio pubblico verificabile."
    tl = title.lower().replace("predictor", "").strip(" —-·")
    if not tl or tl in body.lower()[:40]:
        desc = body
    else:
        desc = title + ": " + body
    desc = desc[:155].rstrip(" ,.;") + ("…" if len(desc) > 155 else "")
    return title, desc


# 🆕 19/11 TABBAR UNIVERSALE — riparazione automatica della navigazione.
#    Misurato il 19/11 sulle 24 pagine pubblicate: 6 non avevano la tabbar in basso
#    (bankroll, schedina, squadra, verifica, apri-sito, report_giornataNN) → da quelle
#    pagine non si poteva tornare al sito se non col tasto indietro del browser.
#    Invece di rattoppare i singoli generatori (fragile: la prossima pagina nuova
#    avrebbe lo stesso difetto), si interviene QUI, che gira su TUTTE le pagine
#    come ultimo passo della pipeline. Idempotente: chi ha già una tabbar non viene
#    toccato.
_TAB_LINKS = [
    ("index.html", "⌂", "HOME"),
    ("pronostici.html", "🎯", "PRONOSTICI"),
    ("giocata_multi.html", "💎", "GIOCATE"),
    ("ppa.html", "⚡", "PPA"),
    ("archivio.html", "🗂", "ARCHIVIO"),
]
_TAB_CSS = ("<style>.tabbar{position:fixed;bottom:0;left:0;right:0;z-index:50;background:#0b0f14;"
            "border-top:1px solid #242c37;display:flex;overflow-x:auto}"
            ".tabbar a{flex:1;text-align:center;padding:10px 4px;color:#8b96a5;font-size:12px;"
            "font-weight:600;border-right:1px solid #242c37;text-decoration:none}"
            ".tabbar a:last-child{border-right:none}"
            "html[data-theme=light] .tabbar{background:#f4f6f9;border-top-color:#d8dee6}"
            "html[data-theme=light] .tabbar a{color:#5c6878;border-right-color:#d8dee6}"
            "body{padding-bottom:96px!important}</style>")


def ensure_tabbar(path):
    """Aggiunge la tabbar alla pagina se manca. Ritorna True se ha modificato il file."""
    try:
        s = open(path, encoding="utf-8").read()
    except Exception:
        return False
    if 'class="tabbar"' in s:
        return False
    if "</body>" not in s:
        return False
    cur = os.path.basename(path)
    links = "".join(
        f'<a href="{h}"{" class=\"on\"" if h == cur else ""}><span>{ic}</span>{lb}</a>'
        for h, ic, lb in _TAB_LINKS)
    bar = f'<div class="tabbar">{links}</div>'
    s = s.replace("</head>", _TAB_CSS + "</head>", 1) if "</head>" in s else s
    s = s.replace("</body>", bar + "</body>", 1)
    try:
        open(path, "w", encoding="utf-8").write(s)
        return True
    except Exception:
        return False


def main():
    n = 0
    for p in sorted(glob.glob(os.path.join(SITE, "*.html"))):
        s = open(p, encoding="utf-8", errors="ignore").read()
        if 'name="description"' in s:
            continue
        title, desc = build_desc(s)
        de = html.escape(desc, quote=True)
        te = html.escape(f"{title} — Serie A Predictor", quote=True)
        block = (f'<meta name="description" content="{de}">\n'
                 f'<meta property="og:title" content="{te}">\n'
                 f'<meta property="og:description" content="{de}">\n'
                 f'<meta property="og:type" content="website">\n'
                 f'<meta property="og:image" content="{BASE}icon-512.png">\n'
                 f'<meta name="twitter:card" content="summary">')
        if re.search(r"</title>", s):
            s = re.sub(r"(</title>)", r"\1\n" + block.replace("\\", "\\\\"), s, count=1)
        elif "<head>" in s:
            s = s.replace("<head>", "<head>\n" + block, 1)
        else:
            continue
        open(p, "w", encoding="utf-8").write(s)
        n += 1
        print(f"  ✅ {os.path.basename(p)}: {desc[:70]}…")
    print(f"🔎 meta aggiunte a {n} pagine")
    # 🆕 19/11 tabbar su ogni pagina che ne è priva (vedi ensure_tabbar)
    #    ⚠️ Si guardano DUE cartelle: site/ (pagine di make_site) e ROOT (pagine scritte
    #    direttamente lì da step19_diretta, step25_verifica_mensile, step27_schedina,
    #    step28_bankroll, step29_squadra). Il primo tentativo guardava solo site/ e
    #    4 pagine su 22 restavano senza navigazione: misurato, non supposto.
    nav = 0
    for p in sorted(set(glob.glob(os.path.join(SITE, "*.html")) +
                        glob.glob(os.path.join(ROOT, "*.html")))):
        if ensure_tabbar(p):
            nav += 1
            print(f"  🧭 tabbar aggiunta: {os.path.basename(p)}")
    if nav:
        print(f"🧭 navigazione riparata su {nav} pagine")
    else:
        print("🧭 navigazione: tutte le pagine hanno già la tabbar")




# 🆕 13/11-b ANONIMIZZATORE FONTI: sui NODI DI TESTO (mai dentro tag/URL, così i loghi esterni
# continuano a caricare) i nomi delle fonti specifiche diventano descrizioni generiche.
_SRC_MAP = [
    (r"\bESPN ?API\b", "API pubblica"), (r"\bESPN\b", "fonte live pubblica"),
    (r"\bFotMob\b", "fonte pubblica"), (r"\bfootball-data(?:\.co\.uk)?\b", "fonte pubblica"),
    (r"\bwincomparator(?:\.com)?\b", "aggregatore di quote"), (r"\bCentroQuote\b", "fonte di comparazione"),
    (r"\bUnderstat\b", "fonte pubblica"), (r"\bOddsportal\b", "fonte pubblica"),
    (r"\bBet365\b|\bbet365\b", "un book"), (r"\bPinnacle\b", "un book professionale"),
    (r"\bFantacalcio[- ]online\b", "fonte pubblica"), (r"\bKaggle\b", "fonte pubblica"),
    (r"\bNominatim\b|\bOSM\b", "servizio pubblico di geocoding"),
    (r"\bfantacalcio(?:\.it)?\b", "fonte pubblica"), (r"\bkaggle\b", "fonte pubblica"),
    (r"\bunderstat\.com\b|\bfotmob\.com\b|\boddsportal\.com\b|\bwincomparator\.com\b", "fonte pubblica"),
]


def anonymize_sources(path):
    s = open(path, encoding="utf-8", errors="ignore").read()
    parts = re.split(r"(<[^>]*>)", s)
    changed = 0
    for i, chunk in enumerate(parts):
        if chunk.startswith("<"):
            continue
        new = chunk
        for pat, rep in _SRC_MAP:
            new2 = re.sub(pat, rep, new, flags=re.I)
            if new2 != new:
                changed += 1
                new = new2
        parts[i] = new
    if changed:
        open(path, "w", encoding="utf-8").write("".join(parts))
    return changed


def main_sources():
    tot = 0
    for p in sorted(glob.glob(os.path.join(SITE, "*.html"))):
        n = anonymize_sources(p)
        if n:
            tot += n
            print(f"  🧼 {os.path.basename(p)}: {n} nomi fonti → generico")
    print(f"🧼 fonti anonimizzate in {tot} punti")


if __name__ == "__main__":
    main()
    main_sources()
    # 📄 copia in ROOT: GitHub Pages serve la root, non site/. Senza questa copia il fix
    #    resterebbe invisibile online (era esattamente il bug del run #25).
    import shutil as _sh
    copiati = 0
    for _p in glob.glob(os.path.join(SITE, "*.html")):
        try:
            _sh.copy2(_p, os.path.join(ROOT, os.path.basename(_p)))
            copiati += 1
        except Exception as _e:
            print("  ⚠️ copia fallita:", _p, _e)
    print(f"📄 copiate {copiati} pagine da site/ alla root (GitHub Pages)")
