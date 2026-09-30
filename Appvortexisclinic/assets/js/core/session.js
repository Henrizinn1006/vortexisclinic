/* =============================================================
   SESSÃO — usuário, vínculos e workspace ativo
   -------------------------------------------------------------
   Agora é de verdade: tudo aqui vem de `GET /auth/me`. O painel
   não inventa nem guarda identidade — ele pergunta ao servidor e
   desenha o que a resposta permitir.

   Regras que este arquivo respeita, e que o servidor REPETE
   (porque o front não decide nada):

   1. o workspace ativo nunca é escolhido pelo cliente: trocar é
      `POST /session/workspace`, e o servidor confirma se existe
      membership ativa antes de mudar a sessão dele;
   2. sem workspace válido, operação de dados falha (fail-closed);
   3. workspace que não é seu responde como inexistente (404), não
      como "sem permissão" — 403 já confirmaria que existe;
   4. permissão daqui serve para ESCONDER interface. Quem autoriza
      é o servidor, em toda requisição.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var P = VC.types.PERMISSIONS;

  /* Estado da sessão. Só é escrito pelas respostas do servidor. */
  var estado = {
    autenticado: false,
    usuario: null,          // { id, nome, email, emailVerificado }
    workspaceAtivo: null,   // { id, nome, slug, tipo, papel, papelNome, escopo }
    workspaces: [],
    permissoes: [],
    perfil: null            // { id, nomeExibicao, profissao, conselho, registro }
  };

  var ouvintes = [];

  /* ---------- Tradução da resposta ---------- */
  function aplicar(resposta) {
    estado.autenticado = true;
    estado.usuario = {
      id: resposta.usuario.id,
      nome: resposta.usuario.nome,
      email: resposta.usuario.email,
      emailVerificado: !!resposta.usuario.email_verificado
    };
    estado.workspaceAtivo = resposta.workspace_ativo
      ? converterWorkspace(resposta.workspace_ativo) : null;
    estado.workspaces = (resposta.workspaces || []).map(converterWorkspace);
    estado.permissoes = resposta.permissoes || [];
    estado.perfil = resposta.perfil ? {
      id: resposta.perfil.id,
      nomeExibicao: resposta.perfil.nome_exibicao,
      profissao: resposta.perfil.profissao,
      conselho: resposta.perfil.conselho,
      registro: resposta.perfil.registro
    } : null;
    aplicarContexto();
    return estado;
  }

  function converterWorkspace(w) {
    return {
      id: w.id, nome: w.nome, slug: w.slug, tipo: w.tipo,
      papel: w.papel, papelNome: w.papel_nome, escopo: w.escopo, ativo: !!w.ativo
    };
  }

  function limpar() {
    estado = {
      autenticado: false, usuario: null, workspaceAtivo: null,
      workspaces: [], permissoes: [], perfil: null
    };
  }

  /* ---------- Leitura ---------- */
  function tenantId() {
    /* fail-closed: sem workspace ativo não existe contexto de dados.
       Lançar aqui é o que impede uma tela pedir "tudo" sem querer. */
    if (!estado.workspaceAtivo) throw new Error("sessão sem workspace ativo");
    return estado.workspaceAtivo.id;
  }

  function pode(permissao) {
    return estado.permissoes.indexOf(permissao) > -1;
  }

  /* Conteúdo clínico de OUTRO profissional exige permissão própria,
     nunca o papel. Dono da conta não entra aqui por ser dono. */
  function podeVerClinicoDe(professionalId) {
    if (!pode(P.CLINICAL_RECORDS_READ)) return false;
    if (estado.perfil && estado.perfil.id === professionalId) return true;
    return pode(P.CLINICAL_RECORDS_READ_OTHERS);
  }

  function escopo() {
    return estado.workspaceAtivo ? estado.workspaceAtivo.escopo : null;
  }

  function workspaces() {
    return estado.workspaces.map(function (w) {
      return {
        tenantId: w.id, nome: w.nome, tipo: w.tipo, papel: w.papel,
        papelNome: w.papelNome,
        ativo: !!(estado.workspaceAtivo && estado.workspaceAtivo.id === w.id)
      };
    });
  }

  /* Terminologia e cor seguem a profissão do workspace ativo. */
  function aplicarContexto() {
    var profissao = (estado.perfil && estado.perfil.profissao) || "psicologia";
    VC.terms.configurar({ profissao: profissao });
    if (document.documentElement) {
      document.documentElement.setAttribute("data-vertical", profissao);
    }
  }

  /* ---------- Conversas com o servidor ---------- */
  function carregar() {
    return VC.api.get("/auth/me").then(aplicar, function (e) {
      limpar();
      if (e.status === 401) return estado;      // ainda não entrou: normal
      throw e;
    });
  }

  function entrar(email, senha) {
    return VC.api.post("/auth/login", { email: email, senha: senha }).then(aplicar);
  }

  function cadastrar(dados) {
    return VC.api.post("/auth/register", dados).then(aplicar);
  }

  function criarWorkspace(dados) {
    return VC.api.post("/workspaces", dados).then(aplicar);
  }

  /* A troca é decidida pelo servidor. O id vai junto só para ele
     PROCURAR a membership — se não achar, responde 404. */
  function trocarTenant(workspaceId) {
    return VC.api.post("/session/workspace", { workspace_id: workspaceId })
      .then(function (r) {
        aplicar(r);
        ouvintes.forEach(function (fn) { fn(estado.workspaceAtivo); });
        return estado.workspaceAtivo;
      });
  }

  /* Sair não é só apagar o cookie: o que este navegador guardou
     enquanto a sessão existia sai junto. */
  function limparRastros() {
    try {
      if (global.navigator && navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({ tipo: "limpar-cache" });
      }
      if (global.caches && caches.keys) {
        caches.keys().then(function (chaves) {
          chaves.forEach(function (k) { caches.delete(k); });
        });
      }
      if (global.sessionStorage) sessionStorage.clear();
    } catch (e) {
      /* Navegador sem suporte ou modo restrito: seguir mesmo assim. */
    }
  }

  function encerrar() {
    function terminar() {
      limpar();
      limparRastros();
      global.location.reload();
    }
    /* Mesmo se a chamada falhar, a sessão local não continua de pé. */
    return VC.api.post("/auth/logout").then(terminar, terminar);
  }

  function aoTrocarTenant(fn) { ouvintes.push(fn); }

  VC.session = {
    /* ciclo */
    carregar: carregar,
    entrar: entrar,
    cadastrar: cadastrar,
    criarWorkspace: criarWorkspace,
    encerrar: encerrar,

    /* leitura */
    estado: function () { return estado; },
    autenticado: function () { return estado.autenticado; },
    temWorkspace: function () { return !!estado.workspaceAtivo; },
    usuario: function () { return estado.usuario; },
    tenantId: tenantId,
    tenant: function () { return estado.workspaceAtivo; },
    membership: function () {
      var w = estado.workspaceAtivo;
      return w ? { role: w.papel, dataScope: w.escopo, tenantId: w.id } : null;
    },
    permissoes: function () { return estado.permissoes.slice(); },
    pode: pode,
    podeVerClinicoDe: podeVerClinicoDe,
    escopo: escopo,
    profissional: function () {
      var p = estado.perfil;
      if (!p) return null;
      return {
        id: p.id, displayName: p.nomeExibicao, professionSlug: p.profissao,
        council: p.conselho, registrationNumber: p.registro
      };
    },
    profissionalId: function () { return estado.perfil ? estado.perfil.id : null; },
    workspaces: workspaces,
    trocarTenant: trocarTenant,
    aoTrocarTenant: aoTrocarTenant,
    aplicarContexto: aplicarContexto,

    /* usado pelo cabeçalho e pela tela de perfil */
    atual: function () {
      var u = estado.usuario || {};
      var p = estado.perfil;
      var w = estado.workspaceAtivo;
      return {
        id: u.id, nome: u.nome || "", email: u.email || "",
        papel: w ? w.papel : null,
        tratamento: p ? (p.conselho ? p.conselho : "Profissional") : "",
        registro: p && p.conselho ? p.conselho + " " + (p.registro || "") : "",
        tenantId: w ? w.id : null
      };
    }
  };
})(window);
