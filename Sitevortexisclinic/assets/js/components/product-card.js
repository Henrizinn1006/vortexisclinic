/* =============================================================
   Card de solução (vertical) + grade de soluções.
   Um produto novo em products.js aparece aqui automaticamente.
   ============================================================= */
(function (global) {
  "use strict";

  function card(product, opts) {
    opts = opts || {};
    var st = global.VC.products.status(product);
    var site = global.VC.site;
    var maxFeatures = opts.maxFeatures || 5;
    var features = product.features.slice(0, maxFeatures);
    var rest = product.features.length - features.length;

    var pills = features
      .map(function (f) { return '<span class="feature-pill">' + f + "</span>"; })
      .join("");
    if (rest > 0) pills += '<span class="feature-pill">+' + rest + "</span>";

    var cta = site.features.productPages
      ? '<a class="btn btn--accent btn--sm btn--arrow" href="' + global.VC.url(product.slug) + '">' +
        st.cta + "</a>"
      : '<span class="btn btn--outline btn--sm" aria-disabled="true">' + st.cta + "</span>";

    return (
      '<article class="card card--hover product-card" data-anim="up" data-theme="' + (product.theme || "clinic") + '">' +
      '<div class="product-card__head">' +
      "<div>" +
      '<span class="product-card__brand">Vortexis Clinic</span>' +
      '<h3 class="product-card__name">' + product.name + "</h3>" +
      "</div>" +
      '<span class="badge ' + st.badge + '"><span class="badge__dot"></span>' + st.label + "</span>" +
      "</div>" +
      '<p class="product-card__text">' + product.short + "</p>" +
      '<div class="product-card__features">' + pills + "</div>" +
      '<div class="product-card__footer">' + cta + "</div>" +
      "</article>"
    );
  }

  function grid(host, opts) {
    if (!host) return;
    var items = global.VC.products.all();
    host.innerHTML = items
      .map(function (p) { return card(p, opts); })
      .join("");
  }

  global.VC = global.VC || {};
  global.VC.productCard = card;
  global.VC.renderProductGrid = grid;
})(window);
