/* =============================================================
   Rodapé institucional.
   Renderiza em: <footer class="site-footer" data-component="footer"></footer>
   ============================================================= */
(function (global) {
  "use strict";

  function linkList(links) {
    return links
      .map(function (l) {
        var href = l.page ? global.VC.url(l.page) : (l.url || global.VC.anchor(l.href));
        var ext = l.url ? ' target="_blank" rel="noopener"' : "";
        return "<li><a href=\"" + href + "\"" + ext + ">" + l.label + "</a></li>";
      })
      .join("");
  }

  function productLinks() {
    return global.VC.products
      .all()
      .map(function (p) {
        var st = global.VC.products.status(p);
        return (
          '<li><a href="' + global.VC.url(p.slug) + '">' + p.name +
          (st.live || p.status === "in-development" ? "" : " <span style=\"opacity:.55\">- " + st.label + "</span>") +
          "</a></li>"
        );
      })
      .join("");
  }

  function socialLinks() {
    var site = global.VC.site;
    if (!site.social.length) return "";
    return (
      '<div class="social">' +
      site.social
        .map(function (s) {
          return (
            '<a href="' + s.url + '" target="_blank" rel="noopener" aria-label="' + s.label + '">' +
            global.VC.icon(s.id) + "</a>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function render(host) {
    var site = global.VC.site;
    var year = new Date().getFullYear();

    var contactLinks = [];
    if (site.contact.email) contactLinks.push({ label: site.contact.email, url: "mailto:" + site.contact.email });
    if (site.contact.whatsapp)
      contactLinks.push({ label: site.contact.whatsappLabel, url: "https://wa.me/" + site.contact.whatsapp });

    host.innerHTML =
      '<div class="container">' +
      '<div class="footer__grid">' +
      '<div class="footer__brand">' +
      global.VC.logo({ onDark: true }) +
      '<p class="footer__tagline">' + site.brand.description + "</p>" +
      socialLinks() +
      "</div>" +
      '<div><h4 class="footer__title">Soluções</h4><ul class="footer__list">' + productLinks() + "</ul></div>" +
      site.footer.columns
        .map(function (col) {
          return '<div><h4 class="footer__title">' + col.title + '</h4><ul class="footer__list">' +
            linkList(col.links) + "</ul></div>";
        })
        .join("") +
      "</div>" +
      '<div class="footer__bottom">' +
      "<span>&copy; " + year + " " + site.brand.nameUpper + ". Todos os direitos reservados.</span>" +
      "<span>Uma solução <strong>" + site.brand.parent + "</strong>" +
      (contactLinks.length ? " &middot; <a href=\"" + contactLinks[0].url + "\">" + contactLinks[0].label + "</a>" : "") +
      "</span>" +
      "</div>" +
      "</div>";
  }

  global.VC = global.VC || {};
  global.VC.renderFooter = render;
})(window);
