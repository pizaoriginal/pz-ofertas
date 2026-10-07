/* PZ Ofertas — service worker (v4)
   Deixa o app abrir mesmo sem internet, SEM prender o site numa versão velha.

   Estratégia:
   - Páginas (HTML) e arquivos .json (catálogo): REDE primeiro. Se tiver
     internet, sempre pega a versão nova; o cache só entra se estiver offline.
   - Imagens, CSS, JS e o resto do próprio site: usa o cache pra abrir rápido,
     mas confere a versão nova em segundo plano e atualiza pra próxima visita.
   - Só guarda no cache respostas que deram certo (status 200). Respostas de
     erro (tipo 404) nunca são guardadas.
   - A instalação não quebra se algum arquivo da lista não existir no site.

   Você só precisa mexer na VERSAO se mudar a lista ARQUIVOS_FIXOS.
*/

const VERSAO = "pz-ofertas-v4";

// guardados já na primeira visita, pra funcionar offline (inclui o joguinho)
const ARQUIVOS_FIXOS = [
  "/",
  "/index.html",
  "/game.html",
  "/404.html",
  "/manifest.json",
];

// Instalação: guarda os arquivos fixos, um por um. Se algum não existir,
// os outros continuam sendo guardados e a instalação segue normalmente.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSAO).then((cache) =>
      Promise.allSettled(ARQUIVOS_FIXOS.map((url) => cache.add(url)))
    )
  );
  self.skipWaiting();
});

// Ativação: apaga os caches de versões antigas (inclusive qualquer cópia
// velha ou com erro que tenha ficado guardada antes)
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

  // só lida com pedidos de leitura aos arquivos do próprio site
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  const ehPagina =
    req.mode === "navigate" ||
    (req.headers.get("accept") || "").includes("text/html");
  const ehDados = url.pathname.endsWith(".json");

  if (ehPagina || ehDados) {
    event.respondWith(redePrimeiro(req));
    return;
  }

  event.respondWith(cacheERevalida(event));
});

// HTML e JSON: tenta a rede; só cai pro cache se estiver sem internet
async function redePrimeiro(req) {
  try {
    const resp = await fetch(req);
    if (resp && resp.ok) {
      const cache = await caches.open(VERSAO);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch (erro) {
    const cacheado = await caches.match(req);
    if (cacheado) return cacheado;

    // offline numa página que nunca foi guardada: abre a home
    if (req.mode === "navigate") {
      const home =
        (await caches.match("/")) || (await caches.match("/index.html"));
      if (home) return home;
    }
    throw erro;
  }
}

// Imagens e afins: responde na hora com o que tem e atualiza em segundo plano
function cacheERevalida(event) {
  const req = event.request;

  return caches.open(VERSAO).then((cache) =>
    cache.match(req).then((cacheado) => {
      const buscar = fetch(req).then((resp) => {
        if (resp && resp.ok) cache.put(req, resp.clone());
        return resp;
      });

      if (cacheado) {
        event.waitUntil(buscar.catch(() => {}));
        return cacheado;
      }
      return buscar;
    })
  );
}
