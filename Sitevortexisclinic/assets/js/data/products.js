/* =============================================================
   CATÁLOGO DE SOLUÇÕES DA VORTEXIS CLINIC
   -------------------------------------------------------------
   Para adicionar um sistema novo:
   1. copie um objeto abaixo e ajuste os campos;
   2. crie a pasta /<slug>/index.html (copie de outra vertical);
   3. se quiser cor própria, adicione [data-theme="<theme>"]
      em assets/css/tokens.css.
   Nada mais precisa ser alterado: home, menus e páginas leem daqui.
   ============================================================= */
(function (global) {
  "use strict";

  /* Estados possíveis de um produto e como aparecem na interface.
     live = o sistema já funciona: a página fala no presente ("O que já faz"),
     não no futuro ("Recursos previstos"). */
  var STATUS = {
    available: { label: "Disponível", badge: "badge--available", cta: "Conhecer sistema", active: true, live: true },
    "early-access": { label: "Acesso antecipado", badge: "badge--available", cta: "Conhecer sistema", active: true, live: true },
    "in-development": { label: "Em desenvolvimento", badge: "badge--available", cta: "Conhecer sistema", active: true },
    "coming-soon": { label: "Em breve", badge: "badge--soon", cta: "Ver detalhes", active: true },
    planned: { label: "No roadmap", badge: "badge--planned", cta: "Ver detalhes", active: true }
  };

  var PRODUCTS = [
    {
      slug: "psicologia",
      name: "Psicologia",
      fullName: "Vortexis Clinic — Psicologia",
      status: "early-access",
      theme: "psicologia",
      icon: "brain",
      order: 1,
      short: "Gestão completa para psicólogos e clínicas de psicologia.",
      description:
        "Agenda com sessões recorrentes, pessoas atendidas, financeiro, prontuário cifrado e documentos em PDF — num sistema que trata o sigilo clínico como regra, não como opção.",
      features: [
        "Agenda",
        "Sessões recorrentes",
        "Pessoas atendidas",
        "Financeiro",
        "Prontuário cifrado",
        "Recibos e declarações",
        "Equipe e permissões",
        "LGPD"
      ],
      highlights: [
        { title: "Agenda que entende consultório", text: "Atendimento avulso, série semanal, quinzenal ou mensal e bloqueio de horário. Horário em conflito é recusado; numa série, só a data em conflito fica de fora." },
        { title: "Pessoas atendidas", text: "Cadastro, vínculo com o profissional, histórico completo, arquivamento e anonimização quando a pessoa pede." },
        { title: "Financeiro do consultório", text: "Baixa por atendimento, pagamento avulso ou parcial, estorno, pendências, resumo do mês, meta e exportação em CSV." },
        { title: "Prontuário versionado", text: "Nenhuma nota é sobrescrita: cada edição vira uma versão nova, e a nota assinada só recebe adendo, com motivo." },
        { title: "Documentos em PDF", text: "Recibo, declaração de comparecimento e cópia de prontuário gerados direto no sistema." },
        { title: "Equipe com papéis claros", text: "Convite por link e papéis de dono, profissional e recepção. A recepção cuida da agenda e não vê conteúdo clínico." },
        { title: "Lembretes por e-mail", text: "Lembrete de atendimento, confirmação de endereço e recuperação de senha automáticos." },
        { title: "Acesso de qualquer lugar", text: "Computador, tablet ou celular, com instalação como aplicativo — sem guardar dado clínico no aparelho." }
      ],
      /* Só aparece na página da vertical. Cada item descreve algo que o sistema
         já faz hoje; não acrescente promessa que o código não cumpre. */
      security: [
        { title: "Prontuário cifrado", text: "O texto clínico é cifrado com AES-256 antes de ser gravado. Quem olha o banco de dados direto vê só texto ilegível." },
        { title: "Trilha de acesso", text: "Cada leitura de prontuário fica registrada: quem abriu, qual nota e quando — inclusive as tentativas negadas." },
        { title: "Cada clínica isolada", text: "Os dados de uma conta nunca aparecem para outra. O isolamento vale para toda consulta ao banco, não tela a tela." },
        { title: "Administrar não é ler", text: "Ser dono da conta não dá acesso ao prontuário. Acesso clínico excepcional exige motivo e fica registrado." },
        { title: "LGPD na prática", text: "Consentimento com versão registrada e pedidos do titular decididos item a item, com motivo e base legal." },
        { title: "Sessão protegida", text: "Senha guardada com Argon2id e sessão em cookie protegido, com defesa contra requisições forjadas." }
      ],
      audience: "Psicólogos autônomos e clínicas de psicologia com vários profissionais."
    },
    {
      slug: "odontologia",
      name: "Odontologia",
      fullName: "Vortexis Clinic — Odontologia",
      status: "coming-soon",
      theme: "odontologia",
      icon: "tooth",
      order: 2,
      short: "Gestão para consultórios e clínicas odontológicas.",
      description:
        "Módulo com odontograma, procedimentos, orçamentos e acompanhamento de tratamentos sobre a mesma base da plataforma.",
      features: ["Pacientes", "Agenda", "Odontograma", "Orçamentos", "Tratamentos", "Financeiro"],
      highlights: [
        { title: "Odontograma digital", text: "Registro visual por dente e por face." },
        { title: "Orçamentos e tratamentos", text: "Planos de tratamento, aprovação e acompanhamento das etapas." },
        { title: "Imagens e exames", text: "Arquivos do paciente reunidos no mesmo prontuário." }
      ],
      audience: "Dentistas autônomos e clínicas odontológicas."
    },
    {
      slug: "estetica",
      name: "Estética",
      fullName: "Vortexis Clinic — Estética",
      status: "coming-soon",
      theme: "estetica",
      icon: "sparkle",
      order: 3,
      short: "Gestão para clínicas e profissionais de estética.",
      description:
        "Pacotes, sessões, procedimentos e acompanhamento de resultados com controle financeiro integrado.",
      features: ["Clientes", "Agenda", "Procedimentos", "Pacotes", "Antes e depois", "Financeiro"],
      highlights: [
        { title: "Pacotes e sessões", text: "Controle de sessões usadas e saldo de cada pacote." },
        { title: "Registro de evolução", text: "Comparativo de antes e depois por procedimento." },
        { title: "Produtos e insumos", text: "Acompanhamento do que é usado em cada atendimento." }
      ],
      audience: "Profissionais de estética e clínicas com vários atendentes."
    },
    {
      slug: "fisioterapia",
      name: "Fisioterapia",
      fullName: "Vortexis Clinic — Fisioterapia",
      status: "coming-soon",
      theme: "fisioterapia",
      icon: "activity",
      order: 4,
      short: "Gestão para fisioterapeutas e clínicas de reabilitação.",
      description:
        "Evolução dos pacientes, planos de tratamento, sessões e financeiro dentro da mesma plataforma.",
      features: ["Pacientes", "Agenda", "Sessões", "Evolução", "Planos de tratamento", "Financeiro"],
      highlights: [
        { title: "Planos de tratamento", text: "Sequência de sessões e objetivos por paciente." },
        { title: "Evolução clínica", text: "Registro de progresso ao longo do tratamento." }
      ],
      audience: "Fisioterapeutas autônomos e clínicas de reabilitação."
    },
    {
      slug: "nutricao",
      name: "Nutrição",
      fullName: "Vortexis Clinic — Nutrição",
      status: "coming-soon",
      theme: "nutricao",
      icon: "leaf",
      order: 5,
      short: "Gestão para nutricionistas e clínicas de nutrição.",
      description:
        "Consultas, medidas, evolução e planos alimentares organizados junto com a agenda e o financeiro.",
      features: ["Pacientes", "Agenda", "Consultas", "Medidas", "Evolução", "Planos"],
      highlights: [
        { title: "Medidas e evolução", text: "Histórico de avaliações e comparativo entre consultas." },
        { title: "Planos alimentares", text: "Planos vinculados ao paciente e ao acompanhamento." }
      ],
      audience: "Nutricionistas autônomos e clínicas de nutrição."
    }
  ];

  var api = {
    STATUS: STATUS,
    all: function () {
      return PRODUCTS.slice().sort(function (a, b) { return a.order - b.order; });
    },
    bySlug: function (slug) {
      for (var i = 0; i < PRODUCTS.length; i++) {
        if (PRODUCTS[i].slug === slug) return PRODUCTS[i];
      }
      return null;
    },
    others: function (slug) {
      return api.all().filter(function (p) { return p.slug !== slug; });
    },
    status: function (product) {
      return STATUS[product.status] || STATUS["coming-soon"];
    }
  };

  global.VC = global.VC || {};
  global.VC.products = api;
})(window);
