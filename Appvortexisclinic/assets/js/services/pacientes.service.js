/* =============================================================
   Pessoas atendidas — agora vindo do banco.

     GET    /workspace/clients?busca=&status=&com_pendencia=
     GET    /workspace/clients/contagem
     GET    /workspace/clients/{id}
     GET    /workspace/clients/{id}/appointments
     POST   /workspace/clients
     PATCH  /workspace/clients/{id}
     POST   /workspace/clients/{id}/archive

   O resumo de cada pessoa (último, próximo, presença, em aberto)
   vem calculado do servidor. Não é preguiça: é a regra de que
   tela e relatório não podem divergir — a conta é feita uma vez,
   na camada de domínio do backend.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  VC.services.pacientes = {
    listar: function (filtros) {
      filtros = filtros || {};
      var status = filtros.status && filtros.status !== "todos"
        ? mapa.paraApi.statusCliente[filtros.status] || filtros.status
        : "todos";

      /* Sem página, devolve a lista como sempre. Com página, devolve
         {lista, total, pagina} — o total vem do cabeçalho. */
      var caminho = "/workspace/clients" + base.query({
        busca: filtros.busca,
        status: status,
        com_pendencia: filtros.somenteComPendencia ? "true" : "",
        limite: filtros.limite,
        pagina: filtros.pagina
      });

      if (filtros.pagina) {
        return base.escopado(function () { return VC.api.listaPaginada(caminho); })
          .then(function (r) {
            return {
              lista: (r.dados || []).map(mapa.cliente),
              total: r.total,
              pagina: r.pagina
            };
          });
      }

      return base.buscar(caminho).then(function (lista) {
        return (lista || []).map(mapa.cliente);
      });
    },

    obter: function (id) {
      /* Ficha e histórico numa ida só do ponto de vista da tela. */
      return Promise.all([
        base.buscar("/workspace/clients/" + encodeURIComponent(id)),
        base.buscar("/workspace/clients/" + encodeURIComponent(id) + "/appointments")
      ]).then(function (r) {
        var pessoa = mapa.cliente(r[0]);
        pessoa.historico = (r[1] || []).map(mapa.atendimento);
        return pessoa;
      });
    },

    contar: function () {
      return base.buscar("/workspace/clients/contagem").then(function (c) {
        return { total: c.total, ativos: c.ativos, inativos: c.inativos, arquivados: c.arquivados };
      });
    },

    criar: function (dados) {
      return base.enviar("post", "/workspace/clients", mapa.clienteParaApi(dados))
        .then(mapa.cliente);
    },

    atualizar: function (id, dados) {
      return base.enviar("patch", "/workspace/clients/" + encodeURIComponent(id),
                         mapa.clienteParaApi(dados)).then(mapa.cliente);
    },

    /* Arquivar é lógico: o histórico continua. Exclusão de verdade
       só existe no fluxo de LGPD, e lá é decidida item a item. */
    arquivar: function (id) {
      return base.enviar("post", "/workspace/clients/" + encodeURIComponent(id) + "/archive")
        .then(mapa.cliente);
    }
  };
})(window);
