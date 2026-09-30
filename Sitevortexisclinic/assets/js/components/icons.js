/* =============================================================
   Ícones — apenas os funcionais.
   A interface não usa ícones decorativos: a hierarquia é feita
   com tipografia, numeração e réguas de acento.
   Aqui ficam só o "fechar" do modal e as marcas das redes sociais.
   ============================================================= */
(function (global) {
  "use strict";

  var P = {
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    instagram:
      '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="3.6"/><path d="M17 7h.01"/>',
    linkedin:
      '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 10.5V17M8 7.5v.01M12 17v-3.6a2 2 0 0 1 4 0V17"/>',
    facebook: '<path d="M14 8.5V7a1.5 1.5 0 0 1 1.5-1.5H17V2.5h-2.5A4.5 4.5 0 0 0 10 7v1.5H7.5V12H10v9.5h4V12h2.6l.4-3.5H14Z"/>',
    youtube:
      '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="m10.5 9.5 4.5 2.5-4.5 2.5v-5Z"/>',
    whatsapp:
      '<path d="M3.5 20.5 5 16.4A8 8 0 1 1 8.2 19.4l-4.7 1.1Z"/><path d="M9 9.5c.4 2.2 2.3 4.1 4.5 4.5l1-1.3 1.8.8"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6 8.5-6"/>'
  };

  function icon(name, className) {
    var path = P[name];
    if (!path) return "";
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' +
      (className ? ' class="' + className + '"' : "") +
      ">" + path + "</svg>"
    );
  }

  global.VC = global.VC || {};
  global.VC.icon = icon;
  global.VC.hasIcon = function (name) { return !!P[name]; };
})(window);
