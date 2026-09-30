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

  /* Estados possíveis de um produto e como aparecem na interface. */
  var STATUS = {
    available: { label: "Disponível", badge: "badge--available", cta: "Conhecer sistema", active: true },
    "in-development": { label: "Em desenvolvimento", badge: "badge--available", cta: "Conhecer sistema", active: true },
    "coming-soon": { label: "Em breve", badge: "badge--soon", cta: "Ver detalhes", active: true },
    planned: { label: "No roadmap", badge: "badge--planned", cta: "Ver detalhes", active: true }
  };

  var PRODUCTS = [
    {
      slug: "psicologia",
      name: "Psicologia",
      fullName: "Vortexis Clinic — Psicologia",
      status: "in-development",
      theme: "psicologia",
      icon: "brain",
      order: 1,
      short: "Gestão completa para psicólogos e clínicas de psicologia.",
      description:
        "Pacientes, agenda, sessões, presenças e financeiro em um único lugar, com o registro clínico organizado do jeito que a rotina do consultório pede.",
      features: [
        "Pacientes",
        "Agenda",
        "Sessões",
        "Presença e faltas",
        "Financeiro",
        "Prontuários",
        "Anotações",
        "Relatórios"
      ],
      highlights: [
        { title: "Pacientes e agenda", text: "Cadastro, histórico e agenda com visão de dia, semana e profissional." },
        { title: "Sessões e frequência", text: "Controle de sessões realizadas, faltas e remarcações sem planilha paralela." },
        { title: "Prontuário e anotações", text: "Evolução e registros do atendimento organizados por paciente." },
        { title: "Financeiro do consultório", text: "Recebimentos, pendências e visão simples do mês." },
        { title: "Relatórios essenciais", text: "Números de atendimentos, faltas e receita para decidir com clareza." },
        { title: "Acesso de qualquer lugar", text: "Computador, tablet ou celular, com instalação como aplicativo." }
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
