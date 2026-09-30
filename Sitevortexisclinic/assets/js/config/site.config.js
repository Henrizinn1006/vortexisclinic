/* =============================================================
   CONFIGURAÇÃO GLOBAL DO SITE
   Altere aqui marca, contatos, redes e navegação.
   Nenhum texto de contato deve ser escrito direto no HTML.
   ============================================================= */
(function (global) {
  "use strict";

  var SITE = {
    brand: {
      name: "Vortexis Clinic",
      nameUpper: "VORTEXIS CLINIC",
      parent: "VORTEXIS",
      parentUrl: "https://vortexistech.com",
      tagline: "Ciência a favor de uma vida mais plena",
      description:
        "Plataforma da VORTEXIS com sistemas de gestão para profissionais e clínicas de diferentes áreas da saúde."
    },

    domains: {
      site: "vortexisclinic.com.br",
      app: "app.vortexisclinic.com.br",
      admin: "admin.vortexisclinic.com.br"
    },

    /* Coloque os dados reais quando definir os canais oficiais. */
    contact: {
      email: "contato@vortexisclinic.com.br",
      whatsapp: "",                      // ex.: "5511999999999"
      whatsappLabel: "Falar no WhatsApp",
      city: "Brasil - atendimento online"
    },

    social: [
      // { id: "instagram", label: "Instagram", url: "https://instagram.com/..." },
      // { id: "linkedin",  label: "LinkedIn",  url: "https://linkedin.com/company/..." }
    ],

    /* Flags das funcionalidades das próximas fases.
       Ligue para true quando a etapa correspondente existir. */
    features: {
      auth: false,          // botões Entrar / Criar conta ativos
      plans: false,         // seção de planos e preços
      pwaTutorial: true,    // modal "Como instalar no celular"
      productPages: true    // links das páginas por vertical
    },

    /* URLs de destino das próximas fases (ainda inativas). */
    links: {
      login: "#",
      signup: "#",
      appUrl: "https://app.vortexisclinic.com.br"
    },

    /* Se um dia o site rodar com URLs limpas (/psicologia),
       troque para true e os links deixam de usar index.html. */
    prettyUrls: false,

    nav: [
      { label: "Início", href: "#inicio" },
      { label: "Soluções", href: "#solucoes" },
      { label: "Como funciona", href: "#como-funciona" },
      { label: "Para quem é", href: "#para-quem" },
      { label: "Sobre", href: "#sobre" },
      { label: "Contato", href: "#contato" }
    ],

    footer: {
      columns: [
        {
          title: "Plataforma",
          links: [
            { label: "Soluções", href: "#solucoes" },
            { label: "Como funciona", href: "#como-funciona" },
            { label: "Aplicativo (PWA)", href: "#aplicativo" },
            { label: "Sobre", href: "#sobre" }
          ]
        },
        {
          title: "Institucional",
          links: [
            { label: "Contato", href: "#contato" },
            { label: "Política de Privacidade", page: "politica-de-privacidade" },
            { label: "Termos de Uso", page: "termos-de-uso" }
          ]
        }
      ]
    },

    legal: { updatedAt: "setembro de 2026" }
  };

  global.VC = global.VC || {};
  global.VC.site = SITE;

  /* Resolve caminhos relativos a partir de qualquer página.
     <body data-base="../"> nas páginas internas. */
  global.VC.base = function () {
    var b = document.body && document.body.getAttribute("data-base");
    return b || "";
  };

  /* Monta a URL de uma página interna. */
  global.VC.url = function (page, hash) {
    var base = global.VC.base();
    var suffix = SITE.prettyUrls ? "/" : "/index.html";
    var path;
    if (!page || page === "home") {
      path = base + (SITE.prettyUrls ? "" : "index.html");
      if (!path) path = SITE.prettyUrls ? "/" : "index.html";
    } else {
      path = base + page + suffix;
    }
    return hash ? path + hash : path;
  };

  /* Ancora da home: funciona tanto na home quanto nas internas. */
  global.VC.anchor = function (hash) {
    var base = global.VC.base();
    if (!base) return hash;
    return global.VC.url("home", hash);
  };
})(window);
