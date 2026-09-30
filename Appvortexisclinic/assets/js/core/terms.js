/* =============================================================
   TERMINOLOGIA
   -------------------------------------------------------------
   Um tenant chama de "paciente", outro de "cliente"; um chama o
   encontro de "sessão", outro de "atendimento". Nenhuma tela
   escreve esses termos: todas pedem aqui.

       t("client.plural")      -> "Pacientes"
       t("appointment.one")    -> "Atendimento"
       t("client.one", true)   -> "paciente"   (minúsculo, para o meio da frase)

   O dicionário do tenant chega do servidor (tenant_settings.terminology)
   e passa por saneamento: só texto curto e simples. Nada de HTML —
   além disso, todo termo sai daqui como texto e é escapado de novo
   ao entrar em html``.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  /* Padrão da plataforma. Cada profissão pode trazer o seu (vem do
     catálogo de profissões) e o tenant pode sobrescrever. */
  var PADRAO = {
    "client.one": "Paciente",
    "client.many": "Pacientes",
    "client.new": "Cadastrar paciente",
    "client.search": "Buscar paciente",

    "appointment.one": "Atendimento",
    "appointment.many": "Atendimentos",
    "appointment.new": "Novo atendimento",

    "session.one": "Sessão",
    "session.many": "Sessões",

    "professional.one": "Profissional",
    "professional.many": "Profissionais",

    "record.one": "Registro clínico",
    "record.many": "Registros clínicos",
    "record.new": "Novo registro",
    "note.one": "Anotação",
    "note.many": "Anotações",

    "schedule.title": "Agenda",
    "finance.title": "Financeiro",
    "pending.title": "Pendências"
  };

  /* Sugestões por categoria profissional — o back devolverá isto
     junto com a profissão do tenant. */
  var POR_PROFISSAO = {
    psicologia: {},                                   // usa o padrão
    terapia_integrativa: { "client.one": "Cliente", "client.many": "Clientes",
                           "client.new": "Cadastrar cliente", "client.search": "Buscar cliente" },
    nutricao: { "appointment.one": "Consulta", "appointment.many": "Consultas",
                "appointment.new": "Nova consulta" }
  };

  var atual = Object.assign({}, PADRAO);

  /* Saneamento: termo é rótulo curto de interface, não conteúdo.
     Recusa marcação, entidades, quebra de linha e exageros. */
  function limpar(valor) {
    if (typeof valor !== "string") return null;
    var v = valor.replace(/\s+/g, " ").trim();
    if (!v || v.length > 40) return null;
    if (/[<>&"'`\\{}]/.test(v)) return null;          // nada de marcação nem entidade
    if (/^https?:|javascript:|data:/i.test(v)) return null;
    return v;
  }

  function definir(dicionario, origem) {
    if (!dicionario) return { aplicados: 0, recusados: [] };
    var aplicados = 0, recusados = [];
    Object.keys(dicionario).forEach(function (chave) {
      if (!Object.prototype.hasOwnProperty.call(PADRAO, chave)) { recusados.push(chave); return; }
      var v = limpar(dicionario[chave]);
      if (v === null) { recusados.push(chave); return; }
      atual[chave] = v;
      aplicados++;
    });
    if (recusados.length && global.console && origem) {
      console.warn("[terms] termos ignorados (" + origem + "):", recusados.join(", "));
    }
    return { aplicados: aplicados, recusados: recusados };
  }

  /* Ordem de precedência: padrão -> profissão -> tenant. */
  function configurar(opcoes) {
    opcoes = opcoes || {};
    atual = Object.assign({}, PADRAO);
    if (opcoes.profissao && POR_PROFISSAO[opcoes.profissao]) {
      definir(POR_PROFISSAO[opcoes.profissao], "profissão");
    }
    if (opcoes.tenant) definir(opcoes.tenant, "tenant");
    return atual;
  }

  function t(chave, minusculo) {
    var v = atual[chave];
    if (v === undefined) {
      if (global.console) console.warn("[terms] chave desconhecida:", chave);
      return chave;
    }
    return minusculo ? v.charAt(0).toLowerCase() + v.slice(1) : v;
  }

  VC.terms = {
    t: t,
    configurar: configurar,
    definir: definir,
    padrao: function () { return Object.assign({}, PADRAO); },
    atual: function () { return Object.assign({}, atual); },
    chaves: function () { return Object.keys(PADRAO); },
    _limpar: limpar
  };

  global.t = t;
})(window);
