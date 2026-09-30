/* =============================================================
   Privacidade — consentimento, pedidos do titular e auditoria.

     GET/POST /workspace/clients/{id}/consents
     POST     /workspace/consents/{id}/revoke
     GET/POST /workspace/data-requests
     POST     /workspace/data-requests/{id}/decisions
     POST     /workspace/data-requests/{id}/decisions/{item}/apply
     POST     /workspace/data-requests/{id}/close
     GET      /workspace/clients/{id}/data-package
     POST     /workspace/clients/{id}/anonymize
     GET/PUT  /workspace/retention-policies
     GET      /workspace/audit

   **Decidir e executar são chamadas separadas.** Registrar o plano
   não apaga nada; executar é um segundo passo, explícito. É o que
   permite alguém revisar antes de a ação virar irreversível — e
   praticamente tudo aqui é irreversível.

   **Exclusão não é DELETE.** Um pedido vira decisões por tipo de
   dado, cada uma com motivo e base legal — inclusive quando a
   decisão é *manter*.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  function doCliente(id, sufixo) {
    return "/workspace/clients/" + encodeURIComponent(id) + sufixo;
  }

  VC.services.privacidade = {
    /* ---------- consentimento ---------- */
    consentimentos: function (pacienteId) {
      return base.buscar(doCliente(pacienteId, "/consents")).then(function (lista) {
        return (lista || []).map(mapa.consentimento);
      });
    },

    registrarConsentimento: function (pacienteId, dados) {
      dados = dados || {};
      return base.enviar("post", doCliente(pacienteId, "/consents"), {
        tipo: dados.tipo,
        versao: dados.versao || "1",
        texto: dados.texto || null,
        origem: dados.origem || "in_person",
        observacao: dados.observacao || null
      }).then(mapa.consentimento);
    },

    revogarConsentimento: function (id) {
      return base.enviar("post", "/workspace/consents/" + encodeURIComponent(id) + "/revoke", {})
        .then(mapa.consentimento);
    },

    /* ---------- pedidos do titular ---------- */
    pedidos: function (status) {
      return base.buscar("/workspace/data-requests" + base.query({ status: status || "" }))
        .then(function (lista) { return (lista || []).map(mapa.pedido); });
    },

    pedido: function (id) {
      return base.buscar("/workspace/data-requests/" + encodeURIComponent(id)).then(mapa.pedido);
    },

    abrirPedido: function (pacienteId, dados) {
      dados = dados || {};
      return base.enviar("post", doCliente(pacienteId, "/data-requests"), {
        tipo: dados.tipo,
        solicitante: dados.solicitante || "titular",
        prazo: dados.prazo ? new Date(dados.prazo).toISOString() : null,
        observacao: dados.observacao || null
      }).then(mapa.pedido);
    },

    decidir: function (pedidoId, dados) {
      return base.enviar("post",
        "/workspace/data-requests/" + encodeURIComponent(pedidoId) + "/decisions", {
          alvo: dados.alvo, decisao: dados.decisao,
          motivo: dados.motivo, base_legal: dados.baseLegal || null
        }).then(mapa.pedido);
    },

    /* Segundo passo, explícito: é aqui que a coisa acontece. */
    aplicar: function (pedidoId, decisaoId) {
      return base.enviar("post",
        "/workspace/data-requests/" + encodeURIComponent(pedidoId) +
        "/decisions/" + encodeURIComponent(decisaoId) + "/apply", {}).then(mapa.pedido);
    },

    encerrar: function (pedidoId, dados) {
      return base.enviar("post",
        "/workspace/data-requests/" + encodeURIComponent(pedidoId) + "/close", {
          status: dados.status, observacao: dados.observacao || null
        }).then(mapa.pedido);
    },

    /* ---------- portabilidade e anonimização ---------- */
    baixarPacote: function (pacienteId, nome) {
      return base.escopado(function () {
        return VC.api.baixar(doCliente(pacienteId, "/data-package"));
      }).then(function (r) {
        var url = global.URL.createObjectURL(r.blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = r.nome || ("dados-" + (nome || pacienteId) + ".json");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        global.setTimeout(function () { global.URL.revokeObjectURL(url); }, 1000);
        return r;
      });
    },

    anonimizar: function (pacienteId, motivo) {
      return base.enviar("post", doCliente(pacienteId, "/anonymize"), { motivo: motivo })
        .then(mapa.cliente);
    },

    /* ---------- retenção ---------- */
    politicas: function () {
      return base.buscar("/workspace/retention-policies").then(function (lista) {
        return (lista || []).map(mapa.politica);
      });
    },

    definirPolitica: function (dados) {
      return base.enviar("put", "/workspace/retention-policies", {
        alvo: dados.alvo,
        profissao: dados.profissao || null,
        meses: dados.meses ? Number(dados.meses) : null,
        base_legal: dados.baseLegal || null,
        observacao: dados.observacao || null
      }).then(mapa.politica);
    },

    /* ---------- auditoria ---------- */
    auditoria: function (limite) {
      return base.buscar("/workspace/audit" + base.query({ limite: limite || 200 }))
        .then(function (lista) { return (lista || []).map(mapa.evento); });
    }
  };
})(window);
