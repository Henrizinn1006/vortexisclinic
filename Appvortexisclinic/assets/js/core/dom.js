/* =============================================================
   Utilidades de DOM. Sem framework: só o mínimo que o painel usa.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  function el(sel, ctx) { return (ctx || document).querySelector(sel); }
  function els(sel, ctx) { return [].slice.call((ctx || document).querySelectorAll(sel)); }

  /* Escapa texto vindo de dados antes de entrar em HTML.
     Todo dado de paciente passa por aqui. */
  function esc(v) {
    if (v === null || v === undefined) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* Delegação de eventos: on(container, 'click', '[data-x]', fn) */
  function on(root, type, sel, handler) {
    (root || document).addEventListener(type, function (e) {
      var alvo = e.target.closest(sel);
      if (alvo && (root || document).contains(alvo)) handler(e, alvo);
    });
  }

  /* Mantido por compatibilidade: delega para a renderização segura,
     que recusa string crua. Prefira VC.safe.render diretamente. */
  function setHTML(node, conteudo) {
    return VC.safe.render(node, conteudo);
  }

  VC.dom = { el: el, els: els, esc: esc, on: on, setHTML: setHTML };
})(window);
