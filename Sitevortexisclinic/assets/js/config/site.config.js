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
      // Botões Entrar / Criar conta ativos. Só vire true quando a API estiver
      // no ar (VPS) e app.vortexisclinic.com.br abrir de verdade — antes
      // disso o botão leva a uma página quebrada.
      auth: false,
      plans: false,         // seção de planos e preços (os preços ainda não existem)
      pwaTutorial: true,    // modal "Como instalar no celular"
      productPages: true    // links das páginas por vertical
    },

    /* Destinos do painel. O login e o cadastro moram na mesma tela de entrada. */
    links: {
      login: "https://app.vortexisclinic.com.br/",
      signup: "https://app.vortexisclinic.com.br/",
      appUrl: "https://app.vortexisclinic.com.br"
    },

    /* Assunto do e-mail do botão "Quero testar" (acesso antecipado). */
    earlyAccessSubject: "Quero testar a Vortexis Clinic",

    /* Se um dia o site rodar com URLs limpas (/psicologia),
       troque para true e os links deixam de usar index.html. */
    prettyUrls: false,

    /* Seis itens no máximo: com mais, o menu aperta no desktop estreito.
       "Início" fica a cargo do logo. */
    nav: [
      { label: "Soluções", href: "#solucoes" },
      { label: "Como funciona", href: "#como-funciona" },
      { label: "Segurança", href: "#seguranca" },
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
            { label: "Segurança e LGPD", href: "#seguranca" },
            { label: "Aplicativo (PWA)", href: "#aplicativo" },
            { label: "Perguntas frequentes", href: "#perguntas" },
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

    legal: { updatedAt: "outubro de 2026" }
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

  /* Destino do "Quero testar" / "Falar com a Vortexis": WhatsApp se houver,
     senão e-mail (com assunto, quando informado), senão a seção de contato. */
  global.VC.contactHref = function (subject) {
    if (SITE.contact.whatsapp) return "https://wa.me/" + SITE.contact.whatsapp;
    if (SITE.contact.email) {
      return "mailto:" + SITE.contact.email + (subject ? "?subject=" + encodeURIComponent(subject) : "");
    }
    return global.VC.anchor("#contato");
  };

  /* Ancora da home: funciona tanto na home quanto nas internas. */
  global.VC.anchor = function (hash) {
    var base = global.VC.base();
    if (!base) return hash;
    return global.VC.url("home", hash);
  };
})(window);
