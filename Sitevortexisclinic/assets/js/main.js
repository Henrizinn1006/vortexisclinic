/* =============================================================
   Bootstrap do site. Carregado por ultimo em todas as páginas.
   ============================================================= */
(function (global) {
  "use strict";

  function renderShell() {
    var header = document.querySelector("[data-component='header']");
    var footer = document.querySelector("[data-component='footer']");
    if (header) global.VC.renderHeader(header);
    if (footer) global.VC.renderFooter(footer);
  }

  /* Preenche e-mail/WhatsApp vindos de site.config.js */
  function renderContact() {
    var site = global.VC.site;

    var mail = document.querySelectorAll("[data-contact='email']");
    [].forEach.call(mail, function (el) {
      if (!site.contact.email) { el.closest("[data-contact-card]") && el.closest("[data-contact-card]").remove(); return; }
      el.textContent = site.contact.email;
      if (el.tagName === "A") el.href = "mailto:" + site.contact.email;
    });

    var wpp = document.querySelectorAll("[data-contact='whatsapp']");
    [].forEach.call(wpp, function (el) {
      if (site.contact.whatsapp) {
        el.textContent = site.contact.whatsappLabel;
        if (el.tagName === "A") {
          el.href = "https://wa.me/" + site.contact.whatsapp;
          el.target = "_blank";
          el.rel = "noopener";
        }
      } else {
        /* Sem número oficial: some o cartão em vez de mostrar canal morto. */
        var card = el.closest("[data-contact-card]");
        if (card) card.remove();
        else el.textContent = "Canal em configuração";
      }
    });

    /* Botões "Quero testar" fora do header (CTA da home) */
    var early = document.querySelectorAll("[data-contact='early-access']");
    [].forEach.call(early, function (el) {
      var href = global.VC.contactHref(site.earlyAccessSubject);
      el.href = href;
      if (/^https?:/.test(href)) { el.target = "_blank"; el.rel = "noopener"; }
    });

    var domain = document.querySelectorAll("[data-site='domain']");
    [].forEach.call(domain, function (el) { el.textContent = site.domains.site; });
  }

  function init() {
    renderShell();

    var page = document.body.getAttribute("data-page");
    if (page === "home" && global.VC.pages.home) global.VC.pages.home.init();
    if (page === "product" && global.VC.pages.product) global.VC.pages.product.init();

    renderContact();
    if (global.VC.site.features.pwaTutorial) global.VC.pwaModal.init();
    if (global.VC.motion) global.VC.motion.init();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
