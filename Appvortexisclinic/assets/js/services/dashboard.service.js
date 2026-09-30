/* =============================================================
   Início — uma chamada só.

     GET /workspace/dashboard

   A tela inicial precisa de seis recortes ao mesmo tempo: o dia,
   os próximos, a contagem de pessoas, o mês, as pendências e a
   semana. Seis chamadas seriam seis idas ao banco e seis chances
   de cada uma calcular do seu jeito.

   Os números chegam prontos, calculados pela camada de domínio do
   servidor. A view não soma nada — só desenha.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  VC.services.dashboard = {
    carregar: function () {
      return base.buscar("/workspace/dashboard").then(function (d) {
        return {
          hoje: (d.hoje || []).map(mapa.atendimento),
          resumoDia: mapa.resumoDia(d.resumo_dia),
          proximos: (d.proximos || []).map(mapa.atendimento),
          pacientes: {
            total: d.clientes.total,
            ativos: d.clientes.ativos,
            inativos: d.clientes.inativos,
            arquivados: d.clientes.arquivados
          },
          /* Sem permissão de financeiro, o servidor não manda os
             números — e a tela simplesmente não mostra os cartões. */
          financeiro: mapa.financeiro(d.financeiro) || {
            recebido: 0, pendente: 0, previsto: 0, total: 0,
            meta: null, percentualMeta: null, variacaoMesAnterior: null
          },
          pendencias: (d.pendencias || []).map(mapa.atendimento),
          semana: mapa.resumoSemana(d.semana)
        };
      });
    }
  };
})(window);
