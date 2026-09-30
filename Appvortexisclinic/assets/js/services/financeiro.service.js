/* =============================================================
   Financeiro — leitura e caixa.

     GET  /workspace/finance/summary?mes=
     GET  /workspace/finance/pending
     GET  /workspace/finance/series?meses=
     GET  /workspace/payments?de=&ate=&metodo=
     POST /workspace/appointments/{id}/payment     (baixa)
     POST /workspace/appointments/{id}/waive       (isenção)
     POST /workspace/payments/{id}/refund          (estorno)

   Uma coisa que mudou e vale saber: **"recebido" é regime de
   caixa**. Soma os pagamentos pela data em que o dinheiro entrou,
   não pela data do atendimento. Um atendimento de agosto pago em
   setembro conta em setembro — é assim que bate com o extrato.

   Ler o financeiro é `finance.read`; mexer no dinheiro é
   `finance.write`. São permissões diferentes de propósito.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  function dataISO(v) {
    if (!v) return "";
    var d = VC.fmt.toDate(v);
    return d.toISOString();
  }

  VC.services.financeiro = {
    resumoMes: function (dataRef) {
      var mes = dataRef ? VC.fmt.toDate(dataRef) : null;
      return base.buscar("/workspace/finance/summary" + base.query({
        mes: mes ? mes.toISOString().slice(0, 10) : ""
      })).then(mapa.financeiro);
    },

    pendencias: function () {
      return base.buscar("/workspace/finance/pending").then(function (lista) {
        return (lista || []).map(mapa.atendimento);
      });
    },

    serieMensal: function (meses) {
      return base.buscar("/workspace/finance/series" + base.query({ meses: meses || 6 }))
        .then(function (serie) {
          return (serie || []).map(function (p) {
            /* O servidor manda "2026-09-01"; a tela desenha com Date. */
            return { mes: VC.fmt.toDate(p.mes), valor: Number(p.valor || 0), quantidade: p.quantidade };
          });
        });
    },

    /* Livro-caixa: o que entrou, por quando entrou. */
    pagamentos: function (filtros) {
      filtros = filtros || {};
      return base.buscar("/workspace/payments" + base.query({
        de: dataISO(filtros.de),
        ate: dataISO(filtros.ate),
        metodo: filtros.metodo && filtros.metodo !== "todos" ? filtros.metodo : "",
        limite: filtros.limite
      })).then(function (lista) {
        return (lista || []).map(mapa.pagamento);
      });
    },

    doAtendimento: function (atendimentoId) {
      return base.buscar("/workspace/appointments/" + encodeURIComponent(atendimentoId) + "/payments")
        .then(function (lista) { return (lista || []).map(mapa.pagamento); });
    },

    /* ---------- escrita ---------- */
    registrarPagamento: function (atendimentoId, dados) {
      dados = dados || {};
      return base.enviar("post",
        "/workspace/appointments/" + encodeURIComponent(atendimentoId) + "/payment", {
          metodo: dados.metodo || "pix",
          pago_em: dados.pagoEm ? dataISO(dados.pagoEm) : null,
          valor: dados.valor !== undefined && dados.valor !== null && dados.valor !== ""
            ? String(dados.valor) : null,
          observacao: dados.observacao || null
        }).then(mapa.pagamento);
    },

    /* Pagamento que não nasce de um atendimento: pacote, sinal, acerto.
       Sem ele, um pacote pago adiantado só entrava distorcendo a agenda. */
    registrarAvulso: function (pacienteId, dados) {
      dados = dados || {};
      return base.enviar("post",
        "/workspace/clients/" + encodeURIComponent(pacienteId) + "/payment", {
          valor: String(dados.valor),
          metodo: dados.metodo || "pix",
          pago_em: dados.pagoEm ? dataISO(dados.pagoEm) : null,
          observacao: dados.observacao || null
        }).then(mapa.pagamento);
    },

    isentar: function (atendimentoId, motivo) {
      return base.enviar("post",
        "/workspace/appointments/" + encodeURIComponent(atendimentoId) + "/waive",
        { motivo: motivo || null }).then(mapa.atendimento);
    },

    /* Estorno não apaga o lançamento: marca como devolvido e
       devolve o atendimento para pendente. */
    estornar: function (pagamentoId, motivo) {
      return base.enviar("post",
        "/workspace/payments/" + encodeURIComponent(pagamentoId) + "/refund",
        { motivo: motivo || null }).then(mapa.pagamento);
    }
  };
})(window);
