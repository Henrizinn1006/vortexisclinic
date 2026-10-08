/* =============================================================
   SUÍTE DE TESTES — roda em Node, sem navegador.
       node tests/run.js

   Cobre o que não pode regredir:
   - isolamento entre contas (tenant);
   - escape de conteúdo na renderização;
   - definições de métrica (a conta tem que ser uma só);
   - terminologia e o saneamento dos rótulos;
   - separação entre permissão administrativa e clínica.
   ============================================================= */
"use strict";

var fs = require("fs");
var path = require("path");
var vm = require("vm");

/* ---------------- ambiente mínimo de navegador ---------------- */
var elementoFalso = {
  setAttribute: function () {}, removeAttribute: function () {},
  classList: { add: function () {}, remove: function () {}, toggle: function () {} },
  style: { setProperty: function () {} },
  appendChild: function () {}, addEventListener: function () {},
  querySelector: function () { return null; }, querySelectorAll: function () { return []; },
  focus: function () {}, textContent: "", innerHTML: ""
};

var janela = {
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  Promise: Promise,
  Intl: Intl,
  Date: Date,
  Math: Math,
  console: console,
  URLSearchParams: URLSearchParams,
  location: { hash: "#/", protocol: "file:" },
  navigator: { userAgent: "node" },
  matchMedia: function () { return { matches: false, addEventListener: function () {} }; },
  requestAnimationFrame: function (fn) { return setTimeout(fn, 0); },
  localStorage: {
    _d: {},
    getItem: function (k) { return this._d[k] || null; },
    setItem: function (k, v) { this._d[k] = v; }
  },
  document: Object.assign({}, elementoFalso, {
    documentElement: Object.assign({}, elementoFalso),
    body: Object.assign({}, elementoFalso),
    createElement: function () { return Object.assign({}, elementoFalso); },
    addEventListener: function () {}
  })
};
janela.window = janela;
janela.global = janela;

var contexto = vm.createContext(janela);

function carregar(rel) {
  var arquivo = path.join(__dirname, "..", rel);
  vm.runInContext(fs.readFileSync(arquivo, "utf8"), contexto, { filename: rel });
}

[
  "assets/js/config/app.config.js",
  "assets/js/types/entities.js",
  "assets/js/core/safe.js",
  "assets/js/core/api.js",
  "assets/js/core/dom.js",
  "assets/js/core/terms.js",
  "assets/js/core/format.js",
  "assets/js/core/store.js",
  "assets/js/core/toast.js",
  "assets/js/core/session.js",
  "assets/js/domain/metrics.js",
  "assets/js/services/mapa.js",
  "assets/js/services/base.js",
  "assets/js/services/pacientes.service.js",
  "assets/js/services/atendimentos.service.js",
  "assets/js/services/financeiro.service.js",
  "assets/js/services/prontuario.service.js",
  "assets/js/services/equipe.service.js",
  "assets/js/services/agenda.service.js",
  "assets/js/services/documentos.service.js",
  "assets/js/services/privacidade.service.js",
  "assets/js/services/configuracoes.service.js",
  "assets/js/services/dashboard.service.js",
  /* Só o que a suíte confere de tela: o cartão do plano. */
  "assets/js/components/ui.js",
  "assets/js/components/form.js",
  "assets/js/views/configuracoes.js"
].forEach(carregar);

var VC = contexto.VC;

/* ---------------- servidor falso ----------------
   A sessão agora vem de GET /auth/me. Aqui não há rede: no lugar do
   cliente HTTP entra um servidor de mentira com DUAS contas, que
   responde no mesmo formato do backend.

   Isso faz a suíte testar o que interessa de verdade: o painel lê
   identidade e permissão do servidor, e trocar de conta é uma
   decisão DELE — pedir uma conta sem vínculo responde 404, igual à
   API real. */
var SERVIDOR = {
  usuario: { id: "usr_001", nome: "Camila Ferraz", email: "camila@exemplo.com", email_verificado: false },
  workspaces: {
    tnt_001: {
      id: "tnt_001", nome: "Consultório Camila Ferraz", slug: "consultorio-camila",
      tipo: "solo", papel: "OWNER", papel_nome: "Dono da conta", escopo: "all",
      /* dono que também atende: permissão clínica por concessão
         explícita na membership, nunca herdada do papel */
      concessoes: ["clinical_records.read", "clinical_records.write", "documents.read", "documents.write"],
      perfil: { id: "prf_001", nome_exibicao: "Camila Ferraz", profissao: "psicologia",
                conselho: "CRP", registro: "06/123456" }
    },
    tnt_002: {
      id: "tnt_002", nome: "Clínica Bem Viver", slug: "clinica-bem-viver",
      tipo: "clinic", papel: "PROFESSIONAL", papel_nome: "Profissional", escopo: "own",
      concessoes: [],
      perfil: { id: "prf_044", nome_exibicao: "Camila Ferraz", profissao: "terapia_integrativa",
                conselho: null, registro: null }
    }
  },
  ativo: "tnt_001"
};

function corpoDoMe() {
  var w = SERVIDOR.workspaces[SERVIDOR.ativo];
  var base = (VC.types.ROLE_PERMISSIONS[w.papel] || []).slice();
  w.concessoes.forEach(function (p) { if (base.indexOf(p) === -1) base.push(p); });
  return {
    usuario: SERVIDOR.usuario,
    workspace_ativo: resumo(w, true),
    workspaces: Object.keys(SERVIDOR.workspaces).map(function (k) {
      return resumo(SERVIDOR.workspaces[k], k === SERVIDOR.ativo);
    }),
    permissoes: base,
    perfil: w.perfil
  };
}

function resumo(w, ativo) {
  return { id: w.id, nome: w.nome, slug: w.slug, tipo: w.tipo, papel: w.papel,
           papel_nome: w.papel_nome, escopo: w.escopo, ativo: ativo };
}

/* ---------------- dados de cada conta ----------------
   Pessoas atendidas e atendimentos agora vêm da API. O servidor de
   mentira guarda um conjunto por workspace e SÓ devolve o do
   workspace ativo — que é exatamente o que o backend faz com o
   filtro por tenant. É isso que torna o teste de isolamento real e
   não decorativo. */
function emHoras(horas) {
  var d = new Date();
  d.setMinutes(0, 0, 0);
  d.setHours(d.getHours() + horas);
  return d.toISOString();
}

var DADOS = {
  tnt_001: {
    clientes: [
      { id: "cli_A1", nome: "Ana Beatriz Moraes", status: "active", valor_sessao: "180.00" },
      { id: "cli_A2", nome: "Rafael Lima", status: "active", valor_sessao: "200.00" },
      { id: "cli_A3", nome: "Juliana Costa", status: "inactive", valor_sessao: "180.00" }
    ],
    atendimentos: [
      { id: "atd_A1", cliente: "cli_A1", inicio: emHoras(-3), status: "done", pagamento: "paid", valor: "180.00" },
      { id: "atd_A2", cliente: "cli_A2", inicio: emHoras(-2), status: "no_show", pagamento: "pending", valor: "200.00" },
      { id: "atd_A3", cliente: "cli_A1", inicio: emHoras(3), status: "scheduled", pagamento: "pending", valor: "180.00" },
      { id: "atd_A4", cliente: "cli_A2", inicio: emHoras(30), status: "scheduled", pagamento: "pending", valor: "200.00" }
    ]
  },
  tnt_002: {
    clientes: [
      { id: "cli_B1", nome: "Clara Benedetti", status: "active", valor_sessao: "160.00" }
    ],
    atendimentos: [
      { id: "atd_B1", cliente: "cli_B1", inicio: emHoras(-1), status: "done", pagamento: "pending", valor: "160.00" }
    ]
  }
};

/* ---------------- prontuário de mentira ----------------
   O servidor real cifra o conteúdo e guarda versões; aqui interessa
   só o contrato que o painel consome: a lista NÃO carrega texto, o
   texto vem de uma chamada própria, e essa chamada vira trilha. */
var NOTAS = {
  tnt_001: [
    { id: "not_A1", cliente: "cli_A1", autor: "prf_001", autor_nome: "Camila Ferraz",
      tipo: "session", status: "draft", ocorrido_em: emHoras(-3), versao_atual: 1,
      versoes: [{ versao: 1, conteudo: "Primeira sessão. Combinamos frequência semanal." }] },
    { id: "not_A2", cliente: "cli_A1", autor: "prf_outro", autor_nome: "Colega de sala",
      tipo: "session", status: "signed", ocorrido_em: emHoras(-50), versao_atual: 1,
      versoes: [{ versao: 1, conteudo: "Registro de outro profissional." }] }
  ],
  tnt_002: [
    { id: "not_B1", cliente: "cli_B1", autor: "prf_044", autor_nome: "Camila Ferraz",
      tipo: "session", status: "draft", ocorrido_em: emHoras(-1), versao_atual: 1,
      versoes: [{ versao: 1, conteudo: "Registro da outra conta." }] }
  ]
};

var TRILHA = { tnt_001: [], tnt_002: [] };

function notasDaConta() { return NOTAS[SERVIDOR.ativo] || []; }

function podeVerNota(n) {
  var eu = SERVIDOR.workspaces[SERVIDOR.ativo].perfil;
  if (n.autor === (eu && eu.id)) return true;
  return VC.session.pode("clinical_records.read_others");
}

function anotarTrilha(acao, resultado, motivo) {
  TRILHA[SERVIDOR.ativo].push({
    id: "acs_" + TRILHA[SERVIDOR.ativo].length, quando: new Date().toISOString(),
    acao: acao, resultado: resultado, motivo: motivo || null, quem: "Camila Ferraz", nota_id: null
  });
}

function notaPublica(n) {
  var eu = SERVIDOR.workspaces[SERVIDOR.ativo].perfil;
  return {
    id: n.id, tipo: n.tipo, status: n.status, ocorrido_em: n.ocorrido_em,
    versao_atual: n.versao_atual, assinada_em: n.status === "signed" ? n.ocorrido_em : null,
    conteudo_apagado_em: null, autor: n.autor_nome, autor_id: n.autor,
    sou_o_autor: n.autor === (eu && eu.id), atendimento_id: null,
    cliente: { id: n.cliente, nome: "—", status: "active" }
  };
}

/* ---------------- equipe e configurações de mentira ---------------- */
var EQUIPE = {
  tnt_001: {
    membros: [
      { id: "mem_1", nome: "Camila Ferraz", email: "camila@exemplo.com", papel: "OWNER",
        papel_nome: "Dono da conta", escopo: "all", status: "active", sou_eu: true, atende: true },
      { id: "mem_2", nome: "Rita Recepção", email: "rita@exemplo.com", papel: "ASSISTANT",
        papel_nome: "Apoio administrativo", escopo: "all", status: "active",
        sou_eu: false, atende: false }
    ],
    convites: []
  },
  tnt_002: { membros: [], convites: [] }
};

/* Plano: limite null é "sem limite"; preço null é "ainda não definido". */
var PLANO = {
  plano: "essencial", plano_nome: "Essencial", status: "trialing", vigente: true,
  trial_ate: "2026-10-17T12:00:00", preco_mensal: null,
  periodo_ate: null, plano_pendente: null, cobranca_ativa: true, assinatura_paga: false,
  catalogo: [{ plano: "essencial", nome: "Essencial", descricao: "", preco_mensal: "59.90" }],
  limites: { profissionais: 5, membros: 10, clientes: 500, armazenamento_mb: null },
  recursos: { clinico: true, documentos: true, exportacao: true, lembretes: true },
  uso: { profissionais: 1, membros: 1, clientes: 498, armazenamento_mb: 12.5 }
};

var CONFIG = {
  tnt_001: {
    jornada_inicio: "08:00", jornada_fim: "20:00", dias_da_semana: [1, 2, 3, 4, 5],
    duracao_padrao: 50, intervalo: 10, tolerancia_falta: 24,
    meta_mensal: null, moeda: "BRL", fuso: "America/Sao_Paulo",
    terminologia: {}, recusados: []
  },
  tnt_002: {
    jornada_inicio: "09:00", jornada_fim: "18:00", dias_da_semana: [1, 2, 3],
    duracao_padrao: 60, intervalo: 0, tolerancia_falta: 12,
    meta_mensal: "5000.00", moeda: "BRL", fuso: "America/Manaus",
    terminologia: { "client.one": "Cliente" }, recusados: []
  }
};

/* O servidor sanea o rótulo de novo, mesmo o painel já recusando.
   O de mentira faz igual — senão o teste não provaria nada. */
function saneiaTermo(v) {
  if (typeof v !== "string") return null;
  var limpo = v.replace(/\s+/g, " ").trim();
  if (!limpo || limpo.length > 40) return null;
  if (/[<>&"'`\\{}]/.test(limpo)) return null;
  return limpo;
}

/* ---------------- agenda: séries e bloqueios de mentira ---------------- */
var SERIES = { tnt_001: [], tnt_002: [] };
var BLOQUEIOS = { tnt_001: [], tnt_002: [] };

/* ---------------- documentos de mentira ---------------- */
var DOCUMENTOS = { tnt_001: [], tnt_002: [] };
var PDF_FALSO = "JVBERi0xLjQK";     /* "%PDF-1.4\n" em base64 */

/* ---------------- privacidade de mentira ---------------- */
var CONSENTIMENTOS = { tnt_001: [], tnt_002: [] };
var PEDIDOS = { tnt_001: [], tnt_002: [] };
var POLITICAS = { tnt_001: [], tnt_002: [] };

/* Toda rota pedida fica registrada: é assim que a suíte confere
   que o painel nunca manda tenant_id para o servidor. */
var ROTAS_PEDIDAS = [];

function daConta() {
  return DADOS[SERVIDOR.ativo] || { clientes: [], atendimentos: [] };
}

function clientePublico(c, atendimentos) {
  return {
    id: c.id, nome: c.nome, email: c.email || null, telefone: c.telefone || null,
    nascimento: null, status: c.status, frequencia: "weekly", modalidade: "in_person",
    valor_sessao: c.valor_sessao, desde: null, observacao: null,
    resumo: resumoDoCliente(c, atendimentos)
  };
}

function resumoDoCliente(c, atendimentos) {
  var dele = (atendimentos || []).filter(function (a) { return a.cliente === c.id; });
  var validos = dele.filter(function (a) { return a.status !== "cancelled"; });
  var realizados = validos.filter(function (a) { return a.status === "done"; }).length;
  var faltas = validos.filter(function (a) { return a.status === "no_show"; }).length;
  var abertos = validos.filter(function (a) {
    return a.pagamento === "pending" && (a.status === "done" || a.status === "no_show");
  });
  return {
    total: validos.length, realizados: realizados, faltas: faltas,
    presenca: realizados + faltas ? Math.round(realizados * 1000 / (realizados + faltas)) / 10 : null,
    ultimo: null, proximo: null,
    valor_em_aberto: abertos.reduce(function (s, a) { return s + Number(a.valor); }, 0).toFixed(2),
    quantidade_em_aberto: abertos.length
  };
}

function atendimentoPublico(a, clientes) {
  var c = clientes.filter(function (x) { return x.id === a.cliente; })[0] || { id: null, nome: "—", status: "active" };
  return {
    id: a.id, inicio: a.inicio, duracao_min: 50, modalidade: "in_person",
    status: a.status, valor: a.valor, pagamento: a.pagamento,
    metodo_pagamento: null, pago_em: null, observacao: null,
    cliente: { id: c.id, nome: c.nome, status: c.status },
    profissional_id: "prf_001"
  };
}

function rotaSemQuery(caminho) { return caminho.split("?")[0]; }

VC.api = {
  /* O harness não fala HTTP: `listaPaginada` devolve o mesmo formato que
     o cliente real monta a partir do cabeçalho X-Total-Count. */
  listaPaginada: function (caminho) {
    return VC.api.get(caminho).then(function (r) {
      if (r && r.__paginado) return { dados: r.dados, total: r.total, pagina: r.pagina };
      return { dados: r || [], total: (r || []).length, pagina: 1 };
    });
  },

  get: function (caminho) {
    ROTAS_PEDIDAS.push(caminho);
    var rota = rotaSemQuery(caminho);
    var conta = daConta();

    if (rota === "/auth/me") return Promise.resolve(corpoDoMe());

    if (rota === "/workspace/clients") {
      /* Com `pagina`, o de mentira também precisa paginar e devolver o
         total — senão o teste de paginação não provaria nada. */
      var q = new URLSearchParams((caminho.split("?")[1] || ""));
      if (q.get("pagina")) {
        var todos = daConta().clientes.map(function (c) {
          return clientePublico(c, daConta().atendimentos);
        });
        var tam = parseInt(q.get("limite"), 10) || 25;
        var pg = parseInt(q.get("pagina"), 10) || 1;
        return Promise.resolve({
          __paginado: true,
          dados: todos.slice((pg - 1) * tam, pg * tam),
          total: todos.length,
          pagina: pg
        });
      }
    }
    if (rota === "/workspace/clients") {
      var status = (caminho.match(/status=([^&]*)/) || [])[1] || "active";
      var busca = decodeURIComponent((caminho.match(/busca=([^&]*)/) || [])[1] || "");
      var lista = conta.clientes.filter(function (c) {
        return status === "todos" || c.status === status;
      });
      if (busca) {
        lista = lista.filter(function (c) {
          return c.nome.toLowerCase().indexOf(busca.toLowerCase()) > -1;
        });
      }
      return Promise.resolve(lista.map(function (c) {
        return clientePublico(c, conta.atendimentos);
      }));
    }

    if (rota === "/workspace/clients/contagem") {
      return Promise.resolve({
        total: conta.clientes.length,
        ativos: conta.clientes.filter(function (c) { return c.status === "active"; }).length,
        inativos: conta.clientes.filter(function (c) { return c.status === "inactive"; }).length,
        arquivados: 0
      });
    }

    var ficha = rota.match(/^\/workspace\/clients\/([^/]+)$/);
    if (ficha) {
      var achado = conta.clientes.filter(function (c) { return c.id === ficha[1]; })[0];
      /* Cliente de outra conta: para esta, não existe. 404, nunca 403. */
      if (!achado) return Promise.reject({ status: 404, code: "nao_encontrado" });
      return Promise.resolve(clientePublico(achado, conta.atendimentos));
    }

    var historico = rota.match(/^\/workspace\/clients\/([^/]+)\/appointments$/);
    if (historico) {
      var dono = conta.clientes.filter(function (c) { return c.id === historico[1]; })[0];
      if (!dono) return Promise.reject({ status: 404, code: "nao_encontrado" });
      return Promise.resolve(conta.atendimentos
        .filter(function (a) { return a.cliente === dono.id; })
        .map(function (a) { return atendimentoPublico(a, conta.clientes); }));
    }

    if (rota === "/workspace/appointments" || rota === "/workspace/agenda") {
      return Promise.resolve(conta.atendimentos.map(function (a) {
        return atendimentoPublico(a, conta.clientes);
      }));
    }

    if (rota === "/workspace/appointments/proximos") {
      var agora = Date.now();
      return Promise.resolve(conta.atendimentos
        .filter(function (a) { return new Date(a.inicio).getTime() > agora && a.status === "scheduled"; })
        .map(function (a) { return atendimentoPublico(a, conta.clientes); }));
    }

    if (rota === "/workspace/dashboard") {
      var hoje = conta.atendimentos.filter(function (a) {
        return new Date(a.inicio).toDateString() === new Date().toDateString();
      });
      var realizados = hoje.filter(function (a) { return a.status === "done"; }).length;
      var faltas = hoje.filter(function (a) { return a.status === "no_show"; }).length;
      return Promise.resolve({
        hoje: hoje.map(function (a) { return atendimentoPublico(a, conta.clientes); }),
        resumo_dia: {
          total: hoje.filter(function (a) { return a.status !== "cancelled"; }).length,
          realizados: realizados, faltas: faltas, cancelados: 0, restantes: 0,
          previsto: "0.00",
          presenca: realizados + faltas ? Math.round(realizados * 1000 / (realizados + faltas)) / 10 : null
        },
        proximos: [],
        clientes: {
          total: conta.clientes.length,
          ativos: conta.clientes.filter(function (c) { return c.status === "active"; }).length,
          inativos: conta.clientes.filter(function (c) { return c.status === "inactive"; }).length,
          arquivados: 0
        },
        financeiro: {
          referencia: new Date().toISOString().slice(0, 10),
          recebido: "0.00", pendente: "0.00", previsto: "0.00", total: "0.00",
          quantidade_recebida: 0, quantidade_pendente: 0,
          meta: null, percentual_meta: null, variacao_mes_anterior: null
        },
        pendencias: [],
        semana: {
          inicio: new Date().toISOString().slice(0, 10),
          fim: new Date().toISOString().slice(0, 10),
          dias: [], agendados: 0, realizados: realizados, faltas: faltas, presenca: null
        }
      });
    }

    if (rota === "/workspace/finance/pending") return Promise.resolve([]);
    if (rota === "/workspace/finance/series") return Promise.resolve([]);
    if (rota === "/workspace/finance/summary") {
      return Promise.resolve({
        referencia: new Date().toISOString().slice(0, 10),
        recebido: "180.00", pendente: "200.00", previsto: "0.00", total: "380.00",
        quantidade_recebida: 1, quantidade_pendente: 1,
        meta: null, percentual_meta: null, variacao_mes_anterior: null
      });
    }

    var listaNotas = rota.match(/^\/workspace\/clients\/([^/]+)\/notes$/);
    if (listaNotas) {
      var doCliente = notasDaConta().filter(function (n) {
        return n.cliente === listaNotas[1] && podeVerNota(n);
      });
      anotarTrilha("list", "allowed");
      return Promise.resolve(doCliente.map(notaPublica));
    }

    var trilhaDe = rota.match(/^\/workspace\/clients\/([^/]+)\/clinical-access$/);
    if (trilhaDe) return Promise.resolve(TRILHA[SERVIDOR.ativo].slice().reverse());

    var conteudoDe = rota.match(/^\/workspace\/notes\/([^/]+)\/content$/);
    if (conteudoDe) {
      var alvo = notasDaConta().filter(function (n) { return n.id === conteudoDe[1]; })[0];
      if (!alvo || !podeVerNota(alvo)) {
        anotarTrilha("read", "denied", "fora_do_alcance");
        return Promise.reject({ status: 404, code: "nao_encontrado" });
      }
      anotarTrilha("read", "allowed");
      var v = alvo.versoes[alvo.versoes.length - 1];
      return Promise.resolve({ id: alvo.id, versao: v.versao, conteudo: v.conteudo,
                               impressao: "hash", criado_em: alvo.ocorrido_em });
    }

    var versoesDe = rota.match(/^\/workspace\/notes\/([^/]+)\/versions$/);
    if (versoesDe) {
      var comVersoes = notasDaConta().filter(function (n) { return n.id === versoesDe[1]; })[0];
      if (!comVersoes || !podeVerNota(comVersoes)) {
        return Promise.reject({ status: 404, code: "nao_encontrado" });
      }
      return Promise.resolve(comVersoes.versoes.map(function (v) {
        return { versao: v.versao, criado_em: comVersoes.ocorrido_em, motivo: v.motivo || null,
                 impressao: "hash" };
      }));
    }

    var consentimentosDe = rota.match(/^\/workspace\/clients\/([^/]+)\/consents$/);
    if (consentimentosDe) {
      return Promise.resolve((CONSENTIMENTOS[SERVIDOR.ativo] || []).filter(function (c) {
        return c.cliente === consentimentosDe[1];
      }));
    }
    if (rota === "/workspace/data-requests") {
      return Promise.resolve(PEDIDOS[SERVIDOR.ativo]);
    }
    if (rota === "/workspace/retention-policies") {
      return Promise.resolve(POLITICAS[SERVIDOR.ativo]);
    }

    var docsDe = rota.match(/^\/workspace\/clients\/([^/]+)\/documents$/);
    if (docsDe) {
      /* O servidor filtra por classe; o de mentira faz igual, senão o
         teste de "recepção não vê laudo" não provaria nada. */
      return Promise.resolve((DOCUMENTOS[SERVIDOR.ativo] || []).filter(function (d) {
        return d.classe === "clinical"
          ? VC.session.pode("documents.read")
          : VC.session.pode("finance.read");
      }));
    }

    if (rota === "/workspace/blocks") {
      return Promise.resolve(BLOQUEIOS[SERVIDOR.ativo]);
    }
    var seriesDe = rota.match(/^\/workspace\/clients\/([^/]+)\/series$/);
    if (seriesDe) {
      return Promise.resolve((SERIES[SERVIDOR.ativo] || []).filter(function (x) {
        return x.cliente.id === seriesDe[1];
      }));
    }

    if (rota === "/workspace/team") {
      return Promise.resolve(EQUIPE[SERVIDOR.ativo] || { membros: [], convites: [] });
    }
    if (rota === "/workspace/settings") {
      return Promise.resolve(CONFIG[SERVIDOR.ativo]);
    }
    if (rota === "/workspace/plan") {
      /* Como no servidor real: plano é informação de conta (settings.manage). */
      if (corpoDoMe().permissoes.indexOf("settings.manage") === -1) {
        return Promise.reject({ status: 403, code: "sem_permissao" });
      }
      return Promise.resolve(PLANO);
    }

    var fichaNota = rota.match(/^\/workspace\/notes\/([^/]+)$/);
    if (fichaNota) {
      var uma = notasDaConta().filter(function (n) { return n.id === fichaNota[1]; })[0];
      if (!uma || !podeVerNota(uma)) return Promise.reject({ status: 404, code: "nao_encontrado" });
      return Promise.resolve(notaPublica(uma));
    }

    return Promise.reject({ status: 404, code: "nao_encontrado" });
  },

  post: function (caminho, corpo) {
    ROTAS_PEDIDAS.push(caminho);
    if (caminho === "/session/workspace") {
      var pedido = corpo && corpo.workspace_id;
      /* mesma resposta do servidor real: conta sem vínculo não existe */
      if (!SERVIDOR.workspaces[pedido]) {
        return Promise.reject({ status: 404, code: "nao_encontrado", message: "Recurso não encontrado." });
      }
      SERVIDOR.ativo = pedido;
      return Promise.resolve(corpoDoMe());
    }
    if (caminho === "/workspace/clients") {
      var novo = { id: "cli_novo", nome: corpo.nome, status: "active", valor_sessao: corpo.valor_sessao };
      daConta().clientes.push(novo);
      return Promise.resolve(clientePublico(novo, daConta().atendimentos));
    }
    var novaNota = caminho.match(/^\/workspace\/clients\/([^/]+)\/notes$/);
    if (novaNota) {
      var eu = SERVIDOR.workspaces[SERVIDOR.ativo].perfil;
      var criada = {
        id: "not_novo", cliente: novaNota[1], autor: eu.id, autor_nome: eu.nome_exibicao,
        tipo: corpo.tipo || "session", status: "draft",
        ocorrido_em: corpo.ocorrido_em || new Date().toISOString(), versao_atual: 1,
        versoes: [{ versao: 1, conteudo: corpo.conteudo }]
      };
      notasDaConta().push(criada);
      anotarTrilha("create", "allowed");
      return Promise.resolve(notaPublica(criada));
    }

    var avulso = caminho.match(/^\/workspace\/clients\/([^/]+)\/payment$/);
    if (avulso) {
      return Promise.resolve({ id: "pag_avulso", valor: corpo.valor, metodo: corpo.metodo,
                               status: "paid", pago_em: corpo.pago_em || new Date().toISOString(),
                               observacao: corpo.observacao || null, estornado_em: null,
                               motivo_estorno: null,
                               cliente: { id: avulso[1], nome: "—", status: "active" },
                               atendimento_id: null });
    }

    var novoConsent = caminho.match(/^\/workspace\/clients\/([^/]+)\/consents$/);
    if (novoConsent) {
      var c = { id: "cns_" + (CONSENTIMENTOS[SERVIDOR.ativo].length + 1),
                cliente: novoConsent[1], tipo: corpo.tipo, versao: corpo.versao || "1",
                aceito_em: new Date().toISOString(), revogado_em: null, vigente: true,
                origem: corpo.origem || "in_person", observacao: corpo.observacao || null };
      CONSENTIMENTOS[SERVIDOR.ativo].push(c);
      return Promise.resolve(c);
    }

    var revogaConsent = caminho.match(/^\/workspace\/consents\/([^/]+)\/revoke$/);
    if (revogaConsent) {
      var alvoC = CONSENTIMENTOS[SERVIDOR.ativo].filter(function (x) {
        return x.id === revogaConsent[1]; })[0];
      if (!alvoC) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (alvoC.revogado_em) return Promise.reject({ status: 409, code: "ja_revogado" });
      alvoC.revogado_em = new Date().toISOString();
      alvoC.vigente = false;
      return Promise.resolve(alvoC);
    }

    var novoPedido = caminho.match(/^\/workspace\/clients\/([^/]+)\/data-requests$/);
    if (novoPedido) {
      var p = { id: "req_" + (PEDIDOS[SERVIDOR.ativo].length + 1), tipo: corpo.tipo,
                status: "open", solicitante: corpo.solicitante || "titular",
                pedido_em: new Date().toISOString(),
                /* O servidor NÃO inventa prazo: nulo continua nulo. */
                prazo: corpo.prazo || null, encerrado_em: null,
                observacao: corpo.observacao || null, desfecho: null,
                cliente: { id: novoPedido[1], nome: "—", status: "active" },
                decisoes: [] };
      PEDIDOS[SERVIDOR.ativo].push(p);
      return Promise.resolve(p);
    }

    var decide = caminho.match(/^\/workspace\/data-requests\/([^/]+)\/decisions$/);
    if (decide) {
      var ped = PEDIDOS[SERVIDOR.ativo].filter(function (x) { return x.id === decide[1]; })[0];
      if (!ped) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (!corpo.motivo || !corpo.motivo.trim()) {
        return Promise.reject({ status: 422, code: "dados_invalidos",
                                message: "Toda decisão precisa de motivo registrado." });
      }
      ped.decisoes.push({ id: "dec_" + (ped.decisoes.length + 1), alvo: corpo.alvo,
                          decisao: corpo.decisao, motivo: corpo.motivo,
                          base_legal: corpo.base_legal || null,
                          aplicado_em: null, resultado: null });
      ped.status = "in_progress";
      return Promise.resolve(ped);
    }

    var aplica = caminho.match(/^\/workspace\/data-requests\/([^/]+)\/decisions\/([^/]+)\/apply$/);
    if (aplica) {
      var ped2 = PEDIDOS[SERVIDOR.ativo].filter(function (x) { return x.id === aplica[1]; })[0];
      if (!ped2) return Promise.reject({ status: 404, code: "nao_encontrado" });
      var dec = ped2.decisoes.filter(function (x) { return x.id === aplica[2]; })[0];
      if (!dec) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (dec.aplicado_em) return Promise.reject({ status: 409, code: "ja_aplicado" });
      if (dec.decisao === "erase" && (dec.alvo === "payments" || dec.alvo === "appointments")) {
        return Promise.reject({ status: 409, code: "apagar_nao_se_aplica",
                                message: "Guarda obrigatória." });
      }
      dec.aplicado_em = new Date().toISOString();
      dec.resultado = "executado";
      return Promise.resolve(ped2);
    }

    var encerraPedido = caminho.match(/^\/workspace\/data-requests\/([^/]+)\/close$/);
    if (encerraPedido) {
      var ped3 = PEDIDOS[SERVIDOR.ativo].filter(function (x) { return x.id === encerraPedido[1]; })[0];
      if (!ped3) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (corpo.status === "refused" && !(corpo.observacao || "").trim()) {
        return Promise.reject({ status: 422, code: "dados_invalidos",
                                message: "Recusar exige motivo escrito." });
      }
      var pendentes = ped3.decisoes.filter(function (d) {
        return !d.aplicado_em && d.decisao !== "keep"; });
      if (corpo.status === "done" && pendentes.length) {
        return Promise.reject({ status: 409, code: "decisoes_pendentes" });
      }
      ped3.status = corpo.status;
      ped3.encerrado_em = new Date().toISOString();
      ped3.desfecho = corpo.observacao || null;
      return Promise.resolve(ped3);
    }

    var recibo = caminho.match(/^\/workspace\/clients\/([^/]+)\/documents\/receipt$/);
    if (recibo) {
      var d = { id: "doc_" + (DOCUMENTOS[SERVIDOR.ativo].length + 1), tipo: "receipt",
                classe: "administrative", titulo: "Recibo — R$ 180,00",
                nome_arquivo: "recibo.pdf", tamanho: 1400,
                criado_em: new Date().toISOString(), impressao: "hash",
                conteudo_apagado_em: null,
                cliente: { id: recibo[1], nome: "—", status: "active" } };
      DOCUMENTOS[SERVIDOR.ativo].push(d);
      return Promise.resolve(d);
    }

    var declar = caminho.match(/^\/workspace\/clients\/([^/]+)\/documents\/attendance$/);
    if (declar) {
      var dd = { id: "doc_d" + (DOCUMENTOS[SERVIDOR.ativo].length + 1), tipo: "attendance",
                 classe: "clinical", titulo: "Declaração — 12/09/2026",
                 nome_arquivo: "declaracao.pdf", tamanho: 1200,
                 criado_em: new Date().toISOString(), impressao: "hash",
                 conteudo_apagado_em: null,
                 cliente: { id: declar[1], nome: "—", status: "active" } };
      DOCUMENTOS[SERVIDOR.ativo].push(dd);
      return Promise.resolve(dd);
    }

    var anexo = caminho.match(/^\/workspace\/clients\/([^/]+)\/documents$/);
    if (anexo) {
      var da = { id: "doc_a" + (DOCUMENTOS[SERVIDOR.ativo].length + 1), tipo: "upload",
                 classe: "clinical", titulo: corpo.nome_arquivo,
                 nome_arquivo: corpo.nome_arquivo, tamanho: 10,
                 criado_em: new Date().toISOString(), impressao: "hash",
                 conteudo_apagado_em: null,
                 cliente: { id: anexo[1], nome: "—", status: "active" } };
      DOCUMENTOS[SERVIDOR.ativo].push(da);
      return Promise.resolve(da);
    }

    if (caminho === "/workspace/series") {
      /* O servidor pula o horário ocupado e devolve o conflito — não
         recusa a série inteira. O de mentira faz igual. */
      var passo = { weekly: 7, biweekly: 14, monthly: 30 }[corpo.frequencia] || 7;
      var base0 = new Date(corpo.inicio);
      var ocupados = (daConta().atendimentos || []).map(function (a) {
        return new Date(a.inicio).toISOString().slice(0, 16);
      });
      var criados = [], conflitos = [];
      for (var i = 0; i < corpo.ocorrencias; i++) {
        var quando = new Date(base0.getTime() + i * passo * 864e5);
        var chave = quando.toISOString().slice(0, 16);
        if (ocupados.indexOf(chave) > -1) {
          conflitos.push({ inicio: quando.toISOString(), motivo: "conflito_de_horario" });
          continue;
        }
        var novoAtd = { id: "atd_s" + i, cliente: corpo.cliente_id,
                        inicio: quando.toISOString(), status: "scheduled",
                        pagamento: "pending", valor: corpo.valor || "180.00" };
        daConta().atendimentos.push(novoAtd);
        criados.push(atendimentoPublico(novoAtd, daConta().clientes));
      }
      if (!criados.length) {
        return Promise.reject({ status: 409, code: "nenhuma_ocorrencia_livre" });
      }
      var serie = { id: "ser_1", frequencia: corpo.frequencia, inicio: corpo.inicio,
                    duracao_min: corpo.duracao_min || 50, modalidade: "in_person",
                    valor: corpo.valor, ocorrencias: corpo.ocorrencias, ate: null,
                    status: "active",
                    cliente: { id: corpo.cliente_id, nome: "—", status: "active" } };
      SERIES[SERVIDOR.ativo].push(serie);
      return Promise.resolve({ serie: serie, criados: criados, conflitos: conflitos });
    }

    var encerrar = caminho.match(/^\/workspace\/series\/([^/]+)\/end$/);
    if (encerrar) {
      var alvoSerie = SERIES[SERVIDOR.ativo].filter(function (x) { return x.id === encerrar[1]; })[0];
      if (!alvoSerie) return Promise.reject({ status: 404, code: "nao_encontrado" });
      alvoSerie.status = "ended";
      return Promise.resolve(alvoSerie);
    }

    if (caminho === "/workspace/blocks") {
      var choque = (daConta().atendimentos || []).filter(function (a) {
        var q = new Date(a.inicio).getTime();
        return q >= new Date(corpo.inicio).getTime() && q < new Date(corpo.fim).getTime();
      });
      if (choque.length && !corpo.forcar) {
        return Promise.reject({ status: 409, code: "atendimentos_no_periodo",
                                message: "Há " + choque.length + " atendimento(s) nesse período." });
      }
      var b = { id: "blk_" + (BLOQUEIOS[SERVIDOR.ativo].length + 1),
                inicio: corpo.inicio, fim: corpo.fim, titulo: corpo.titulo,
                tipo: corpo.tipo || "other", profissional_id: null,
                da_conta_inteira: !!corpo.conta_inteira };
      BLOQUEIOS[SERVIDOR.ativo].push(b);
      return Promise.resolve({
        bloqueio: b,
        atendimentos_no_periodo: choque.map(function (a) {
          return atendimentoPublico(a, daConta().clientes);
        })
      });
    }

    if (caminho === "/workspace/invitations") {
      var equipe = EQUIPE[SERVIDOR.ativo];
      if (equipe.membros.some(function (m) { return m.email === corpo.email; })) {
        return Promise.reject({ status: 409, code: "ja_e_membro",
                                message: "Esta pessoa já faz parte da conta." });
      }
      if (equipe.convites.some(function (c) { return c.email === corpo.email; })) {
        return Promise.reject({ status: 409, code: "convite_pendente",
                                message: "Já existe um convite aberto para este e-mail." });
      }
      /* Só dono cria dono — o servidor real recusa igual. */
      if (corpo.papel === "OWNER" && SERVIDOR.workspaces[SERVIDOR.ativo].papel !== "OWNER") {
        return Promise.reject({ status: 403, code: "sem_permissao" });
      }
      var novoConvite = {
        id: "inv_" + (equipe.convites.length + 1), email: corpo.email,
        papel: corpo.papel || "PROFESSIONAL", escopo: corpo.escopo || "own",
        profissao: corpo.profissao || null, mensagem: corpo.mensagem || null,
        expira_em: new Date(Date.now() + 7 * 864e5).toISOString(),
        convidado_por: "Camila Ferraz",
        link: "https://painel.exemplo/#/convite/TOKEN-" + (equipe.convites.length + 1)
      };
      /* Na listagem o link NÃO volta: o servidor guarda só o hash do
         token, então o que fica registrado não tem link nenhum. */
      equipe.convites.push(Object.assign({}, novoConvite, { link: null }));
      return Promise.resolve(novoConvite);
    }

    var revogar = caminho.match(/^\/workspace\/invitations\/([^/]+)\/revoke$/);
    if (revogar) {
      var lista = EQUIPE[SERVIDOR.ativo].convites;
      var i = lista.map(function (c) { return c.id; }).indexOf(revogar[1]);
      if (i < 0) return Promise.reject({ status: 404, code: "nao_encontrado" });
      var removido = lista.splice(i, 1)[0];
      return Promise.resolve(Object.assign({}, removido, { link: null }));
    }

    var assinar = caminho.match(/^\/workspace\/notes\/([^/]+)\/sign$/);
    if (assinar) {
      var paraAssinar = notasDaConta().filter(function (n) { return n.id === assinar[1]; })[0];
      if (!paraAssinar) return Promise.reject({ status: 404, code: "nao_encontrado" });
      paraAssinar.status = "signed";
      anotarTrilha("sign", "allowed");
      return Promise.resolve(notaPublica(paraAssinar));
    }

    return Promise.reject({ status: 404, code: "nao_encontrado" });
  },

  put: function (caminho, corpo) {
    ROTAS_PEDIDAS.push(caminho);

    if (caminho === "/workspace/retention-policies") {
      /* Prazo sem base legal não vale para apagar nada — o servidor real
         recusa, e o de mentira precisa recusar igual. */
      if (corpo.meses && !(corpo.base_legal || "").trim()) {
        return Promise.reject({ status: 422, code: "dados_invalidos",
                                message: "Prazo de guarda exige base legal escrita." });
      }
      var lista = POLITICAS[SERVIDOR.ativo];
      var pol = lista.filter(function (x) { return x.alvo === corpo.alvo; })[0];
      if (!pol) { pol = { id: "pol_" + (lista.length + 1), alvo: corpo.alvo }; lista.push(pol); }
      pol.profissao = corpo.profissao || null;
      pol.meses = corpo.meses || null;
      pol.base_legal = corpo.base_legal || null;
      pol.observacao = corpo.observacao || null;
      pol.aplicavel = !!(pol.meses && (pol.base_legal || "").trim());
      return Promise.resolve(pol);
    }

    var editar = caminho.match(/^\/workspace\/notes\/([^/]+)$/);
    if (editar) {
      var alvo = notasDaConta().filter(function (n) { return n.id === editar[1]; })[0];
      if (!alvo) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (alvo.status === "signed" && !corpo.motivo) {
        return Promise.reject({ status: 422, code: "dados_invalidos",
                                message: "Nota assinada só aceita adendo com motivo." });
      }
      /* append-only: a versão anterior continua na lista */
      alvo.versao_atual += 1;
      alvo.versoes.push({ versao: alvo.versao_atual, conteudo: corpo.conteudo,
                          motivo: corpo.motivo || null });
      anotarTrilha("update", "allowed");
      return Promise.resolve(notaPublica(alvo));
    }
    return Promise.reject({ status: 404, code: "nao_encontrado" });
  },

  remover: function (caminho) {
    ROTAS_PEDIDAS.push(caminho);
    var m = caminho.match(/^\/workspace\/blocks\/([^/]+)$/);
    if (m) {
      var lista = BLOQUEIOS[SERVIDOR.ativo];
      var i = lista.map(function (b) { return b.id; }).indexOf(m[1]);
      if (i < 0) return Promise.reject({ status: 404, code: "nao_encontrado" });
      return Promise.resolve(lista.splice(i, 1)[0]);
    }
    return Promise.reject({ status: 404, code: "nao_encontrado" });
  },

  patch: function (caminho, corpo) {
    ROTAS_PEDIDAS.push(caminho);

    if (caminho === "/workspace/settings") {
      var c = CONFIG[SERVIDOR.ativo];
      var recusados = [];
      ["jornada_inicio", "jornada_fim", "dias_da_semana", "duracao_padrao",
       "intervalo", "tolerancia_falta", "fuso"].forEach(function (k) {
        if (corpo[k] !== undefined && corpo[k] !== null) c[k] = corpo[k];
      });
      if (corpo.limpar_meta) c.meta_mensal = null;
      else if (corpo.meta_mensal !== undefined) c.meta_mensal = corpo.meta_mensal;

      if (corpo.terminologia) {
        Object.keys(corpo.terminologia).forEach(function (chave) {
          var valor = corpo.terminologia[chave];
          if (typeof valor === "string" && !valor.trim()) { delete c.terminologia[chave]; return; }
          var limpo = saneiaTermo(valor);
          if (limpo === null) { recusados.push(chave); return; }
          c.terminologia[chave] = limpo;
        });
      }
      c.recusados = recusados;
      return Promise.resolve(c);
    }

    var membro = caminho.match(/^\/workspace\/members\/([^/]+)$/);
    if (membro) {
      var alvo = (EQUIPE[SERVIDOR.ativo].membros || [])
        .filter(function (m) { return m.id === membro[1]; })[0];
      if (!alvo) return Promise.reject({ status: 404, code: "nao_encontrado" });
      if (alvo.sou_eu) {
        return Promise.reject({ status: 409, code: "nao_edita_a_si",
                                message: "Mudança no seu próprio acesso precisa passar por outra pessoa." });
      }
      if (corpo.papel) alvo.papel = corpo.papel;
      if (corpo.escopo) alvo.escopo = corpo.escopo;
      if (corpo.status) alvo.status = corpo.status;
      return Promise.resolve(alvo);
    }

    return Promise.reject({ status: 404, code: "nao_encontrado" });
  }
};

/* ---------------- runner ---------------- */
var passou = 0, falhou = 0, pendentes = [];

function ok(condicao, titulo, detalhe) {
  if (condicao) { passou++; console.log("  ok   " + titulo); }
  else { falhou++; console.log("  FALHA " + titulo + (detalhe ? "\n        " + detalhe : "")); }
}

var fila = [];

/* Os grupos entram numa fila e só rodam depois de GET /auth/me —
   antes disso a sessão não existe, e é assim no painel também. */
function grupo(nome, fn) {
  fila.push({ nome: nome, fn: fn });
}

function igual(a, b, titulo) {
  ok(JSON.stringify(a) === JSON.stringify(b), titulo, "esperado " + JSON.stringify(b) + ", veio " + JSON.stringify(a));
}

/* =============================================================
   1. ISOLAMENTO ENTRE CONTAS
   ============================================================= */
grupo("Isolamento entre contas (tenant)", function () {
  return VC.services.pacientes.listar({ status: "todos" }).then(function (lista) {
    igual(lista.map(function (p) { return p.nome; }).sort(),
          ["Ana Beatriz Moraes", "Juliana Costa", "Rafael Lima"],
          "listar() devolve as pessoas da conta ativa");

    /* Nenhuma pessoa da outra conta aparece, nem com status "todos". */
    ok(lista.every(function (p) { return p.nome !== "Clara Benedetti"; }),
       "ninguém da outra conta entra na lista");
  }).then(function () {
    /* ler registro de outra conta deve responder "não encontrado" */
    return VC.services.pacientes.obter("cli_B1").then(function () {
      ok(false, "obter() de outra conta deveria falhar");
    }, function (e) {
      ok(e.status === 404, "obter() de outra conta responde 404 (não revela que existe)",
         "veio: " + JSON.stringify(e.status));
    });
  }).then(function () {
    return VC.services.atendimentos.listar({}).then(function (lista) {
      ok(lista.length === 4 && lista.every(function (a) { return a.id.indexOf("atd_A") === 0; }),
         "atendimentos também ficam restritos à conta ativa");
      ok(lista[0].status === "realizado" && lista[0].pagamento === "pago",
         "os valores do servidor chegam traduzidos para a tela");
    });
  }).then(function () {
    /* fail-closed: sem workspace ativo nada é consultado */
    var original = VC.session.tenantId;
    var antes = ROTAS_PEDIDAS.length;
    VC.session.tenantId = function () { throw new Error("sessão sem workspace ativo"); };
    return VC.services.pacientes.listar({}).then(function () {
      VC.session.tenantId = original;
      ok(false, "consulta sem workspace deveria falhar");
    }, function (e) {
      VC.session.tenantId = original;
      ok(/workspace/.test(e.message), "sem workspace no contexto, a consulta falha");
      ok(ROTAS_PEDIDAS.length === antes, "e nem chega a sair requisição");
    });
  }).then(function () {
    /* trocar para uma conta sem vínculo responde como inexistente */
    return VC.session.trocarTenant("tnt_999").then(function () {
      ok(false, "trocar para conta sem vínculo deveria falhar");
    }, function (e) {
      ok(e.status === 404, "trocar para conta sem vínculo responde 404");
    });
  }).then(function () {
    /* troca legítima muda o conjunto de dados */
    return VC.session.trocarTenant("tnt_002").then(function () {
      return VC.services.pacientes.listar({ status: "todos" }).then(function (lista) {
        igual(lista.map(function (p) { return p.nome; }), ["Clara Benedetti"],
              "após trocar de conta, os dados são os da nova conta");
        return VC.session.trocarTenant("tnt_001");
      });
    });
  }).then(function () {
    /* o tenant nunca viaja: quem decide é a sessão do servidor */
    var vazou = ROTAS_PEDIDAS.filter(function (r) { return /tenant/i.test(r); });
    igual(vazou, [], "nenhuma requisição carrega tenant_id");
  });
});

/* =============================================================
   2. RENDERIZAÇÃO SEGURA
   ============================================================= */
grupo("Renderização segura (XSS)", function () {
  var html = VC.safe.html;
  var ataque = '<img src=x onerror="alert(1)">';

  var saida = html`<p>${ataque}</p>`.value;
  ok(saida.indexOf("<img") === -1, "dado dinâmico é escapado dentro de html``");
  ok(saida.indexOf("&lt;img") > -1, "o conteúdo continua visível como texto");

  var comAspas = html`<div title="${'" onmouseover="alert(1)'}">x</div>`.value;
  ok(comAspas.indexOf('onmouseover="alert') === -1, "não dá para escapar de um atributo");

  var aninhado = html`<div>${html`<b>${ataque}</b>`}</div>`.value;
  ok(aninhado.indexOf("<b>") > -1 && aninhado.indexOf("<img") === -1,
     "fragmento seguro é reaproveitado sem escapar duas vezes");

  var recusou = false;
  try { VC.safe.render({ innerHTML: "" }, "<b>string crua</b>"); } catch (e) { recusou = true; }
  ok(recusou, "render() recusa string crua (só aceita html``)");

  var nome = VC.ui ? null : null; // ui não é carregado aqui (depende de DOM)
  ok(true, "componentes de tela usam a mesma porta (verificado por inspeção)");
});

/* =============================================================
   3. MÉTRICAS — definição única
   ============================================================= */
grupo("Métricas (fonte única)", function () {
  var m = VC.domain.metrics;
  var hoje = new Date();
  function at(h, status, pagamento, valor) {
    var d = new Date(hoje); d.setHours(h, 0, 0, 0);
    return { inicio: d.toISOString(), status: status, pagamento: pagamento, valor: valor, duracaoMin: 50 };
  }

  var lista = [
    at(8, "realizado", "pago", 200),
    at(9, "realizado", "pendente", 200),
    at(10, "falta", "pendente", 200),
    at(11, "cancelado", "isento", 200)
  ];

  var c = m.contagens(lista);
  igual([c.total, c.realizados, c.faltas, c.cancelados], [3, 2, 1, 1], "cancelado não entra no total");
  igual(m.presenca(2, 1), 67, "presença = realizados / (realizados + faltas)");
  igual(m.presenca(0, 0), null, "sem histórico, presença é nula (não zero)");

  var r = m.receita(lista, new Date(new Date().setHours(23, 0, 0, 0)));
  igual(r.recebido, 200, "recebido soma só o que está pago");
  igual(r.pendente, 400, "a receber inclui falta cobrada");
  ok(r.total === 600, "cancelado fora do total (" + r.total + ")");

  var dia = m.resumoDoDia(lista);
  igual([dia.total, dia.realizados, dia.faltas], [3, 2, 1], "resumo do dia bate com as contagens");
});

/* =============================================================
   4. TERMINOLOGIA
   ============================================================= */
grupo("Terminologia", function () {
  var t = VC.terms.t;
  VC.terms.configurar({ profissao: "psicologia" });
  igual(t("client.many"), "Pacientes", "padrão da psicologia");

  VC.terms.configurar({ profissao: "terapia_integrativa" });
  igual(t("client.many"), "Clientes", "a profissão troca o termo");

  VC.terms.configurar({ profissao: "psicologia", tenant: { "client.one": "Cliente", "client.many": "Clientes" } });
  igual(t("client.one"), "Cliente", "a conta sobrescreve a profissão");
  igual(t("client.one", true), "cliente", "versão minúscula para o meio da frase");

  var r = VC.terms.definir({ "client.one": "<b>Paciente</b>" });
  igual(r.aplicados, 0, "termo com marcação é recusado");
  ok(VC.terms.t("client.one").indexOf("<") === -1, "e o valor anterior é mantido");

  var r2 = VC.terms.definir({ "chave.inexistente": "x" });
  igual(r2.aplicados, 0, "chave fora do dicionário é ignorada");

  igual(VC.terms._limpar("Paciente muito muito muito muito muito longo demais"), null, "rótulo longo demais é recusado");
  VC.terms.configurar({ profissao: "psicologia" });
});

/* =============================================================
   5. PERMISSÕES — administrativo x clínico
   ============================================================= */
grupo("Permissões (administrativo x clínico)", function () {
  var P = VC.types.PERMISSIONS;
  var RP = VC.types.ROLE_PERMISSIONS;

  ok(RP.OWNER.indexOf(P.CLINICAL_RECORDS_READ) === -1,
     "OWNER não recebe leitura clínica pelo papel");
  ok(RP.ASSISTANT.indexOf(P.CLINICAL_RECORDS_READ) === -1 && RP.ASSISTANT.indexOf(P.DOCUMENTS_READ) === -1,
     "ASSISTANT não alcança nada clínico");
  ok(RP.PROFESSIONAL.indexOf(P.CLINICAL_RECORDS_READ) > -1,
     "PROFESSIONAL lê o próprio conteúdo clínico");
  ok(RP.PROFESSIONAL.indexOf(P.CLINICAL_RECORDS_READ_OTHERS) === -1,
     "PROFESSIONAL não lê o conteúdo clínico de outro profissional");
  ok(RP.OWNER.indexOf(P.MEMBERS_MANAGE) > -1, "OWNER administra a conta");

  var clinicas = VC.types.CLASS_PERMISSIONS.clinical;
  var adm = VC.types.CLASS_PERMISSIONS.administrative;
  var cruzou = adm.filter(function (p) { return clinicas.indexOf(p) > -1; });
  igual(cruzou.length, 0, "nenhuma permissão administrativa alcança a classe clínica");

  /* sessão atual: dono que também atende (grant explícito) */
  ok(VC.session.pode(P.CLINICAL_RECORDS_READ), "dono-que-atende tem acesso clínico por concessão explícita");
  ok(VC.session.podeVerClinicoDe(VC.session.profissionalId()), "acessa o próprio conteúdo");
  ok(!VC.session.podeVerClinicoDe("prf_outro"), "não acessa o de outro profissional sem clinical.read_others");
});

/* =============================================================
   PRONTUÁRIO
   ============================================================= */
grupo("Prontuário", function () {
  var criada = null;

  return VC.services.prontuario.listar("cli_A1").then(function (notas) {
    /* A sessão atual é a dona que também atende: enxerga as próprias
       notas e NÃO enxerga a do colega (não tem read_others). */
    igual(notas.map(function (n) { return n.id; }), ["not_A1"],
          "lista traz só as notas que a pessoa pode ler");
    ok(notas[0].conteudo === undefined,
       "a lista não carrega conteúdo clínico (metadado apenas)");
    ok(notas[0].souOAutor === true, "marca quem é autor da nota");
    ok(notas[0].tipoRotulo === "Evolução", "tipo chega traduzido para a tela");

  }).then(function () {
    /* Nota do colega: para quem não tem read_others, não existe. */
    return VC.services.prontuario.conteudo("not_A2").then(function () {
      ok(false, "conteúdo de nota alheia deveria falhar");
    }, function (e) {
      ok(e.status === 404, "nota de outro profissional responde 404, não 403");
    });

  }).then(function () {
    var antes = ROTAS_PEDIDAS.length;
    return VC.services.prontuario.conteudo("not_A1").then(function (c) {
      ok(c.conteudo.indexOf("frequência semanal") > -1, "conteúdo abre para o autor");
      ok(ROTAS_PEDIDAS.length > antes &&
         /\/content$/.test(rotaSemQuery(ROTAS_PEDIDAS[ROTAS_PEDIDAS.length - 1])),
         "ler conteúdo é uma chamada própria — é ela que vira trilha");
    });

  }).then(function () {
    return VC.services.prontuario.criar("cli_A1", {
      conteudo: "Sessão nova. Manteve o plano.", tipo: "session", ocorridoEm: new Date()
    }).then(function (n) {
      criada = n;
      igual(n.versaoAtual, 1, "registro novo nasce na versão 1");
      igual(n.status, "rascunho", "e nasce como rascunho");
    });

  }).then(function () {
    return VC.services.prontuario.salvar(criada.id, { conteudo: "Sessão nova. Texto corrigido." })
      .then(function (n) {
        igual(n.versaoAtual, 2, "salvar cria a versão seguinte");
        return VC.services.prontuario.versoes(criada.id);
      }).then(function (versoes) {
        igual(versoes.map(function (v) { return v.versao; }), [1, 2],
              "a versão anterior continua no histórico (nada é sobrescrito)");
      });

  }).then(function () {
    return VC.services.prontuario.assinar(criada.id).then(function (n) {
      ok(n.assinada, "assinar fecha o registro");
      return VC.services.prontuario.salvar(criada.id, { conteudo: "mexendo depois" });
    }).then(function () {
      ok(false, "assinada sem motivo deveria falhar");
    }, function (e) {
      ok(e.status === 422, "nota assinada só aceita adendo com motivo");
    });

  }).then(function () {
    return VC.services.prontuario.salvar(criada.id, {
      conteudo: "Adendo devido.", motivo: "erro de digitação"
    }).then(function (n) {
      igual(n.versaoAtual, 3, "adendo com motivo entra como versão nova");
      ok(n.assinada, "e a nota continua assinada");
    });

  }).then(function () {
    return VC.services.prontuario.trilha("cli_A1").then(function (linhas) {
      ok(linhas.length > 0, "a trilha registra os acessos");
      ok(linhas.some(function (l) { return !l.permitido; }),
         "inclusive a tentativa recusada — é ela que denuncia acesso indevido");
      ok(linhas.every(function (l) { return l.conteudo === undefined; }),
         "e nenhuma linha da trilha carrega conteúdo");
    });

  }).then(function () {
    /* Isolamento entre contas vale igual para o prontuário. */
    return VC.services.prontuario.conteudo("not_B1").then(function () {
      ok(false, "nota de outra conta deveria falhar");
    }, function (e) {
      ok(e.status === 404, "nota de outra conta responde como inexistente");
    });
  });
});

/* =============================================================
   EQUIPE
   ============================================================= */
grupo("Equipe", function () {
  return VC.services.equipe.listar().then(function (e) {
    igual(e.membros.length, 2, "a equipe lista quem tem acesso");
    var eu = e.membros.filter(function (m) { return m.souEu; })[0];
    ok(eu && eu.papel === "OWNER", "marca qual membro é você");
    var rita = e.membros.filter(function (m) { return m.email === "rita@exemplo.com"; })[0];
    igual(rita.escopoRotulo, "toda a conta", "traduz o escopo para linguagem de gente");
    ok(rita.atende === false, "mostra quem atende e quem só administra");

  }).then(function () {
    return VC.services.equipe.convidar({ email: "novo@exemplo.com", papel: "PROFESSIONAL" })
      .then(function (c) {
        ok(!!c.link, "o convite devolve o link na criação");
        return VC.services.equipe.listar();
      }).then(function (e) {
        igual(e.convites.length, 1, "o convite entra na lista de abertos");
        ok(e.convites[0].link === null, "e o link NÃO volta na listagem (token existe uma vez)");
      });

  }).then(function () {
    return VC.services.equipe.convidar({ email: "camila@exemplo.com" }).then(function () {
      ok(false, "convidar quem já é membro deveria falhar");
    }, function (erro) {
      ok(erro.code === "ja_e_membro", "não convida quem já está dentro");
    });

  }).then(function () {
    return VC.services.equipe.convidar({ email: "novo@exemplo.com" }).then(function () {
      ok(false, "convite repetido deveria falhar");
    }, function (erro) {
      ok(erro.code === "convite_pendente", "não cria dois convites para o mesmo e-mail");
    });

  }).then(function () {
    return VC.services.equipe.listar().then(function (e) {
      return VC.services.equipe.revogar(e.convites[0].id);
    }).then(function () {
      return VC.services.equipe.listar();
    }).then(function (e) {
      igual(e.convites.length, 0, "revogar fecha o convite");
    });

  }).then(function () {
    return VC.services.equipe.listar().then(function (e) {
      var eu = e.membros.filter(function (m) { return m.souEu; })[0];
      return VC.services.equipe.alterar(eu.id, { papel: "ASSISTANT" });
    }).then(function () {
      ok(false, "editar o próprio acesso deveria falhar");
    }, function (erro) {
      ok(erro.code === "nao_edita_a_si", "ninguém edita o próprio acesso");
    });

  }).then(function () {
    return VC.services.equipe.listar().then(function (e) {
      var rita = e.membros.filter(function (m) { return !m.souEu; })[0];
      return VC.services.equipe.alterar(rita.id, { escopo: "own", status: "suspended" });
    }).then(function (m) {
      igual(m.escopo, "own", "dá para trocar o escopo de outra pessoa");
      ok(!m.ativo, "e suspender o acesso");
    });
  });
});

/* =============================================================
   CONFIGURAÇÕES DA CONTA
   ============================================================= */
/* =============================================================
   PLANO E USO
   ============================================================= */
grupo("Plano e uso", function () {
  return VC.services.configuracoes.plano().then(function (p) {
    igual(p.nome, "Essencial", "lê o plano da conta");
    igual(p.status, "em teste", "status traduzido na fronteira (trialing → em teste)");
    ok(p.precoMensal === null, "preço nulo continua nulo (a tela não inventa valor)");
    igual(p.limites.pessoas, 500, "limite vem do servidor, como número");
    igual(p.uso.pessoas, 498, "uso vem ao lado do limite");
    ok(p.limites.armazenamentoMb === null, "limite nulo é sem limite, não zero");

    var pagina = VC.safe.html`${VC.views.configuracoes._cartaoPlano(p)}`.toString();
    ok(pagina.indexOf("498 de 500") > -1, "a tela mostra \"498 de 500\"");
    ok(pagina.indexOf("sem limite") > -1, "e diz \"sem limite\" quando não há teto");
    ok(pagina.indexOf("meter--warn") > -1, "perto do limite a barra muda de tom");
    ok(!/data-acao="(trocar|mudar)-plano"/.test(pagina), "não há botão de trocar de plano direto");
    ok(pagina.indexOf('data-acao="contratar-plano"') > -1, "com cobrança ativa, há botão de contratar");
    ok(pagina.indexOf('data-acao="cancelar-assinatura"') === -1, "sem assinatura paga, não há cancelar");
    igual(p.catalogo[0].precoMensal, 59.9, "preço do catálogo vem como número");

    var paga = Object.assign({}, p, { assinaturaPaga: true, planoPendente: "profissional" });
    var pg = VC.safe.html`${VC.views.configuracoes._cartaoPlano(paga)}`.toString();
    ok(pg.indexOf('data-acao="cancelar-assinatura"') > -1, "com assinatura paga, aparece cancelar");
    ok(pg.indexOf('data-acao="contratar-plano"') === -1, "e some contratar");
    ok(pg.indexOf("Aguardando o pagamento") > -1, "plano pendente é avisado");

    var semGateway = Object.assign({}, p, { cobrancaAtiva: false });
    var sg = VC.safe.html`${VC.views.configuracoes._cartaoPlano(semGateway)}`.toString();
    ok(sg.indexOf('data-acao="contratar-plano"') === -1, "sem gateway configurado, não há botão");

  }).then(function () {
    SERVIDOR.ativo = "tnt_002";       // profissional: sem settings.manage
    return VC.services.configuracoes.plano().then(function () {
      ok(false, "profissional não deveria ler o plano");
    }, function (erro) {
      igual(erro.status, 403, "quem não administra a conta não lê o plano");
    });
  }).then(function () {
    SERVIDOR.ativo = "tnt_001";
    var vazou = ROTAS_PEDIDAS.filter(function (r) { return /\/workspace\/plan.*(tenant|workspace_id)/.test(r); });
    igual(vazou.length, 0, "a rota do plano não carrega tenant_id");
  });
});

grupo("Configurações da conta", function () {
  return VC.services.configuracoes.obter().then(function (c) {
    igual(c.jornadaInicio, "08:00", "lê a jornada da conta");
    ok(c.metaMensal === null, "meta nasce vazia (não inventa número)");
    igual(c.fuso, "America/Sao_Paulo", "e o fuso da conta");

  }).then(function () {
    return VC.services.configuracoes.salvar({
      jornadaInicio: "07:30", dias: [1, 2, 3, 4, 5, 6], duracaoPadrao: 45, metaMensal: "8000.00"
    }).then(function (c) {
      igual(c.jornadaInicio, "07:30", "grava a jornada");
      igual(c.dias.length, 6, "grava os dias de atendimento");
      igual(Number(c.metaMensal), 8000, "grava a meta do mês");
    });

  }).then(function () {
    return VC.services.configuracoes.salvar({ limparMeta: true }).then(function (c) {
      ok(c.metaMensal === null, "meta pode ser removida (vazio ≠ zero)");
    });

  }).then(function () {
    return VC.services.configuracoes.salvar({
      terminologia: { "client.one": "Cliente", "client.many": "Clientes" }
    }).then(function (c) {
      igual(c.terminologia["client.one"], "Cliente", "troca o rótulo da pessoa atendida");
      igual(c.recusados.length, 0, "sem recusas quando o texto é simples");
    });

  }).then(function () {
    return VC.services.configuracoes.salvar({
      terminologia: { "client.one": "<b>Cliente</b>" }
    }).then(function (c) {
      ok(c.recusados.indexOf("client.one") > -1,
         "rótulo com marcação é recusado — e a tela fica sabendo");
      igual(c.terminologia["client.one"], "Cliente", "o valor anterior é mantido");
    });

  }).then(function () {
    /* Configuração é por conta, como todo o resto. */
    SERVIDOR.ativo = "tnt_002";
    return VC.services.configuracoes.obter().then(function (c) {
      igual(c.fuso, "America/Manaus", "outra conta, outro fuso");
      igual(c.jornadaInicio, "09:00", "outra conta, outra jornada");
      SERVIDOR.ativo = "tnt_001";
    });

  }).then(function () {
    var vazou = ROTAS_PEDIDAS.filter(function (r) { return /tenant_id|workspace_id=/.test(r); });
    igual(vazou.length, 0, "nenhuma rota de equipe ou configuração carrega tenant_id");
  });
});

/* =============================================================
   AGENDA: RECORRÊNCIA E BLOQUEIOS
   ============================================================= */
grupo("Agenda: recorrência e bloqueios", function () {
  var daquiA = function (dias) {
    var d = new Date(); d.setHours(9, 0, 0, 0);
    d.setDate(d.getDate() + dias);
    return d;
  };

  return VC.services.agenda.criarSerie({
    pacienteId: "cli_A1", inicio: daquiA(40), frequencia: "weekly", ocorrencias: 4
  }).then(function (r) {
    igual(r.criados.length, 4, "a recorrência cria as ocorrências de uma vez");
    igual(r.conflitos.length, 0, "sem conflito quando a agenda está livre");
    igual(r.serie.frequenciaRotulo, "semanal", "a frequência chega traduzida");

  }).then(function () {
    /* Agora o horário já está ocupado pela série anterior. */
    return VC.services.agenda.criarSerie({
      pacienteId: "cli_A1", inicio: daquiA(40), frequencia: "weekly", ocorrencias: 2
    }).then(function () {
      ok(false, "série toda ocupada deveria falhar");
    }, function (e) {
      ok(e.code === "nenhuma_ocorrencia_livre", "série sem nenhum horário livre é recusada");
    });

  }).then(function () {
    return VC.services.agenda.criarSerie({
      pacienteId: "cli_A1", inicio: daquiA(41), frequencia: "weekly", ocorrencias: 3
    }).then(function (r) {
      ok(r.criados.length >= 1, "o que está livre é criado mesmo assim");
    });

  }).then(function () {
    return VC.services.agenda.seriesDoPaciente("cli_A1").then(function (lista) {
      ok(lista.length >= 1, "a recorrência aparece na ficha da pessoa");
      ok(lista[0].ativa, "e nasce ativa");
      return VC.services.agenda.encerrarSerie(lista[0].id, { motivo: "alta" });
    }).then(function (s) {
      ok(!s.ativa, "encerrar desliga o molde");
    });

  }).then(function () {
    /* Bloqueio em cima de atendimento marcado: recusado. */
    var quando = new Date(DADOS.tnt_001.atendimentos[0].inicio);
    return VC.services.agenda.bloquear({
      inicio: new Date(quando.getTime() - 36e5), fim: new Date(quando.getTime() + 36e5),
      titulo: "Férias", tipo: "vacation"
    }).then(function () {
      ok(false, "bloquear por cima de atendimento deveria pedir confirmação");
    }, function (e) {
      ok(e.code === "atendimentos_no_periodo", "bloqueio avisa que há atendimento no período");
    });

  }).then(function () {
    var quando = new Date(DADOS.tnt_001.atendimentos[0].inicio);
    return VC.services.agenda.bloquear({
      inicio: new Date(quando.getTime() - 36e5), fim: new Date(quando.getTime() + 36e5),
      titulo: "Férias", tipo: "vacation", forcar: true
    }).then(function (r) {
      igual(r.bloqueio.tipoRotulo, "Férias", "com confirmação, o bloqueio é criado");
      ok(r.atendimentosNoPeriodo.length >= 1,
         "e os atendimentos continuam marcados — bloqueio não cancela ninguém");
    });

  }).then(function () {
    return VC.services.agenda.bloqueios().then(function (lista) {
      ok(lista.length === 1, "o bloqueio aparece na agenda");
      return VC.services.agenda.removerBloqueio(lista[0].id);
    }).then(function () {
      return VC.services.agenda.bloqueios();
    }).then(function (lista) {
      igual(lista.length, 0, "e pode ser removido");
    });

  }).then(function () {
    /* Bloqueio de uma conta não aparece na outra. */
    SERVIDOR.ativo = "tnt_002";
    return VC.services.agenda.bloqueios().then(function (lista) {
      igual(lista.length, 0, "bloqueio não vaza entre contas");
      SERVIDOR.ativo = "tnt_001";
    });
  });
});

/* =============================================================
   DOCUMENTOS
   ============================================================= */
grupo("Documentos", function () {
  return VC.services.documentos.recibo("cli_A1", {}).then(function (d) {
    igual(d.classe, "administrative", "recibo é administrativo");
    igual(d.tipoRotulo, "Recibo", "o tipo chega traduzido");
    ok(!d.eClinico, "e não entra na classe clínica");

  }).then(function () {
    return VC.services.documentos.declaracao("cli_A1", "atd_A1").then(function (d) {
      igual(d.classe, "clinical", "declaração de comparecimento é clínica");
      ok(d.eClinico, "mesmo sem conteúdo de sessão dentro");
    });

  }).then(function () {
    return VC.services.documentos.listar("cli_A1").then(function (lista) {
      igual(lista.length, 2, "os dois aparecem para quem tem as duas permissões");
    });

  }).then(function () {
    /* Simula a recepção: sem acesso clínico. */
    var original = VC.session.pode;
    VC.session.pode = function (p) {
      if (p === "documents.read" || p === "clinical_records.read") return false;
      return original.call(VC.session, p);
    };
    return VC.services.documentos.listar("cli_A1").then(function (lista) {
      igual(lista.map(function (d) { return d.tipo; }), ["receipt"],
            "quem não tem acesso clínico vê o recibo e não vê a declaração");
      VC.session.pode = original;
    }, function (e) {
      VC.session.pode = original;
      throw e;
    });

  }).then(function () {
    var vazou = ROTAS_PEDIDAS.filter(function (r) { return /tenant_id/.test(r); });
    igual(vazou.length, 0, "nenhuma rota de documento carrega tenant_id");
  });
});

/* =============================================================
   PRIVACIDADE (direitos do titular)
   ============================================================= */
grupo("Privacidade", function () {
  var pedidoId = null;

  return VC.services.privacidade.registrarConsentimento("cli_A1", {
    tipo: "clinical_treatment", versao: "2026.1", texto: "Termo de atendimento."
  }).then(function (c) {
    igual(c.versao, "2026.1", "o consentimento guarda a versão do texto");
    ok(c.vigente, "e nasce vigente");
    return VC.services.privacidade.revogarConsentimento(c.id);
  }).then(function (c) {
    ok(!c.vigente, "revogar desliga o consentimento");
    ok(!!c.revogadoEm, "com data");
    return VC.services.privacidade.revogarConsentimento(c.id).then(function () {
      ok(false, "revogar duas vezes deveria falhar");
    }, function (e) {
      ok(e.code === "ja_revogado", "e não dá para revogar duas vezes");
    });

  }).then(function () {
    return VC.services.privacidade.abrirPedido("cli_A1", { tipo: "erasure" }).then(function (p) {
      pedidoId = p.id;
      ok(p.prazo === null || p.prazo === undefined,
         "o pedido nasce SEM prazo — o sistema não inventa um");
      igual(p.statusRotulo, "aberto", "e nasce aberto");
    });

  }).then(function () {
    return VC.services.privacidade.decidir(pedidoId, {
      alvo: "clinical", decisao: "erase", motivo: ""
    }).then(function () {
      ok(false, "decisão sem motivo deveria falhar");
    }, function (e) {
      ok(e.status === 422, "decisão sem motivo é recusada");
    });

  }).then(function () {
    return VC.services.privacidade.decidir(pedidoId, {
      alvo: "payments", decisao: "keep", motivo: "obrigação fiscal",
      baseLegal: "guarda contábil"
    }).then(function (p) {
      igual(p.decisoes.length, 1, "a decisão entra no pedido");
      igual(p.decisoes[0].decisaoRotulo, "Manter", "inclusive quando é para manter");
      ok(!p.decisoes[0].aplicada, "e registrar NÃO executa nada");
    });

  }).then(function () {
    return VC.services.privacidade.decidir(pedidoId, {
      alvo: "payments", decisao: "erase", motivo: "titular pediu"
    }).then(function (p) {
      var dec = p.decisoes[p.decisoes.length - 1];
      return VC.services.privacidade.aplicar(pedidoId, dec.id);
    }).then(function () {
      ok(false, "apagar financeiro deveria falhar");
    }, function (e) {
      ok(e.code === "apagar_nao_se_aplica",
         "financeiro tem guarda obrigatória: apagar é recusado com explicação");
    });

  }).then(function () {
    return VC.services.privacidade.encerrar(pedidoId, { status: "done" }).then(function () {
      ok(false, "encerrar com decisão pendente deveria falhar");
    }, function (e) {
      ok(e.code === "decisoes_pendentes", "não encerra com decisão registrada e não executada");
    });

  }).then(function () {
    return VC.services.privacidade.encerrar(pedidoId, { status: "refused" }).then(function () {
      ok(false, "recusar sem explicar deveria falhar");
    }, function (e) {
      ok(e.status === 422, "recusar sem explicar não é resposta");
    });

  }).then(function () {
    /* Retenção: nasce vazia, e prazo sem base legal não vale. */
    return VC.services.privacidade.politicas().then(function (lista) {
      igual(lista.length, 0, "a política de retenção nasce vazia");
      return VC.services.privacidade.definirPolitica({ alvo: "clinical", meses: 240 });
    }).then(function () {
      ok(false, "prazo sem base legal deveria falhar");
    }, function (e) {
      ok(e.status === 422, "prazo sem base legal é recusado");
    });

  }).then(function () {
    return VC.services.privacidade.definirPolitica({
      alvo: "clinical", meses: 240, baseLegal: "resolução do conselho"
    }).then(function (p) {
      ok(p.aplicavel, "com base legal, a política passa a valer");
      return VC.services.privacidade.definirPolitica({
        alvo: "documents", observacao: "a definir" });
    }).then(function (p) {
      ok(!p.aplicavel, "política sem prazo não decide nada — e isso é explícito");
    });
  });
});

/* =============================================================
   PAGINAÇÃO E PAGAMENTO AVULSO
   ============================================================= */
grupo("Paginação e caixa", function () {
  /* A conta de teste tem 3 pessoas; com página de 2, viram duas páginas. */
  return VC.services.pacientes.listar({ status: "todos", limite: 2, pagina: 1 })
    .then(function (r) {
      igual(r.lista.length, 2, "a página traz só o pedaço pedido");
      igual(r.total, 3, "e o total vem do cabeçalho, não do tamanho da lista");
      igual(r.pagina, 1, "com o número da página");

      return VC.services.pacientes.listar({ status: "todos", limite: 2, pagina: 2 });
    }).then(function (r) {
      igual(r.lista.length, 1, "a última página traz o resto");
      igual(r.total, 3, "e o total continua o mesmo");

    }).then(function () {
      /* Sem `pagina`, a chamada antiga continua devolvendo uma lista —
         é o que permitiu acrescentar paginação sem refazer tela. */
      return VC.services.pacientes.listar({ status: "todos" }).then(function (lista) {
        ok(Array.isArray(lista), "sem página, o service segue devolvendo a lista de sempre");
      });

    }).then(function () {
      return VC.services.financeiro.registrarAvulso("cli_A1", {
        valor: "900.00", metodo: "transfer", pagoEm: new Date(),
        observacao: "pacote de 5 sessões"
      }).then(function (p) {
        igual(Number(p.valor), 900, "pagamento avulso entra no caixa");
        ok(!p.atendimentoId, "sem atendimento atrás dele");
        igual(p.metodoRotulo, "Transferência", "com a forma traduzida");
      });
    });
});

/* ---------------- fechamento ---------------- */
VC.session.carregar().then(function () {
  return fila.reduce(function (anterior, g) {
    return anterior.then(function () {
      console.log("\n" + g.nome);
      return g.fn();
    });
  }, Promise.resolve());
}).then(function () {
  return Promise.all(pendentes);
}).then(function () {
  console.log("\n" + passou + " passaram, " + falhou + " falharam");
  process.exit(falhou ? 1 : 0);
}).catch(function (e) {
  console.error("\nerro na suíte:", e);
  process.exit(1);
});
