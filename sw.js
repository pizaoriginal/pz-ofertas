/* PZ Ofertas — service worker
   Responsável por deixar o app abrir mesmo sem internet.

   Estratégia:
   - Arquivos fixos do site (index, ícones): serve do cache primeiro, rápido.
   - products.json: tenta buscar da rede primeiro (pra pegar achados novos),
     e só usa o cache se estiver offline. Assim o catálogo nunca fica velho
     quando há internet.

   Ao mudar o site, suba o número da versão abaixo para forçar a atualização
   nos celulares que já instalaram o app.
*/

const VERSAO = "pz-ofertas-v1";

const ARQUIVOS_FIXOS = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/icons/icon-maskable-512.png",
];

// Instalação: guarda os arquivos fixos no cache
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSAO).then((cache) => cache.addAll(ARQUIVOS_FIXOS))
  );
  self.skipWaiting();
});

// Ativação: apaga caches de versões antigas
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(
        chaves.filter((c) => c !== VERSAO).map((c) => caches.delete(c))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // só lida com navegação e arquivos do próprio site
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // catálogo: rede primeiro, cache como reserva
  if (url.pathname.endsWith("products.json")) {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(VERSAO).then((cache) => cache.put(req, copia));
          return resp;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // resto: cache primeiro, rede como reserva
  event.respondWith(
    caches.match(req).then((cacheado) => {
      if (cacheado) return cacheado;
      return fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(VERSAO).then((cache) => cache.put(req, copia));
          return resp;
        })
        .catch(() => {
          // se for uma navegação e estiver offline, devolve a home
          if (req.mode === "navigate") return caches.match("/index.html");
        });
    })
  );
});
