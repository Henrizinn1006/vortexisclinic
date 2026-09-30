/* =============================================================
   Página de uma vertical. O HTML da página é apenas uma casca:
   <body data-base="../" data-product="psicologia">
   Todo o conteúdo vem de assets/js/data/products.js.
   ============================================================= */
(function (global) {
  "use strict";

  function ctaContato() {
    var site = global.VC.site;
    if (site.contact.whatsapp) return "https://wa.me/" + site.contact.whatsapp;
    return site.contact.email ? "mailto:" + site.contact.email : global.VC.anchor("#contato");
  }

  function hero(product, st) {
    var soon = product.status !== "available" && product.status !== "in-development";
    return (
      '<section class="product-hero">' +
      '<div class="container product-hero__inner">' +
      '<nav class="breadcrumb" aria-label="Trilha">' +
      '<a href="' + global.VC.url("home") + '">Início</a><span>/</span>' +
      '<a href="' + global.VC.anchor("#solucoes") + '">Soluções</a><span>/</span>' +
      "<span>" + product.name + "</span></nav>" +
      '<span class="badge ' + st.badge + '"><span class="badge__dot"></span>' + st.label + "</span>" +
      '<h1 class="product-hero__title" style="margin-top:var(--sp-4)">' + product.fullName + "</h1>" +
      '<p class="product-hero__text">' + product.description + "</p>" +
      '<div class="product-hero__actions">' +
      '<a class="btn btn--accent btn--arrow" href="' + ctaContato() + '"' +
      (global.VC.site.contact.whatsapp ? ' target="_blank" rel="noopener"' : "") + ">" +
      (soon ? "Quero ser avisado" : "Falar com a Vortexis") + "</a>" +
      '<a class="btn btn--outline" href="' + global.VC.anchor("#solucoes") + '">Ver todas as soluções</a>' +
      "</div>" +
      "</div></section>"
    );
  }

  function highlights(product) {
    if (!product.highlights || !product.highlights.length) return "";
    return (
      '<section class="section section--alt"><div class="container">' +
      '<div class="section__head"><span class="eyebrow">O que o sistema resolve</span>' +
      "<h2 data-anim=\"up\">Recursos previstos para " + product.name + "</h2>" +
      '<p class="section__lead">Módulos planejados sobre a base compartilhada da Vortexis Clinic: cadastro, agenda, financeiro e acesso multiplataforma.</p></div>' +
      '<div class="feature-grid">' +
      product.highlights
        .map(function (h, i) {
          return (
            '<div class="feature-item" data-anim="up">' +
            '<span class="num">' + (i < 9 ? "0" : "") + (i + 1) + "</span>" +
            "<b>" + h.title + "</b>" +
            '<p>' + h.text + "</p></div>"
          );
        })
        .join("") +
      "</div></div></section>"
    );
  }

  function modules(product) {
    return (
      '<section class="section"><div class="container">' +
      '<div class="grid grid--2" style="align-items:start;gap:var(--sp-6)">' +
      "<div>" +
      '<span class="eyebrow">Funcionalidades</span>' +
      "<h2>Tudo em um lugar só</h2>" +
      "<p>A vertical de " + product.name.toLowerCase() +
      " usa o núcleo da plataforma e adiciona os módulos específicos da área.</p>" +
      '<div class="product-card__features" data-theme="' + (product.theme || "clinic") + '">' +
      product.features.map(function (f) { return '<span class="feature-pill">' + f + "</span>"; }).join("") +
      "</div>" +
      "</div>" +
      '<div class="soon-panel" data-anim="up">' +
      '<div><span class="eyebrow">Para quem é</span><p style="margin:0">' + product.audience + "</p></div>" +
      '<div style="border-top:1px solid var(--vc-border);padding-top:var(--sp-4)">' +
      '<b style="color:var(--vc-blue-dark)">Uso no computador e no celular</b>' +
      '<p style="font-size:var(--fs-sm);margin:var(--sp-2) 0 0">O sistema funciona no navegador e pode ser instalado na tela inicial do celular. ' +
      '<a href="#" data-open="pwa" style="color:var(--accent);font-weight:600">Ver como instalar</a></p>' +
      "</div></div>" +
      "</div></div></section>"
    );
  }

  function others(product) {
    var list = global.VC.products.others(product.slug);
    if (!list.length) return "";
    return (
      '<section class="section section--tint"><div class="container">' +
      '<div class="section__head section__head--center"><span class="eyebrow" style="justify-content:center">Plataforma</span>' +
      "<h2>Outras soluções Vortexis Clinic</h2></div>" +
      '<div class="other-products">' +
      list
        .map(function (p) {
          var st = global.VC.products.status(p);
          return (
            '<a class="other-product" href="' + global.VC.url(p.slug) + '">' + p.name +
            '<span class="badge ' + st.badge + '">' + st.label + "</span></a>"
          );
        })
        .join("") +
      "</div></div></section>"
    );
  }

  function cta(product) {
    return (
      '<section class="cta-final"><div class="container"><div class="cta-card">' +
      '<span class="eyebrow" style="color:var(--vc-green-light);justify-content:center">Vortexis Clinic</span>' +
      "<h2>Quer acompanhar o lançamento de " + product.name + "?</h2>" +
      "<p>Fale com a Vortexis e receba as novidades da plataforma em primeira mão.</p>" +
      '<div class="cta-card__actions">' +
      '<a class="btn btn--light btn--arrow" href="' + ctaContato() + '"' +
      (global.VC.site.contact.whatsapp ? ' target="_blank" rel="noopener"' : "") +
      ">Falar com a Vortexis</a>" +
      '<a class="btn btn--on-dark" href="' + global.VC.anchor("#solucoes") + '">Ver soluções</a>' +
      "</div></div></div></section>"
    );
  }

  function init() {
    var host = document.querySelector("[data-component='product-page']");
    if (!host) return;
    var slug = document.body.getAttribute("data-product");
    var product = global.VC.products.bySlug(slug);

    if (!product) {
      host.innerHTML =
        '<section class="section"><div class="container"><h1>Solução não encontrada</h1>' +
        '<p>Volte para a <a href="' + global.VC.url("home") + '">página inicial</a>.</p></div></section>';
      return;
    }

    document.body.setAttribute("data-theme", product.theme || "clinic");
    if (!document.title || document.title.indexOf("Vortexis") === -1) {
      document.title = product.fullName + " | Vortexis Clinic";
    }

    var st = global.VC.products.status(product);
    host.innerHTML = hero(product, st) + highlights(product) + modules(product) + others(product) + cta(product);
  }

  global.VC = global.VC || {};
  global.VC.pages = global.VC.pages || {};
  global.VC.pages.product = { init: init };
})(window);
