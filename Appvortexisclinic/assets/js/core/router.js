/* =============================================================
   Roteador por hash (#/pacientes/123).
   Sem dependência e funciona abrindo o arquivo direto, sem servidor.
   Quando houver backend, este é o único ponto a trocar por
   history.pushState + rotas do servidor.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var rotas = [];
  var antes = [];
  var depois = [];
  var atual = null;

  /* "/pacientes/:id" -> regex + nomes dos parâmetros */
  function compilar(padrao) {
    var nomes = [];
    var partes = padrao.split("/").filter(Boolean);
    var corpo = partes.length
      ? partes.map(function (parte) {
          if (parte.charAt(0) === ":") {
            nomes.push(parte.slice(1));
            return "/([^/]+)";
          }
          return "/" + parte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }).join("")
      : "/";
    return { re: new RegExp("^" + corpo + "$"), nomes: nomes };
  }

  function add(padrao, config) {
    var c = compilar(padrao);
    rotas.push({ padrao: padrao, re: c.re, nomes: c.nomes, config: config });
    return VC.router;
  }

  /* O hash pode trazer consulta (#/pacientes?busca=ana):
     a rota casa só com o caminho; a query fica com a view. */
  function caminhoAtual() {
    var h = global.location.hash.replace(/^#/, "").split("?")[0];
    if (!h || h === "/") return "/";
    return h.replace(/\/$/, "");
  }

  function casar(caminho) {
    for (var i = 0; i < rotas.length; i++) {
      var m = caminho.match(rotas[i].re);
      if (m) {
        var params = {};
        rotas[i].nomes.forEach(function (nome, idx) { params[nome] = decodeURIComponent(m[idx + 1]); });
        return { rota: rotas[i], params: params };
      }
    }
    return null;
  }

  function navegar(caminho) {
    global.location.hash = "#" + caminho;
  }

  function resolver() {
    var caminho = caminhoAtual();
    var achado = casar(caminho) || casar("/404");
    if (!achado) return;

    atual = { caminho: caminho, params: achado.params, config: achado.rota.config };
    antes.forEach(function (fn) { fn(atual); });

    var saida = achado.rota.config.render(achado.params);
    /* A view devolve html`` (SafeHtml) ou cuida do container sozinha.
       String crua é recusada pela renderização segura. */
    var alvo = document.querySelector("[data-outlet]");
    if (saida && alvo) VC.safe.render(alvo, saida);

    if (typeof achado.rota.config.mount === "function") {
      achado.rota.config.mount(achado.params, alvo);
    }

    depois.forEach(function (fn) { fn(atual); });
  }

  function iniciar() {
    global.addEventListener("hashchange", resolver);
    if (!global.location.hash) global.location.replace("#/");
    resolver();
  }

  VC.router = {
    add: add,
    iniciar: iniciar,
    navegar: navegar,
    resolver: resolver,
    atual: function () { return atual; },
    antesDeEntrar: function (fn) { antes.push(fn); },
    aposEntrar: function (fn) { depois.push(fn); }
  };
})(window);
