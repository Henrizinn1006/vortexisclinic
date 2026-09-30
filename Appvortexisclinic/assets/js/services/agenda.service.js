/* =============================================================
   Agenda — recorrência e bloqueios.

     POST   /workspace/series
     GET    /workspace/clients/{id}/series
     POST   /workspace/series/{id}/end
     GET    /workspace/blocks
     POST   /workspace/blocks
     DELETE /workspace/blocks/{id}

   **Criar recorrência devolve três coisas**: a série, o que foi
   criado, e o que NÃO deu — com o motivo. Um horário ocupado no
   meio não derruba as outras onze; ele volta na lista de conflitos
   para a pessoa decidir.

   **Bloqueio é da sua agenda por padrão.** Fechar a clínica inteira
   exige dizer `contaInteira` — e enxergar a conta toda.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  VC.services.agenda = {
    /* ---------- recorrência ---------- */
    criarSerie: function (dados) {
      dados = dados || {};
      return base.enviar("post", "/workspace/series", {
        cliente_id: dados.pacienteId,
        inicio: new Date(dados.inicio).toISOString(),
        frequencia: dados.frequencia || "weekly",
        ocorrencias: Number(dados.ocorrencias || 8),
        ate: dados.ate || null,
        duracao_min: dados.duracaoMin ? Number(dados.duracaoMin) : null,
        modalidade: dados.modalidade || null,
        valor: dados.valor !== undefined && dados.valor !== null && dados.valor !== ""
          ? String(dados.valor) : null,
        observacao: dados.observacao || null
      }).then(function (r) {
        return {
          serie: mapa.serie(r.serie),
          criados: (r.criados || []).map(mapa.atendimento),
          conflitos: (r.conflitos || []).map(mapa.conflitoDaSerie)
        };
      });
    },

    seriesDoPaciente: function (pacienteId) {
      return base.buscar("/workspace/clients/" + encodeURIComponent(pacienteId) + "/series")
        .then(function (lista) { return (lista || []).map(mapa.serie); });
    },

    encerrarSerie: function (id, dados) {
      dados = dados || {};
      return base.enviar("post", "/workspace/series/" + encodeURIComponent(id) + "/end", {
        motivo: dados.motivo || null,
        cancelar_futuros: dados.cancelarFuturos !== false
      }).then(mapa.serie);
    },

    /* ---------- bloqueios ---------- */
    bloqueios: function (de, ate) {
      return base.buscar("/workspace/blocks" + base.query({
        de: de ? new Date(de).toISOString() : "",
        ate: ate ? new Date(ate).toISOString() : ""
      })).then(function (lista) { return (lista || []).map(mapa.bloqueio); });
    },

    bloquear: function (dados) {
      dados = dados || {};
      return base.enviar("post", "/workspace/blocks", {
        inicio: new Date(dados.inicio).toISOString(),
        fim: new Date(dados.fim).toISOString(),
        titulo: dados.titulo,
        tipo: dados.tipo || "other",
        conta_inteira: !!dados.contaInteira,
        forcar: !!dados.forcar
      }).then(function (r) {
        return {
          bloqueio: mapa.bloqueio(r.bloqueio),
          atendimentosNoPeriodo: (r.atendimentos_no_periodo || []).map(mapa.atendimento)
        };
      });
    },

    removerBloqueio: function (id) {
      return base.escopado(function () {
        return VC.api.remover("/workspace/blocks/" + encodeURIComponent(id));
      }).then(mapa.bloqueio);
    }
  };
})(window);
