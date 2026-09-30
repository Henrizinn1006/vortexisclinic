/* =============================================================
   Atendimentos e agenda — agora vindo do banco.

     GET  /workspace/appointments?de=&ate=&status=&modalidade=&pagamento=
     GET  /workspace/appointments/proximos?quantidade=
     GET  /workspace/appointments/{id}
     POST /workspace/appointments
     POST /workspace/appointments/{id}/status
     POST /workspace/appointments/{id}/reschedule
     GET  /workspace/agenda?de=&ate=

   O conflito de horário é decidido no servidor, dentro da
   transação. O painel não tenta adivinhar: manda e trata a
   resposta 409.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  function paraApi(mapaDeValores, valor, vazio) {
    if (!valor || valor === vazio) return "";
    return mapaDeValores[valor] || valor;
  }

  function lista(r) { return (r || []).map(mapa.atendimento); }

  VC.services.atendimentos = {
    listar: function (filtros) {
      filtros = filtros || {};
      return base.buscar("/workspace/appointments" + base.query({
        de: filtros.de,
        ate: filtros.ate,
        status: paraApi(mapa.paraApi.statusAtendimento, filtros.status, "todos"),
        modalidade: paraApi(mapa.paraApi.modalidade, filtros.modalidade, "todas"),
        pagamento: paraApi(mapa.paraApi.pagamento, filtros.pagamento, "todos"),
        limite: filtros.limite
      })).then(function (r) {
        var saida = lista(r);
        if (filtros.pacienteId) {
          saida = saida.filter(function (a) { return a.pacienteId === filtros.pacienteId; });
        }
        return saida;
      });
    },

    doDia: function (data) {
      var d = VC.fmt.toDate(data || new Date());
      var de = new Date(d); de.setHours(0, 0, 0, 0);
      var ate = new Date(d); ate.setHours(23, 59, 59, 999);
      return this.listar({ de: de, ate: ate });
    },

    doPeriodo: function (de, ate) {
      return base.buscar("/workspace/agenda" + base.query({ de: de, ate: ate })).then(lista);
    },

    proximos: function (quantidade) {
      return base.buscar("/workspace/appointments/proximos" + base.query({
        quantidade: quantidade || 5
      })).then(lista);
    },

    obter: function (id) {
      return base.buscar("/workspace/appointments/" + encodeURIComponent(id))
        .then(mapa.atendimento);
    },

    registrar: function (dados) {
      return base.enviar("post", "/workspace/appointments", {
        cliente_id: dados.pacienteId,
        inicio: dados.inicio instanceof Date ? dados.inicio.toISOString() : dados.inicio,
        duracao_min: dados.duracaoMin || 50,
        modalidade: dados.modalidade ? mapa.paraApi.modalidade[dados.modalidade] : null,
        valor: dados.valor !== undefined && dados.valor !== null ? String(dados.valor) : null,
        observacao: dados.observacao || null
      }).then(mapa.atendimento);
    },

    atualizarStatus: function (id, status, motivo) {
      return base.enviar("post", "/workspace/appointments/" + encodeURIComponent(id) + "/status", {
        status: mapa.paraApi.statusAtendimento[status] || status,
        motivo: motivo || null
      }).then(mapa.atendimento);
    },

    reagendar: function (id, inicio, duracaoMin) {
      return base.enviar("post", "/workspace/appointments/" + encodeURIComponent(id) + "/reschedule", {
        inicio: inicio instanceof Date ? inicio.toISOString() : inicio,
        duracao_min: duracaoMin || null
      }).then(mapa.atendimento);
    }
  };
})(window);
