// sw.js — service worker minimale.
// Due scopi soltanto: (1) la pagina non genera errori in console quando registra
// il worker, (2) una pagina gia' visitata si riapre anche senza rete.
// NON mette in cache dati, CSV o API: i pronostici devono essere sempre freschi.
const CACHE = "predictor-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  // solo navigazioni GET: nessun dato, nessuna API, nessun file in data/
  if (req.method !== "GET" || req.mode !== "navigate") return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copia = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
