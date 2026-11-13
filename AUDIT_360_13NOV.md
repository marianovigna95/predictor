# 🔍 AUDIT 360° del sito — 13/11/2026 (sera)

Controllo completo di codice, dati, pagine e coerenza con le regole del progetto.
**Esito: 9 problemi trovati, 9 corretti.** Sotto, in ordine di gravità.

---

## 🔴 Critici (toccavano soldi o numeri pubblici)

### 1. `se` = incertezza di p era in realtà il *Brier score* → stake sballati
**Dove:** `src/weekly_multi.py` (classe `Calib`, funzione `kelly_stake`).
**Cosa:** il margine di incertezza passato a ¼ Kelly valeva **0,44** (44 punti percentuali!) perché era il Brier del modello, non l'errore standard di p. Risultato: `p − se` finiva sotto la soglia e **tutti gli stake venivano azzerati** (5 righe su 8 a 0,00%).
**Fix:** `Calib.se_for(p)` = errore standard binomiale con `n_eff` = coda di calibrazione (clamp 30…250), marginato in 2–10 pp; `kelly_stake` ora scarta NaN e applica un tetto di sicurezza al 5% del bankroll per voce.
**Prima → dopo:** riga 13/11 SINGOLA (U2.5, p 60,3%, quota 2,40): stake **0,00% → 1,32%**.

### 2. Regola dichiarata "stake solo se EV > +2%" non applicata nel codice
**Dove:** `kelly_stake`, `step27_schedina.py`.
**Cosa:** lo stake partiva con qualsiasi EV > 0; il sito però dichiarava ovunque "stake pieno solo se EV > +2%". Incoerenza tra ciò che promettiamo e ciò che calcoliamo.
**Fix:** soglia esplicita in `kelly_stake(..., ev=...)` e nel fallback della schedina. **Verifica: 0 violazioni su 7 giocate.**

### 3. Stake azzerati da `NaN` nelle feature O/U e GG
**Dove:** `weekly_multi.py` (stacker binari).
**Cosa:** quando la quota mercato di O2.5/GG era vuota o NaN, il valore entrava come NaN nello stacker → `p_over`/`p_btts` NaN → stake 0 (4 casi su 8).
**Fix:** fallback esplicito al modello DC quando la quota manca (`_num()` + controllo `isfinite`).

### 4. Pulsante "Esporta archivio CSV" rotto (JS invalido)
**Dove:** `make_site.py` → `archivio.html`.
**Cosa:** `'\n'` dentro l'f-string diventava un **a capo reale** nel JavaScript → `SyntaxError`: il pulsante non esportava nulla (e il CSV sarebbe uscito tutto su una riga).
**Fix:** `String.fromCharCode(10)`. **`node --check` ora passa su tutte le pagine (0 errori).**

---

## 🟠 Onestà dei numeri pubblicati

### 5. Claim "RPS 0.1918 meglio del mercato 0.1963" fuorviante
**Cosa ho verificato:** il 0.1918 è una stima **leave-one-group-out** (a parità di addestramento). Sul test **walk-forward puro** `validation_multi.csv` (535 match g6-g38, pesato per partite) dà:

| | RPS |
|---|---|
| Modello | **0.1989** |
| Mercato | **0.1963** |
| Esito | mercato avanti di **2,6 millesimi** |

Vinciamo solo in **4 leghe su 13**: Primeira Liga (+11,9), Championship (+5,5), Bundesliga (+3,5), Eredivisie (+3,0). Perdiamo in 9, con LaLiga (−16,8) e Ligue 1 (−12,5) peggiori.
**Fix:** `benchmark.html`, `metodo.html` e la card versioni ora dicono **entrambi** i numeri, con un riquadro "📉 esito reale del confronto" in evidenza. Nessun claim residuo del tipo "meglio del mercato".

### 6. 21 pagine senza `meta description` (condivisione vuota)
**Fix:** helper in `make_site.py` + nuovo `src/step30_meta.py` (idempotente) che inietta description + OpenGraph su **tutte** le pagine (0 pagine scoperte).

### 7. Nomi di fonti dati ancora visibili nelle pagine pubbliche
In contraddizione con la regola del 13/11. Trovati in **10 pagine** (wincomparator, FotMob, ESPN, football-data, Understat, Pinnacle, Kaggle, Centrocampo/centroquote, Bet365).
**Fix:** testi riscritti nei generatori + **anonimizzatore** in `step30_meta.py` che agisce solo sui **nodi di testo** (mai dentro tag/URL, così i loghi esterni continuano a caricarsi). **Residui nel testo visibile: 0.** La pagina `fonti.html` (interna) è stata riscritta in forma generica.

---

## 🟡 Rifiniture

### 8. Accessibilità: 4 loghi squadra senza `alt` in Diretta → aggiunto `alt=""` (decorativi).
### 9. Pagine orfane: `report_giornata10.html` non è linkata da nessuna pagina (resta in archivio, non è un errore bloccante).

---

## ✅ Cosa era già a posto (verificato, non toccato)
- Link interni e asset: **0 rotti** su 21 pagine.
- Footer 18+ / ADM / autoesclusione.it / 800 558822: presente su **tutte** le pagine.
- Quote pubblicate: min 1,13 / max 17,50, nessun valore impossibile, `p1+pX+p2 = 100,0`.
- Tutti i 50 script `.py` compilano (`py_compile`), `daily.yml` copre i gate g6-g38.
- Pesi ensemble 0.50 / 0.30 / 0.20 e stacker: coerenti tra `metodo.html` e codice.
- PWA: `sw.js` in network-first per le pagine (nessun problema di cache stantia), manifest con 4 shortcut.

---

## 📌 Da fare quando vuoi (non urgenti)
1. **`CLV` sotto i 30 campioni:** mostrare "n troppo basso" invece del numero.
2. **Pagine archivio giornata 10:** valutarne la rimozione dal repo o il link dall'archivio.
3. **`fpdf2`:** il PDF della schedina viene saltato (fallback `Ctrl+P`), come da vincolo noto.
