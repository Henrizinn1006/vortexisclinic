/* =============================================================
   CLIENTE HTTP DA API
   -------------------------------------------------------------
   Único lugar do painel que fala com o servidor.

   Três coisas que este arquivo garante:

   1. O cookie de sessão viaja em toda chamada (credentials:
      "include") e NUNCA é lido por JavaScript — ele é HttpOnly.
      O painel não guarda token em lugar nenhum: nem localStorage,
      nem memória, nem variável. Isso tira o prêmio de um XSS.

   2. Escrita leva o token CSRF no cabeçalho. Ele vem de um cookie
      legível (double submit): o navegador de um site atacante até
      consegue mandar o cookie, mas não consegue LER o valor para
      montar o cabeçalho.

   3. Erro chega em formato único ({status, code, message}), então
      nenhuma tela precisa interpretar resposta crua — e mensagem
      interna do servidor não vaza para a interface.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var METODOS_SEGUROS = { GET: 1, HEAD: 1, OPTIONS: 1 };

  function base() {
    return (VC.config && VC.config.api && VC.config.api.base) || "";
  }

  /* O cookie CSRF é legível de propósito — é assim que o padrão
     double submit funciona. O de sessão continua invisível aqui. */
  function tokenCsrf() {
    var nome = (VC.config.api && VC.config.api.cookieCsrf) || "vc_csrf";
    var partes = (document.cookie || "").split(";");
    for (var i = 0; i < partes.length; i++) {
      var par = partes[i].trim();
      if (par.indexOf(nome + "=") === 0) return decodeURIComponent(par.slice(nome.length + 1));
    }
    return "";
  }

  function erro(status, code, message) {
    var e = new Error(message || "falha na requisição");
    e.status = status; e.code = code || "erro"; return e;
  }

  function pedir(metodo, caminho, corpo) {
    var opcoes = {
      method: metodo,
      credentials: "include",            // o cookie de sessão precisa viajar
      headers: { "Accept": "application/json" },
      cache: "no-store"                  // resposta de dados não fica em cache
    };

    if (corpo !== undefined && corpo !== null) {
      opcoes.headers["Content-Type"] = "application/json";
      opcoes.body = JSON.stringify(corpo);
    }
    if (!METODOS_SEGUROS[metodo]) {
      opcoes.headers["X-CSRF-Token"] = tokenCsrf();
    }

    return global.fetch(base() + caminho, opcoes).then(function (r) {
      var tipo = r.headers.get("content-type") || "";
      var lendo = tipo.indexOf("application/json") > -1 ? r.json() : Promise.resolve(null);

      return lendo.then(function (dados) {
        if (r.ok) return dados;

        /* O servidor responde {detail:{code,message}} ou {code,message}.
           Nada além disso é exibido: detalhe interno fica no log dele. */
        var d = (dados && dados.detail) || dados || {};
        throw erro(r.status, d.code, d.message);
      });
    }, function () {
      /* Rede fora, servidor parado, CORS recusado: tudo cai aqui. */
      throw erro(0, "sem_conexao", "Não foi possível falar com o servidor.");
    });
  }

  /* Download de arquivo: `fetch` com credenciais e Blob, em vez de um
     link direto para a API. Três motivos: o cookie de sessão viaja do
     mesmo jeito que nas outras chamadas; a URL do documento não fica no
     histórico do navegador; e o erro chega como erro, não como uma aba
     em branco com JSON. */
  function baixar(caminho) {
    return global.fetch(base() + caminho, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { "Accept": "*/*" }
    }).then(function (r) {
      if (!r.ok) {
        var tipo = r.headers.get("content-type") || "";
        var lendo = tipo.indexOf("application/json") > -1
          ? r.json() : Promise.resolve(null);
        return lendo.then(function (dados) {
          var d = (dados && dados.detail) || dados || {};
          throw erro(r.status, d.code, d.message);
        });
      }
      var nome = "";
      var cabecalho = r.headers.get("content-disposition") || "";
      var achado = cabecalho.match(/filename="?([^"]+)"?/);
      if (achado) nome = achado[1];
      return r.blob().then(function (blob) { return { blob: blob, nome: nome }; });
    }, function () {
      throw erro(0, "sem_conexao", "Não foi possível falar com o servidor.");
    });
  }

  /* Lista paginada: o total vem em `X-Total-Count`, não no corpo — é o
     que permitiu acrescentar paginação sem refazer nenhuma tela. */
  function listaPaginada(caminho) {
    return global.fetch(base() + caminho, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      headers: { "Accept": "application/json" }
    }).then(function (r) {
      return r.json().then(function (dados) {
        if (!r.ok) {
          var d = (dados && dados.detail) || dados || {};
          throw erro(r.status, d.code, d.message);
        }
        var total = parseInt(r.headers.get("X-Total-Count"), 10);
        return {
          dados: dados || [],
          /* Sem o cabeçalho (rota sem paginação, ou CORS sem expor),
             o total é o tamanho do que veio — nunca `undefined` na tela. */
          total: isNaN(total) ? (dados || []).length : total,
          pagina: parseInt(r.headers.get("X-Page"), 10) || 1
        };
      });
    }, function () {
      throw erro(0, "sem_conexao", "Não foi possível falar com o servidor.");
    });
  }

  VC.api = {
    get: function (caminho) { return pedir("GET", caminho); },
    listaPaginada: listaPaginada,
    baixar: baixar,
    post: function (caminho, corpo) { return pedir("POST", caminho, corpo); },
    put: function (caminho, corpo) { return pedir("PUT", caminho, corpo); },
    patch: function (caminho, corpo) { return pedir("PATCH", caminho, corpo); },
    remover: function (caminho) { return pedir("DELETE", caminho); },
    tokenCsrf: tokenCsrf
  };
})(window);
