# 🚀 Come mettere il sito online (gratis)
Il sito è statico (solo HTML/CSS inline) → hosting gratis:

## Opzione A — Netlify Drop (la più facile, no account)
1. Vai su https://app.netlify.com/drop
2. Trascina dentro la cartella `sito/` (o lo zip sito-html.zip scompattato)
3. Ti dà subito un URL pubblico tipo https://nome-123.netlify.app

## Opzione B — GitHub Pages (con account GitHub)
1. Nuovo repo pubblico, carica i file di `sito/`
2. Settings → Pages → Deploy from branch → URL tipo https://tuouser.github.io/repo

## Opzione C — Cloudflare Pages (gratis, CDN globale)
1. Pages → Create project → upload della cartella `sito/`

## ⚠️ Da mantenere prima di pubblicare (già presenti nel sito)
- Disclaimer 18+ / ADM / autoesclusione.it / 800 558822 in ogni pagina ✔
- Contenuto analysis-only, mai pronostici "sicuri", mai link per puntare su book non-ADM ✔
- La pagina surebets resta con warning 🚩 e link solo ad aggregatori (wincomparator), non a book di gioco ✔
- Aggiornamenti: basta ricaricare i file (o collegare il repo GitHub per auto-deploy ad ogni push)

## Aggiornamenti automatici
Il server locale 8002 rigenera le pagine quando cambiano i dati; per pubblicare: copia le nouvelles `sito/*.html` sull'hosting (o push su GitHub).
