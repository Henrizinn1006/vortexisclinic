/* =============================================================
   CONFIGURAÇÃO DO PAINEL
   Navegação, chaves de funcionalidade e endereço da futura API.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  VC.config = {
    produto: "Vortexis Clinic",
    /* A vertical (cor e termos) vem do TENANT ativo, não daqui.
       Este valor é só o fallback antes de a sessão responder. */
    verticalPadrao: "psicologia",
    versao: "0.10.0 — documentos e LGPD",

    /* Quando o backend existir: baseUrl preenchido e fonte = "api".
       Os services já falam essa língua; nada mais muda. */
    api: {
      /* Onde a API responde. Em desenvolvimento o painel roda em
         :5500 e a API em :8000, então a origem é diferente — é por
         isso que o backend declara CORS restrito e o cliente envia
         credentials: "include". Em produção, mesma origem: "". */
      /* Pode ser trocado sem editar código: basta declarar
         window.VC_API_BASE antes dos scripts (útil em produção,
         onde API e painel ficam na mesma origem: ""). */
      base: (typeof global.VC_API_BASE === "string" ? global.VC_API_BASE
        /* Sem declaração explícita: em localhost a API fica na :8000;
           em qualquer outro endereço (produção) é a mesma origem. */
        : (/^(localhost|127\.0\.0\.1)$/.test(global.location && global.location.hostname)
            ? "http://127.0.0.1:8000" : "")),
      cookieCsrf: "vc_csrf",

      /* Tudo vem da API: identidade, pessoas, agenda, atendimentos,
         financeiro, prontuário, equipe e configurações. Não sobrou
         nenhum dado de mentira no painel. */
      fonteIdentidade: "api",
      fonte: "api"
    },

    /* Etapas seguintes entram ligando a chave correspondente. */
    features: {
      autenticacao: true,
      notificacoes: false,
      relatoriosPdf: false,
      multiProfissional: false,      // clínica com vários psicólogos
      teleatendimento: false
    },

    /* Navegação: uma fonte só para sidebar, gaveta e barra inferior.
       - "termo" busca o rótulo em core/terms.js (muda por tenant);
       - "rotulo" é usado quando o nome não muda entre profissões;
       - "permissao" esconde o item de quem não pode usá-lo. O front
         esconde por conforto; quem nega o dado é o servidor.
       - "classe" marca o que é conteúdo clínico (nunca aparece para
         quem não tem permissão clínica). */
    navegacao: [
      {
        titulo: "Rotina",
        itens: [
          { id: "dashboard",    rota: "/",             rotulo: "Início",  curto: "Início",  mobile: true },
          { id: "agenda",       rota: "/agenda",       termo: "schedule.title", curto: "Agenda", mobile: true,
            permissao: "agenda.read" },
          { id: "atendimentos", rota: "/atendimentos", termo: "appointment.many", curtoTermo: "session.many",
            permissao: "appointments.read" },
          { id: "pacientes",    rota: "/pacientes",    termo: "client.many", curtoTermo: "client.many", mobile: true,
            permissao: "patients.read" }
        ]
      },
      {
        titulo: "Gestão",
        itens: [
          { id: "financeiro",  rota: "/financeiro",  termo: "finance.title", curto: "Financeiro", mobile: true,
            permissao: "finance.read" },
          { id: "pendencias",  rota: "/pendencias",  termo: "pending.title", curto: "Pendências",
            permissao: "finance.read", contador: "pendencias" },
          { id: "anotacoes",   rota: "/anotacoes",   termo: "record.many", curto: "Registros",
            permissao: "clinical_records.read", classe: "clinical" },
          { id: "relatorios",  rota: "/relatorios",  rotulo: "Relatórios", curto: "Relatórios" }
        ]
      },
      {
        titulo: "Conta",
        itens: [
          { id: "perfil",         rota: "/perfil",         rotulo: "Perfil profissional", curto: "Perfil" },
          { id: "equipe",         rota: "/equipe",         rotulo: "Equipe",              curto: "Equipe",
            permissao: "members.manage" },
          { id: "privacidade",    rota: "/privacidade",    rotulo: "Privacidade",         curto: "Privacidade",
            permissao: "data_requests.manage" },
          { id: "configuracoes",  rota: "/configuracoes",  rotulo: "Configurações",       curto: "Ajustes",
            permissao: "settings.manage" }
        ]
      }
    ],

  };
})(window);
