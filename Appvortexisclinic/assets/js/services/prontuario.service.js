/* =============================================================
   Prontuário — registro clínico.

     GET  /workspace/clients/{id}/notes
     GET  /workspace/notes/{id}
     GET  /workspace/notes/{id}/versions
     GET  /workspace/notes/{id}/content?versao=
     POST /workspace/clients/{id}/notes
     PUT  /workspace/notes/{id}
     POST /workspace/notes/{id}/sign
     GET  /workspace/clients/{id}/clinical-access

   Duas coisas que valem saber antes de mexer aqui.

   **Conteúdo tem chamada própria.** Listar não traz texto: traz
   data, tipo, versão e quem assinou. O texto só vem em
   `conteudo()`, e é essa chamada que o servidor registra como
   leitura na trilha de acesso. Abrir a aba e ler a evolução são
   eventos diferentes — de propósito.

   **Nada disto encosta em cache.** A API responde `no-store` em
   tudo, o service worker só guarda arquivos estáticos, e sair da
   conta limpa o que houver. Conteúdo clínico não fica em disco.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  function caminhoNota(id) {
    return "/workspace/notes/" + encodeURIComponent(id);
  }

  VC.services.prontuario = {
    /* Metadado das notas de uma pessoa. Sem conteúdo. */
    listar: function (pacienteId) {
      return base.buscar("/workspace/clients/" + encodeURIComponent(pacienteId) + "/notes")
        .then(function (lista) { return (lista || []).map(mapa.nota); });
    },

    ficha: function (id) {
      return base.buscar(caminhoNota(id)).then(mapa.nota);
    },

    versoes: function (id) {
      return base.buscar(caminhoNota(id) + "/versions").then(function (lista) {
        return (lista || []).map(mapa.versaoDaNota);
      });
    },

    /* A única chamada que devolve texto clínico — e a que vira trilha. */
    conteudo: function (id, versao) {
      return base.buscar(caminhoNota(id) + "/content" + base.query({ versao: versao }))
        .then(mapa.conteudoDaNota);
    },

    criar: function (pacienteId, dados) {
      dados = dados || {};
      return base.enviar("post",
        "/workspace/clients/" + encodeURIComponent(pacienteId) + "/notes", {
          conteudo: dados.conteudo,
          tipo: dados.tipo || "session",
          ocorrido_em: dados.ocorridoEm ? new Date(dados.ocorridoEm).toISOString() : null,
          atendimento_id: dados.atendimentoId || null
        }).then(mapa.nota);
    },

    /* Salvar cria a versão seguinte. A anterior continua legível. */
    salvar: function (id, dados) {
      dados = dados || {};
      return base.enviar("put", caminhoNota(id), {
        conteudo: dados.conteudo,
        motivo: dados.motivo || null
      }).then(mapa.nota);
    },

    assinar: function (id) {
      return base.enviar("post", caminhoNota(id) + "/sign", {}).then(mapa.nota);
    },

    /* Trilha de acesso da pessoa. Exige permissão de auditoria —
       que é diferente de permissão de leitura clínica. */
    trilha: function (pacienteId) {
      return base.buscar("/workspace/clients/" + encodeURIComponent(pacienteId) + "/clinical-access")
        .then(function (lista) { return (lista || []).map(mapa.acessoClinico); });
    }
  };
})(window);
