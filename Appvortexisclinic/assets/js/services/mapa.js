/* =============================================================
   TRADUÇÃO API ↔ TELA
   -------------------------------------------------------------
   A borda da API fala inglês (clients, appointments, scheduled) —
   foi a decisão 5 da arquitetura. O painel fala português, porque
   é o que aparece para quem usa.

   Este arquivo é a fronteira entre os dois. Existe por um motivo
   prático: sem ele, cada tela teria o seu `if status === "done"`
   espalhado, e a primeira mudança de contrato viraria caça ao
   string. Aqui é um lugar só.

   O que NÃO acontece aqui: regra de negócio. Isto traduz nome e
   formato, nada mais. Número é calculado no servidor.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  var STATUS_ATENDIMENTO = {
    scheduled: "agendado", confirmed: "confirmado", done: "realizado",
    no_show: "falta", cancelled: "cancelado"
  };
  var PAGAMENTO = { pending: "pendente", paid: "pago", waived: "isento" };
  var MODALIDADE = { in_person: "presencial", online: "online" };
  var FREQUENCIA = { weekly: "semanal", biweekly: "quinzenal", monthly: "mensal", irregular: "irregular" };
  var STATUS_CLIENTE = { active: "ativo", inactive: "inativo", archived: "arquivado" };

  function inverter(mapa) {
    var saida = {};
    Object.keys(mapa).forEach(function (k) { saida[mapa[k]] = k; });
    return saida;
  }

  var PARA_API = {
    statusAtendimento: inverter(STATUS_ATENDIMENTO),
    pagamento: inverter(PAGAMENTO),
    modalidade: inverter(MODALIDADE),
    frequencia: inverter(FREQUENCIA),
    statusCliente: inverter(STATUS_CLIENTE)
  };

  function traduzir(mapa, valor) {
    return mapa[valor] !== undefined ? mapa[valor] : valor;
  }

  /* ---------------- resumo da pessoa atendida ---------------- */
  function resumo(r) {
    if (!r) return null;
    return {
      total: r.total,
      realizados: r.realizados,
      faltas: r.faltas,
      presenca: r.presenca,
      ultimo: r.ultimo || null,
      proximo: r.proximo || null,
      valorEmAberto: Number(r.valor_em_aberto || 0),
      quantidadeEmAberto: r.quantidade_em_aberto || 0
    };
  }

  /* ---------------- pessoa atendida ---------------- */
  function cliente(c) {
    if (!c) return null;
    return {
      id: c.id,
      nome: c.nome,
      email: c.email,
      telefone: c.telefone,
      nascimento: c.nascimento,
      status: traduzir(STATUS_CLIENTE, c.status),
      frequencia: traduzir(FREQUENCIA, c.frequencia),
      modalidadePadrao: traduzir(MODALIDADE, c.modalidade),
      valorSessao: c.valor_sessao === null || c.valor_sessao === undefined ? null : Number(c.valor_sessao),
      desde: c.desde,
      observacao: c.observacao,
      /* Cadastro anonimizado a pedido do titular: a tela precisa saber
         para não oferecer "anonimizar" de novo. */
      anonimizadoEm: c.anonimizado_em || null,
      resumo: resumo(c.resumo)
    };
  }

  function clienteParaApi(d) {
    var saida = {};
    if (d.nome !== undefined) saida.nome = d.nome;
    if (d.email) saida.email = d.email;
    if (d.telefone) saida.telefone = d.telefone;
    if (d.nascimento) saida.nascimento = d.nascimento;
    if (d.frequencia) saida.frequencia = traduzir(PARA_API.frequencia, d.frequencia);
    if (d.modalidade) saida.modalidade = traduzir(PARA_API.modalidade, d.modalidade);
    if (d.valorSessao !== undefined && d.valorSessao !== null) saida.valor_sessao = String(d.valorSessao);
    if (d.desde) saida.desde = d.desde;
    if (d.observacao !== undefined) saida.observacao = d.observacao;
    if (d.status) saida.status = traduzir(PARA_API.statusCliente, d.status);
    return saida;
  }

  /* ---------------- atendimento ---------------- */
  function atendimento(a) {
    if (!a) return null;
    return {
      id: a.id,
      inicio: a.inicio,
      duracaoMin: a.duracao_min,
      modalidade: traduzir(MODALIDADE, a.modalidade),
      status: traduzir(STATUS_ATENDIMENTO, a.status),
      pagamento: traduzir(PAGAMENTO, a.pagamento),
      valor: a.valor === null || a.valor === undefined ? 0 : Number(a.valor),
      metodoPagamento: a.metodo_pagamento,
      pagoEm: a.pago_em,
      observacao: a.observacao,
      profissionalId: a.profissional_id,
      pacienteId: a.cliente ? a.cliente.id : null,
      paciente: a.cliente
        ? { id: a.cliente.id, nome: a.cliente.nome, status: traduzir(STATUS_CLIENTE, a.cliente.status) }
        : { id: null, nome: "—", status: null },
      diasEmAberto: a.dias_em_aberto
    };
  }

  /* ---------------- pagamento ---------------- */
  var METODO = {
    pix: "Pix", card: "Cartão", cash: "Dinheiro",
    transfer: "Transferência", other: "Outro"
  };

  function pagamento(p) {
    if (!p) return null;
    return {
      id: p.id,
      valor: Number(p.valor || 0),
      metodo: p.metodo,
      metodoRotulo: METODO[p.metodo] || p.metodo,
      estornado: p.status === "refunded",
      pagoEm: p.pago_em,
      observacao: p.observacao,
      estornadoEm: p.estornado_em,
      motivoEstorno: p.motivo_estorno,
      paciente: p.cliente
        ? { id: p.cliente.id, nome: p.cliente.nome, status: traduzir(STATUS_CLIENTE, p.cliente.status) }
        : { id: null, nome: "—" },
      atendimentoId: p.atendimento_id
    };
  }

  /* ---------------- prontuário ---------------- */
  var TIPO_NOTA = {
    session: "Evolução", assessment: "Avaliação",
    plan: "Plano terapêutico", note: "Anotação"
  };
  var STATUS_NOTA = { draft: "rascunho", signed: "assinada" };

  var ACAO_CLINICA = {
    list: "abriu a lista", read: "leu o registro", create: "criou registro",
    update: "editou registro", sign: "assinou registro", export: "exportou"
  };
  var MOTIVO_NEGATIVA = {
    fora_do_alcance: "sem alcance a este registro",
    nao_e_autor: "não é autor do registro",
    sem_perfil_profissional: "sem perfil profissional",
    conteudo_ilegivel: "conteúdo não pôde ser aberto",
    conteudo_apagado: "conteúdo apagado a pedido"
  };

  function nota(n) {
    if (!n) return null;
    return {
      id: n.id,
      tipo: n.tipo,
      tipoRotulo: TIPO_NOTA[n.tipo] || n.tipo,
      status: traduzir(STATUS_NOTA, n.status),
      assinada: n.status === "signed",
      ocorridoEm: n.ocorrido_em,
      versaoAtual: n.versao_atual,
      assinadaEm: n.assinada_em,
      conteudoApagadoEm: n.conteudo_apagado_em,
      autor: n.autor,
      autorId: n.autor_id,
      souOAutor: !!n.sou_o_autor,
      atendimentoId: n.atendimento_id,
      paciente: n.cliente
        ? { id: n.cliente.id, nome: n.cliente.nome }
        : { id: null, nome: "—" }
    };
  }

  function versaoDaNota(v) {
    return {
      versao: v.versao,
      criadoEm: v.criado_em,
      motivo: v.motivo,
      impressao: v.impressao
    };
  }

  function conteudoDaNota(c) {
    return {
      id: c.id,
      versao: c.versao,
      conteudo: c.conteudo,     /* texto puro: a tela escreve com escape */
      impressao: c.impressao,
      criadoEm: c.criado_em
    };
  }

  function acessoClinico(a) {
    return {
      id: a.id,
      quando: a.quando,
      acao: ACAO_CLINICA[a.acao] || a.acao,
      permitido: a.resultado === "allowed",
      motivo: a.motivo ? (MOTIVO_NEGATIVA[a.motivo] || a.motivo) : null,
      quem: a.quem,
      notaId: a.nota_id
    };
  }

  /* ---------------- privacidade ---------------- */
  var TIPO_CONSENTIMENTO = {
    terms: "Termos de uso", privacy: "Política de privacidade",
    clinical_treatment: "Atendimento clínico", image: "Uso de imagem",
    communication: "Contato e lembretes"
  };
  var TIPO_PEDIDO = {
    access: "Acesso aos dados", portability: "Portabilidade",
    rectification: "Correção", erasure: "Exclusão",
    restriction: "Restrição de tratamento", revoke_consent: "Revogação de consentimento",
    information: "Informação sobre tratamento"
  };
  var STATUS_PEDIDO = { open: "aberto", in_progress: "em andamento",
                        done: "concluído", refused: "recusado" };
  var ALVO = {
    registration: "Cadastro", appointments: "Atendimentos", payments: "Financeiro",
    clinical: "Prontuário", documents: "Documentos", other: "Outros"
  };
  var DECISAO = {
    export: "Exportar", anonymize: "Anonimizar", erase: "Apagar conteúdo",
    keep: "Manter", restrict: "Restringir tratamento"
  };

  function consentimento(c) {
    if (!c) return null;
    return {
      id: c.id,
      tipo: c.tipo,
      tipoRotulo: TIPO_CONSENTIMENTO[c.tipo] || c.tipo,
      versao: c.versao,
      aceitoEm: c.aceito_em,
      revogadoEm: c.revogado_em,
      vigente: !!c.vigente,
      origem: c.origem,
      observacao: c.observacao
    };
  }

  function decisao(d) {
    return {
      id: d.id,
      alvo: d.alvo,
      alvoRotulo: ALVO[d.alvo] || d.alvo,
      decisao: d.decisao,
      decisaoRotulo: DECISAO[d.decisao] || d.decisao,
      motivo: d.motivo,
      baseLegal: d.base_legal,
      aplicadoEm: d.aplicado_em,
      aplicada: !!d.aplicado_em,
      resultado: d.resultado
    };
  }

  function pedido(p) {
    if (!p) return null;
    return {
      id: p.id,
      tipo: p.tipo,
      tipoRotulo: TIPO_PEDIDO[p.tipo] || p.tipo,
      status: p.status,
      statusRotulo: STATUS_PEDIDO[p.status] || p.status,
      encerrado: p.status === "done" || p.status === "refused",
      solicitante: p.solicitante,
      pedidoEm: p.pedido_em,
      prazo: p.prazo,
      encerradoEm: p.encerrado_em,
      observacao: p.observacao,
      desfecho: p.desfecho,
      paciente: p.cliente ? { id: p.cliente.id, nome: p.cliente.nome } : null,
      decisoes: (p.decisoes || []).map(decisao)
    };
  }

  function politica(p) {
    return {
      id: p.id,
      alvo: p.alvo,
      alvoRotulo: ALVO[p.alvo] || p.alvo,
      profissao: p.profissao,
      meses: p.meses,
      baseLegal: p.base_legal,
      observacao: p.observacao,
      /* Só decide algo quando tem prazo E base legal. */
      aplicavel: !!p.aplicavel
    };
  }

  function evento(e) {
    return {
      id: e.id,
      quando: e.quando,
      acao: e.acao,
      permitido: e.resultado === "allowed",
      quem: e.quem,
      detalhe: e.detalhe
    };
  }

  /* ---------------- documentos ---------------- */
  var TIPO_DOCUMENTO = {
    receipt: "Recibo", attendance: "Declaração de comparecimento",
    report: "Relatório", record_copy: "Cópia do prontuário", upload: "Arquivo anexado"
  };

  function documento(d) {
    if (!d) return null;
    return {
      id: d.id,
      tipo: d.tipo,
      tipoRotulo: TIPO_DOCUMENTO[d.tipo] || d.tipo,
      /* "clinical" x "administrative" é o que decide quem abre. */
      classe: d.classe,
      eClinico: d.classe === "clinical",
      titulo: d.titulo,
      nomeArquivo: d.nome_arquivo,
      tamanho: d.tamanho,
      criadoEm: d.criado_em,
      impressao: d.impressao,
      conteudoApagadoEm: d.conteudo_apagado_em,
      paciente: d.cliente ? { id: d.cliente.id, nome: d.cliente.nome } : null
    };
  }

  /* ---------------- agenda: recorrência e bloqueios ---------------- */
  var FREQUENCIA_SERIE = { weekly: "semanal", biweekly: "quinzenal", monthly: "mensal" };
  var TIPO_BLOQUEIO = { vacation: "Férias", holiday: "Feriado",
                        break: "Intervalo", other: "Indisponível" };
  var MOTIVO_CONFLITO = {
    conflito_de_horario: "já havia atendimento nesse horário",
    horario_bloqueado: "horário bloqueado"
  };

  function serie(s) {
    if (!s) return null;
    return {
      id: s.id,
      frequencia: s.frequencia,
      frequenciaRotulo: FREQUENCIA_SERIE[s.frequencia] || s.frequencia,
      inicio: s.inicio,
      duracaoMin: s.duracao_min,
      modalidade: traduzir(MODALIDADE, s.modalidade),
      valor: s.valor === null || s.valor === undefined ? null : Number(s.valor),
      ocorrencias: s.ocorrencias,
      ate: s.ate,
      status: s.status,
      ativa: s.status === "active",
      observacao: s.observacao,
      paciente: s.cliente ? { id: s.cliente.id, nome: s.cliente.nome } : null
    };
  }

  function conflitoDaSerie(c) {
    return {
      inicio: c.inicio,
      motivo: c.motivo,
      motivoRotulo: MOTIVO_CONFLITO[c.motivo] || c.motivo,
      detalhe: c.detalhe
    };
  }

  function bloqueio(b) {
    if (!b) return null;
    return {
      id: b.id,
      inicio: b.inicio,
      fim: b.fim,
      titulo: b.titulo,
      tipo: b.tipo,
      tipoRotulo: TIPO_BLOQUEIO[b.tipo] || b.tipo,
      profissionalId: b.profissional_id,
      daContaInteira: !!b.da_conta_inteira
    };
  }

  /* ---------------- equipe e configurações ---------------- */
  var PAPEL = { OWNER: "Dono da conta", PROFESSIONAL: "Profissional",
                ASSISTANT: "Apoio administrativo" };
  var ESCOPO = { all: "toda a conta", own: "só os seus" };
  var STATUS_MEMBRO = { active: "ativo", suspended: "suspenso", invited: "convidado" };

  function membro(m) {
    if (!m) return null;
    return {
      id: m.id,
      nome: m.nome,
      email: m.email,
      papel: m.papel,
      papelRotulo: m.papel_nome || PAPEL[m.papel] || m.papel,
      escopo: m.escopo,
      escopoRotulo: ESCOPO[m.escopo] || m.escopo,
      status: m.status,
      statusRotulo: STATUS_MEMBRO[m.status] || m.status,
      ativo: m.status === "active",
      souEu: !!m.sou_eu,
      atende: !!m.atende,
      profissionalId: m.profissional_id
    };
  }

  function convite(c) {
    if (!c) return null;
    return {
      id: c.id,
      email: c.email,
      papel: c.papel,
      papelRotulo: PAPEL[c.papel] || c.papel,
      escopo: c.escopo,
      profissao: c.profissao,
      mensagem: c.mensagem,
      expiraEm: c.expira_em,
      convidadoPor: c.convidado_por,
      /* Só vem na criação. Depois o servidor não tem mais o token. */
      link: c.link || null
    };
  }

  function convitePublico(c) {
    return {
      workspace: c.workspace,
      papel: c.papel,
      papelRotulo: c.papel_nome || PAPEL[c.papel] || c.papel,
      email: c.email,
      mensagem: c.mensagem,
      expiraEm: c.expira_em,
      jaTemConta: !!c.ja_tem_conta
    };
  }

  function configuracao(c) {
    if (!c) return null;
    return {
      jornadaInicio: c.jornada_inicio,
      jornadaFim: c.jornada_fim,
      dias: c.dias_da_semana || [],
      duracaoPadrao: c.duracao_padrao,
      intervalo: c.intervalo,
      toleranciaFalta: c.tolerancia_falta,
      metaMensal: c.meta_mensal === null || c.meta_mensal === undefined
        ? null : Number(c.meta_mensal),
      moeda: c.moeda,
      fuso: c.fuso,
      terminologia: c.terminologia || {},
      /* Chaves que o servidor recusou na última gravação. A tela
         avisa em vez de fingir que gravou. */
      recusados: c.recusados || []
    };
  }

  /* ---------------- números ---------------- */
  function resumoDia(d) {
    return {
      total: d.total, realizados: d.realizados, faltas: d.faltas,
      cancelados: d.cancelados, restantes: d.restantes,
      previsto: Number(d.previsto || 0), presenca: d.presenca
    };
  }

  function resumoSemana(s) {
    return {
      inicio: s.inicio, fim: s.fim,
      dias: (s.dias || []).map(function (d) {
        return { data: d.data, total: d.total, realizados: d.realizados, faltas: d.faltas, hoje: d.hoje };
      }),
      agendados: s.agendados, realizados: s.realizados, faltas: s.faltas, presenca: s.presenca
    };
  }

  function financeiro(f) {
    if (!f) return null;
    return {
      referencia: f.referencia,
      recebido: Number(f.recebido || 0),
      pendente: Number(f.pendente || 0),
      previsto: Number(f.previsto || 0),
      total: Number(f.total || 0),
      quantidadeRecebida: f.quantidade_recebida,
      quantidadePendente: f.quantidade_pendente,
      meta: f.meta === null || f.meta === undefined ? null : Number(f.meta),
      percentualMeta: f.percentual_meta,
      variacaoMesAnterior: f.variacao_mes_anterior
    };
  }

  /* ---------------- plano da conta ----------------
     Limite `null` é SEM LIMITE, não zero — e a tela precisa dizer isso.
     Preço `null` é "ainda não definido": a tela não inventa valor. */
  var STATUS_ASSINATURA = {
    trialing: "em teste", active: "ativa", past_due: "pagamento em atraso", canceled: "cancelada"
  };

  function limiteOuNulo(v) { return v === null || v === undefined ? null : Number(v); }

  function plano(p) {
    if (!p) return null;
    var l = p.limites || {}, u = p.uso || {}, r = p.recursos || {};
    return {
      chave: p.plano,
      nome: p.plano_nome,
      status: traduzir(STATUS_ASSINATURA, p.status),
      vigente: !!p.vigente,
      testeAte: p.trial_ate || null,
      periodoAte: p.periodo_ate || null,
      planoPendente: p.plano_pendente || null,
      cobrancaAtiva: !!p.cobranca_ativa,
      assinaturaPaga: !!p.assinatura_paga,
      catalogo: (p.catalogo || []).map(function (c) {
        return { chave: c.plano, nome: c.nome, descricao: c.descricao || "",
                 precoMensal: Number(c.preco_mensal) };
      }),
      precoMensal: p.preco_mensal === null || p.preco_mensal === undefined
        ? null : Number(p.preco_mensal),
      limites: {
        profissionais: limiteOuNulo(l.profissionais),
        membros: limiteOuNulo(l.membros),
        pessoas: limiteOuNulo(l.clientes),
        armazenamentoMb: limiteOuNulo(l.armazenamento_mb)
      },
      uso: {
        profissionais: Number(u.profissionais || 0),
        membros: Number(u.membros || 0),
        pessoas: Number(u.clientes || 0),
        armazenamentoMb: Number(u.armazenamento_mb || 0)
      },
      recursos: {
        clinico: !!r.clinico, documentos: !!r.documentos,
        exportacao: !!r.exportacao, lembretes: !!r.lembretes
      }
    };
  }

  VC.mapa = {
    plano: plano,
    STATUS_ASSINATURA: STATUS_ASSINATURA,
    consentimento: consentimento,
    pedido: pedido,
    decisao: decisao,
    politica: politica,
    evento: evento,
    TIPO_CONSENTIMENTO: TIPO_CONSENTIMENTO,
    TIPO_PEDIDO: TIPO_PEDIDO,
    ALVO_DE_DADO: ALVO,
    DECISAO: DECISAO,
    documento: documento,
    TIPO_DOCUMENTO: TIPO_DOCUMENTO,
    serie: serie,
    conflitoDaSerie: conflitoDaSerie,
    bloqueio: bloqueio,
    FREQUENCIA_SERIE: FREQUENCIA_SERIE,
    TIPO_BLOQUEIO: TIPO_BLOQUEIO,
    membro: membro,
    convite: convite,
    convitePublico: convitePublico,
    configuracao: configuracao,
    PAPEL: PAPEL,
    nota: nota,
    versaoDaNota: versaoDaNota,
    conteudoDaNota: conteudoDaNota,
    acessoClinico: acessoClinico,
    TIPO_NOTA: TIPO_NOTA,
    pagamento: pagamento,
    METODO: METODO,
    cliente: cliente,
    clienteParaApi: clienteParaApi,
    atendimento: atendimento,
    resumo: resumo,
    resumoDia: resumoDia,
    resumoSemana: resumoSemana,
    financeiro: financeiro,
    paraApi: PARA_API,
    STATUS_ATENDIMENTO: STATUS_ATENDIMENTO,
    PAGAMENTO: PAGAMENTO,
    MODALIDADE: MODALIDADE
  };
})(window);
