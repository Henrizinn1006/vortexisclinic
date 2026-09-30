/* =============================================================
   CAMADA DE ACESSO A DADOS
   -------------------------------------------------------------
   Todo service devolve Promise, e todos falam com a API. Não há mais
   nenhum dado de mentira no painel: o último que faltava eram as
   configurações da conta, e elas passaram a ter tabela e tela.

   ISOLAMENTO (regra do projeto, e o servidor repete tudo):

   1. FAIL-CLOSED — nada é consultado sem workspace ativo.
      `VC.session.tenantId()` lança quando não há vínculo válido, e
      `escopado()` deixa o erro subir ANTES de qualquer requisição.
      Não existe caminho em que a ausência de conta vire consulta
      ampla.
   2. O TENANT NUNCA VIAJA — nenhuma chamada manda `tenant_id`. O
      servidor resolve pela sessão, e ignora o que vier de fora.
   3. RECURSO DE OUTRA CONTA NÃO EXISTE — a API responde 404, nunca
      403: negar com 403 já confirmaria que o registro existe.
   4. PERMISSÃO É DO SERVIDOR — o que o painel faz é esconder o que
      a pessoa não pode usar. A decisão real é de lá, em toda
      requisição.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  function NaoEncontrado(recurso) {
    var e = new Error("recurso não encontrado");
    e.status = 404; e.code = "nao_encontrado"; e.recurso = recurso;
    return e;
  }

  function SemPermissao(permissao) {
    var e = new Error("sem permissão");
    e.status = 403; e.code = "sem_permissao"; e.permissao = permissao;
    return e;
  }


  /* ---------- Caminho da API ---------- */

  /* Toda chamada de dados passa por aqui. A checagem de workspace
     acontece ANTES da rede: sem conta ativa, nem sai requisição. */
  function escopado(fn) {
    try {
      VC.session.tenantId();          // lança se não houver workspace ativo
    } catch (e) {
      return Promise.reject(e);       // fail-closed: nada é consultado
    }
    return fn();
  }

  function buscar(caminho) {
    return escopado(function () { return VC.api.get(caminho); });
  }

  function enviar(metodo, caminho, corpo) {
    return escopado(function () { return VC.api[metodo](caminho, corpo); });
  }

  /* Monta query string ignorando o que está vazio. Valores são
     codificados — nada de concatenar texto cru numa URL. */
  function query(parametros) {
    var partes = [];
    Object.keys(parametros || {}).forEach(function (chave) {
      var valor = parametros[chave];
      if (valor === undefined || valor === null || valor === "") return;
      if (valor instanceof Date) valor = valor.toISOString();
      partes.push(encodeURIComponent(chave) + "=" + encodeURIComponent(valor));
    });
    return partes.length ? "?" + partes.join("&") : "";
  }

  /* O caminho do mock morreu aqui.

     Ele existia para os módulos que ainda não tinham banco. Desde a
     etapa das configurações graváveis não sobrou nenhum: tudo o que a
     tela mostra vem da API, com isolamento por conta e número
     calculado no servidor. `assets/js/data/mock.js` foi apagado. */

  VC.services = VC.services || {};
  VC.services._base = {
    /* API */
    escopado: escopado,
    buscar: buscar,
    enviar: enviar,
    query: query,
    NaoEncontrado: NaoEncontrado,
    SemPermissao: SemPermissao
  };
})(window);
