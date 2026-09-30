/* =============================================================
   SERVICE WORKER — só o casco do painel.

   Regra de ouro: **nenhuma resposta de dados entra em cache.**
   Lista de pessoas atendidas é dado de saúde por associação; ela
   não pode ficar no disco do navegador, nem por engano.

   Como isso é garantido aqui: a lista do que pode ser guardado é
   uma ALLOWLIST (o casco e os arquivos de `assets/`). Tudo que
   não estiver nela vai direto para a rede, sem passar por cache
   nem ser gravado.

   A versão anterior fazia o contrário — bloqueava `/api/` e
   guardava o resto. Quando as rotas passaram a ser `/workspace/`,
   isso virou dois problemas de uma vez: a tela mostrava lista
   velha depois de um cadastro, e o cache guardava dado que não
   podia estar ali. Allowlist não tem esse modo de falhar.
   ============================================================= */
var VERSAO = "vc-clinic-shell-v2";

var CASCO = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./assets/css/tokens.css",
  "./assets/css/base.css",
  "./assets/css/layout.css",
  "./assets/css/components.css",
  "./assets/css/views.css",
  "./assets/css/auth.css",
  "./assets/images/simbolo.png",
  "./assets/images/simbolo-claro.png",
  "./assets/images/marca-texto.png",
  "./assets/images/marca-texto-branco.png",
  "./assets/images/icone-192.png",
  "./assets/images/icone-512.png"
];

/* O que pode ser guardado: o casco e qualquer arquivo estático de
   `assets/`. Nada mais — e as rotas de dados (/auth, /workspace,
   /session, /professions) não moram em `assets/`. */
function podeGuardar(url) {
  if (url.origin !== self.location.origin) return false;
  var caminho = url.pathname;
  if (/\/assets\//.test(caminho)) return true;
  return /(^|\/)(index\.html|manifest\.webmanifest)$/.test(caminho) ||
         caminho === new URL("./", self.location).pathname;
}

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(VERSAO)
      .then(function (c) { return c.addAll(CASCO); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (chaves) {
      return Promise.all(chaves.filter(function (k) { return k !== VERSAO; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;

  var url = new URL(req.url);

  /* Não é casco? O service worker sai da frente: a requisição vai
     para a rede como se ele não existisse. */
  if (!podeGuardar(url)) return;

  e.respondWith(
    caches.match(req).then(function (guardado) {
      if (guardado) return guardado;
      return fetch(req).then(function (resp) {
        /* Segunda trava: se a resposta pedir para não ser
           guardada, respeitamos — mesmo sendo do casco. */
        var controle = resp.headers.get("Cache-Control") || "";
        if (resp.ok && controle.indexOf("no-store") === -1) {
          var copia = resp.clone();
          caches.open(VERSAO).then(function (c) { c.put(req, copia); });
        }
        return resp;
      }).catch(function () {
        /* Offline: devolve o casco para a tela não quebrar.
           Dado nenhum vem daqui — a tela vai mostrar o erro de
           conexão dela. */
        return caches.match("./index.html");
      });
    })
  );
});

/* Logout limpa tudo o que ficou guardado neste navegador.
   O painel envia esta mensagem ao encerrar a sessão. */
self.addEventListener("message", function (e) {
  if (!e.data || e.data.tipo !== "limpar-cache") return;
  e.waitUntil(
    caches.keys().then(function (chaves) {
      return Promise.all(chaves.map(function (k) { return caches.delete(k); }));
    })
  );
});
