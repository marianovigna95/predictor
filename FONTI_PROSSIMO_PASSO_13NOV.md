# 🔭 Fonti dati dei siti monitorati → cosa possiamo usare noi
### Analisi del 13/11/2026 — cosa serve davvero per il "passo di qualità" successivo

> Regola di partenza: **nessuna API a pagamento** (vincolo tuo), quindi ogni candidato è valutato
> *prima* per ciò che dà **gratis**, poi per ciò che darebbe **pagando**, con il costo di attivazione stimato.

---

## 1. Cosa usano i siti che teniamo segnati (scansione tecnica degli HTML)

Ho scaricato l'HTML delle home e cercato i provider noti (SofaScore, Flashscore, FotMob, Understat,
api-sports, The Odds API, Pinnacle…), più endpoint `/api/`.

| Sito | Provider/fonte rilevata | Lezione per noi |
|---|---|---|
| **gambeta.ai** | `the-odds-api`, Flashscore, bet365, betfair, espn | usa un'**API quote a pagamento** (500 crediti free) per il best-price multi-book |
| **footballaiapp.com** | `api-sports` (API-Football) | statistiche + quote da **un solo aggregatore**, piano free 100 req/giorno |
| **scoregpt.app** | `api-sports` + livescore | idem, con livescore per il live |
| **futbol24.com** | `api.futbol24.com` interno + livescore | feed proprietario; nulla di riusabile per noi |
| **bettingexchange.net** | betfair, **pinnacle** | la fonte "sharp" per eccellenza (exchange + book professionale) |
| **blablive, livetipsportal, 1x2.tv, stats4bets, aipredict, tipsgenerator, pronext, xscores, mondopengwin, presidentegoal, grownow, scoore.ai, aiscore** | nessun provider rilevabile | **non hanno dati loro**: vendono pick, non modelli → niente da imparare se non cosa *non* fare |
| **one-versus-one.com** | bloccato (0 byte) | non accessibile |

**Conclusione:** i concorrenti "veri" (gambeta, footballaiapp, scoregpt) **non hanno dati migliori dei nostri**: comprano gli stessi feed quote da un aggregatore. Noi oggi prendiamo il best-price gratis da un comparatore (e le chiusure dai CSV gratuiti). **Il divario non è nelle statistiche: è nel prezzo.**

---

## 2. Cosa ho testato dal nostro ambiente (risultati reali, non promesse)

| Fonte | Stato dal nostro sandbox | Verdetto |
|---|---|---|
| `football-data.co.uk` (CSV stagionali) | ✅ 200, **contiene già `HxG`/`AxG`** | già in uso ✅ |
| `api.clubelo.com` (Elo club) | ❌ non risponde | scartata |
| `understat.com` | ⚠️ 200 ma **nessun JSON dati** (pagina di errore/JS) | scartata |
| `fbref.com` | ❌ 403 | scartata (già noto) |
| `transfermarkt` | ❌ 202 (challenge) | scartata |
| `sofascore api` | ❌ 403 | scartata |
| `api.football-data.org` v4 | ✅ 200 ma **49 richieste residue** senza chiave | solo per test manuali |
| `api-football (api-sports)` | ❌ 403 senza chiave | richiede registrazione (free 100/giorno) |
| `openfootball/football.json` (GitHub) | ✅ 200 | calendario di riserva, non serve |
| `open-meteo` | ✅ 200 | già in uso ✅ |
| **`odss-api.com`** | ✅ **funziona senza chiave** su `/coverage`, `/leagues`, `/status`; `/odds` richiede chiave free | **la scoperta interessante** (sotto) |

---

## 3. Le tre strade possibili, in ordine di valore reale

### 🥇 A. API con i **bookmaker ADM italiani** (`odss-api.com`) — l'unica che cambia il gioco
**Cosa dà:** quote normalizzate di **oltre 40 operatori con licenza ADM** (+ book esteri di riferimento ed exchange), in un JSON unico, con `last_update` per book, `suspended` per gli esiti sospesi, `event_id` stabile, quote **live** incluse.
**Free tier:** **500 richieste/mese**, *stessa copertura dei piani a pagamento*, senza carta. C'è una sandbox senza chiave.
**Verificato ora:** `GET /api/v1/coverage` → `{"italy":45,"total":213}`; `GET /api/v1/leagues` → 45 leghe, 8.226 eventi; `/status` → feed operativo, scansione ogni 45 s, live attivo.
**Perché è il passo di qualità più grande disponibile:**
1. Oggi il nostro "best price" viene da un comparatore che copre **bet365/betway/betsson/unibet** — cioè **book non-ADM che tu non puoi giocare**. Con questa fonte la quota pubblicata sarebbe **quella reale del book ADM** dove la puoi davvero mettere.
2. Con 40+ book ADM possiamo calcolare il **vero best-price ADM** e, soprattutto, la **quota di chiusura ADM** → **CLV vero** (oggi misuriamo il CLV sulla media dei book, che è un proxy).
3. Possiamo finalmente misurare **quanto "costa" giocare solo su ADM** rispetto al mercato internazionale: è l'unica domanda a cui oggi non sappiamo rispondere e che determina se il nostro EV è reale o illusorio.
**Costi / rischi:** serve una registrazione (email, senza carta) per la chiave; 500 req/mese = ~16/giorno → sufficienti per **1 snapshot al giorno** delle partite della finestra (non per polling live). È un servizio piccolo/nuovo: da trattare come sperimentale, con fallback sui dati attuali se un giorno smette di rispondere.
**Sforzo:** 1 script nuovo (`step31_quote_adm.py`) + confronto in `giocata_multi.csv` di una colonna `quota_adm_best`. Mezza giornata.

### 🥈 B. Best-price ADM "manuale" (zero dipendenze, zero chiavi)
**Cosa dà:** prendo io (o tu, con uno screenshot) le quote di 2–3 book ADM sulle 6–10 partite della finestra; le registriamo in un CSV e il modello confronta la quota ADM reale con la sua probabilità.
**Costo:** 5 minuti al giorno, nessuna API.
**Valore:** misura **subito** se l'edge sopravvive sui prezzi ADM — la stessa domanda della strada A, senza dipendenze. **È il test che consiglio di fare in parallelo**, perché se l'edge non sopravvive su ADM è inutile continuare a raffinare il modello.

### 🥉 C. API-Football / The Odds API (piano free)
**Cosa danno:** statistiche + quote in un unico feed, 100 req/giorno (api-sports) o 500 crediti/mese (the-odds-api, che però **non copre i book ADM**).
**Perché è la terza scelta:** risolvono un problema che **non abbiamo** (abbiamo già statistiche e quote) e non toccano il problema che **abbiamo** (il prezzo ADM).

---

## 4. Cosa NON serve (e perché lo dico chiaramente)

- **Più xG / più leghe / più mercati**: l'xG c'è già (`HxG`/`AxG` in ogni CSV), e l'esperimento interno dice che l'xG **batte i gol reali** (RPS 0.0833 vs 0.0865) — quindi il dato è già sfruttato.
- **Pinnacle / linea sharp a pagamento**: test appena fatto (`src/step29_bench_pinnacle.py`, 2.076 partite 2025/26+2026/27): Pinnacle close RPS **0.2001** vs media book **0.2002**, Δ **0.0001** sulle nostre leghe. **Nessun guadagno**: non vale un euro.
- **Feed live a pagamento**: la nostra pagina Diretta già usa dati live gratuiti con xG.

---

## 5. Il vero "passo di qualità" (la scoperta dell'audit)

Mettendo insieme i numeri:

- Sul test walk-forward puro il **mercato è avanti di 2,6 millesimi** di RPS.
- Le nostre giocate pubblicate avevano scarti modello-mercato **enormi**: +18,6 / +23,2 / +24,3 punti percentuali. Un modello che si crede più sicuro del mercato di 24 punti **non ha valore: ha un errore**.
- Filtro subito introdotto: **nessuna giocata se lo scarto supera i 10 punti** → le giocate di oggi sono passate da 3 con scarto 18–24pp a **4 con scarto 2,9–9,7pp**, probabilità 57–72% (credibili), 2 delle quali con stake attivo.

**Quindi il passo di qualità non è una fonte nuova: è (a) il filtro di calibrazione, (b) il prezzo ADM reale.** Con quelli il progetto diventa *verificabile*, non solo elegante.

---

## 6. Cosa proporrei di fare, in ordine

| # | Azione | Costo | Effetto |
|---|---|---|---|
| 1 | **Attivare la chiave free di `odss-api`** e fare 1 snapshot/giorno delle quote ADM della finestra | 10 min + 500 req/mese free | quota pubblicata = quota **giocabile**, CLV vero |
| 2 | **Test manuale ADM** su 2 sere (10 partite) | 10 min | dice se l'edge sopravvive ai prezzi ADM |
| 3 | Tenere il **filtro 10pp** e misurarlo sul campo per 2 settimane | già fatto | capire se le giocate "credibili" rendono |
| 4 | Solo dopo: eventuale piano a pagamento | — | se e solo se 1–3 mostrano edge |

---

## 7. Nota di trasparenza
`odss-api.com` è un servizio **piccolo e recente**: non posso garantire che duri. Per questo ogni script lo tratterà come **opzionale con fallback** (se non risponde, il sito continua con le quote attuali). Non è un'affiliazione, non ci pagano, e i book non-ADM restano 🚩 come da regola: la fonte serve solo a leggere **prezzi**, non a linkare operatori.
