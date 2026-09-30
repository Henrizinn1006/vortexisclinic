/* =============================================================
   Marca Vortexis Clinic.
   Os arquivos ficam em assets/images/ e são usados SÓ por aqui —
   para trocar a logo do site inteiro, basta mexer neste componente.
     simbolo.png ............ vórtice (header, favicon, ícones)
     simbolo-claro.png ...... vórtice clareado, para fundos escuros
     marca-texto.png ........ lettering em azul (fundos claros)
     marca-texto-branco.png . lettering em branco (fundos escuros)
     marca-completa.png ..... lockup vertical (compartilhamento/OG)
   ============================================================= */
(function (global) {
  "use strict";

  function img(file) {
    return global.VC.base() + "assets/images/" + file;
  }

  function logo(opts) {
    opts = opts || {};
    var site = global.VC.site;
    var href = opts.href || global.VC.url("home");
    var texto = opts.onDark ? "marca-texto-branco.png" : "marca-texto.png";
    var simbolo = opts.onDark ? "simbolo-claro.png" : "simbolo.png";

    return (
      '<a class="logo' + (opts.onDark ? " logo--on-dark" : "") + '" href="' + href + '" aria-label="' +
      site.brand.nameUpper + ' - início">' +
      '<img class="logo__mark" src="' + img(simbolo) + '" alt="" width="256" height="247" ' +
      'decoding="async">' +
      '<img class="logo__wordmark" src="' + img(texto) + '" alt="' + site.brand.name + '" ' +
      'width="639" height="110" decoding="async">' +
      "</a>"
    );
  }

  global.VC = global.VC || {};
  global.VC.logo = logo;
  global.VC.logoSrc = img;
})(window);
