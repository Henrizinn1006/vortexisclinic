/* =============================================================
   Configurações da conta (tenant_settings)

     GET   /workspace/settings
     PATCH /workspace/settings

   Era o último service que ainda não falava com o banco. Agora fala
   — e `assets/js/data/mock.js` deixou de existir.

   **Ler é de todo mundo, gravar não.** Qualquer pessoa da conta lê:
   a jornada desenha a grade da agenda e a terminologia troca os
   rótulos da interface inteira. Gravar exige `settings.manage`.

   **A terminologia é saneada duas vezes.** `core/terms.js` recusa
   marcação antes de enviar, e o servidor recusa de novo ao gravar,
   devolvendo em `recusados` o que não entrou. A tela avisa em vez de
   fingir que salvou.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  VC.services.configuracoes = {
    obter: function () {
      return base.buscar("/workspace/settings").then(mapa.configuracao);
    },

    /* Plano, limites e uso (GET /workspace/plan). Exige `settings.manage`;
       a tela só chama para quem tem. */
    plano: function () {
      return base.buscar("/workspace/plan").then(mapa.plano);
    },

    /* Contratar: o servidor cria a assinatura no Asaas e devolve o link
       da fatura. O plano NÃO muda aqui — muda quando o pagamento for
       confirmado. O CPF/CNPJ vai ao gateway e não é guardado. */
    contratar: function (chave, cpfCnpj) {
      return base.enviar("post", "/workspace/plan/checkout",
                         { plano: chave, cpf_cnpj: cpfCnpj });
    },

    cancelarAssinatura: function () {
      return base.enviar("post", "/workspace/plan/cancel", {}).then(mapa.plano);
    },

    salvar: function (dados) {
      dados = dados || {};
      var corpo = {};
      if (dados.jornadaInicio) corpo.jornada_inicio = dados.jornadaInicio;
      if (dados.jornadaFim) corpo.jornada_fim = dados.jornadaFim;
      if (dados.dias) corpo.dias_da_semana = dados.dias;
      if (dados.duracaoPadrao) corpo.duracao_padrao = Number(dados.duracaoPadrao);
      if (dados.intervalo !== undefined && dados.intervalo !== null && dados.intervalo !== "") {
        corpo.intervalo = Number(dados.intervalo);
      }
      if (dados.toleranciaFalta !== undefined && dados.toleranciaFalta !== null
          && dados.toleranciaFalta !== "") {
        corpo.tolerancia_falta = Number(dados.toleranciaFalta);
      }
      if (dados.fuso) corpo.fuso = dados.fuso;
      if (dados.terminologia) corpo.terminologia = dados.terminologia;

      /* Meta vazia e meta zero não são a mesma coisa: vazia é "não
         defini", zero seria uma meta de zero. Por isso o sinalizador
         separado em vez de mandar 0. */
      if (dados.limparMeta) corpo.limpar_meta = true;
      else if (dados.metaMensal !== undefined && dados.metaMensal !== null
               && dados.metaMensal !== "") corpo.meta_mensal = String(dados.metaMensal);

      return base.enviar("patch", "/workspace/settings", corpo).then(mapa.configuracao);
    }
  };
})(window);
