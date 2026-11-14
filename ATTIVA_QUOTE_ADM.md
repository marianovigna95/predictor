# 🇮🇹 Attivare le quote ADM reali (5 minuti, gratis)

## Perché
Oggi la quota che pubblichiamo viene da un comparatore che copre book **non-ADM**: sono prezzi che in Italia
non puoi giocare. Con questo passo il sito affianca, sotto la quota best-price, la **migliore quota ADM**
reale (47 operatori con licenza) — così sai subito se il valore che vedi esiste davvero dove puoi giocare.

Lo script è **innocuo senza chiave**: esce con `stato: "senza_chiave"` e il sito funziona identico a prima.

---

## Passo 1 — Chiave (gratis, senza carta)
1. Apri **odss-api.com**
2. Piano **Free**: 500 richieste/mese, stessa copertura dei piani a pagamento, **senza carta**
3. Registrati (email + password) → dal pannello copia la chiave `odss_live_...`
4. ⚠️ Non incollarla in chat e non metterla nel codice: solo come secret

## Passo 2 — Secret su GitHub
1. `github.com/marianovigna95/predictor/settings/secrets/actions`
2. **New repository secret**
3. Name: `ODSS_API_KEY` · Secret: `odss_live_...` → **Add secret**

## Passo 3 — Run
Actions → daily-predictor → **Run workflow** (~20 min).

## Passo 4 — Verifica
- `data/quote_adm_meta.json` → `"stato": "ok"`
- `data/quote_adm.csv` → righe con `book` = operatori ADM
- nel sito, sotto "Quota best": **🇮🇹 miglior quota ADM 2.xx su N book**

---

## Budget richieste (3 per run: il punto di equilibrio)

| Tetto per run | Mese (4 run × 30 gg) | Resta su 500 | Leghe coperte |
|---|---|---|---|
| 2 | 240 | 260 | 1 |
| **3** ✅ | **360** | **140** | **1 lega intera (2 richieste) + 1 mercato della successiva** |
| 4 | 480 | 20 | 2 — troppo vicino al limite |
| 6 | 720 | **−220** | fuori dal free tier |

**Scelto 3** perché:
- copre **una lega completa** (1X2 + Over/Under = 2 richieste) **più un mercato** della lega successiva
- lascia **~140 richieste di margine** al mese: bastano per qualche run manuale extra
- con 4 si arriverebbe a 480/500: un mese da 31 giorni più un paio di run a mano e si sfora
- 6 era fuori scala

**Doppia sicurezza:** oltre al tetto per run c'è un **contatore mensile** in `data/quote_adm_usage.json`:
a 480 richieste lo script si **ferma da solo** (`stato: "budget_esaurito"`) e riprende il mese dopo
(il contatore si azzera da solo al cambio di mese — testato).

## Quali leghe interroga
Prima le leghe **dove abbiamo giocate attive** (è lì che serve la quota ADM), poi il resto della finestra.
Così le 2 richieste per run non si sprecano su campionati senza valore.

## Se un giorno la fonte smette di rispondere
`stato: "errore"`, il file vecchio resta, il sito mostra solo la quota best-price. Nessuna dipendenza critica.
