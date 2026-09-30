/* =============================================================
   Modal "Como instalar no celular" (tutorial PWA).
   Aberto por qualquer elemento com [data-open="pwa"].
   ============================================================= */
(function (global) {
  "use strict";

  var modal = null;
  var lastFocus = null;

  function build() {
    var c = global.VC.content.pwaTutorial;
    var el = document.createElement("div");
    el.className = "modal";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", c.title);
    el.innerHTML =
      '<div class="modal__card">' +
      '<div class="modal__head">' +
      '<button class="modal__close" type="button" aria-label="Fechar">' + global.VC.icon("close") + "</button>" +
      '<span class="eyebrow">Aplicativo</span>' +
      "<h3>" + c.title + "</h3>" +
      "<p>" + c.intro + "</p>" +
      "</div>" +
      '<div class="modal__cols">' +
      c.platforms
        .map(function (p) {
          return (
            "<div><h4>" + p.name + ' <span class="muted" style="font-weight:400">- ' + p.note + "</span></h4>" +
            '<ol class="modal__list">' +
            p.steps.map(function (s) { return "<li><span>" + s + "</span></li>"; }).join("") +
            "</ol></div>"
          );
        })
        .join("") +
      "</div>" +
      '<p class="muted" style="font-size:var(--fs-xs);margin:var(--sp-5) 0 0">' + c.footer + "</p>" +
      "</div>";
    document.body.appendChild(el);

    el.addEventListener("click", function (e) {
      if (e.target === el || e.target.closest(".modal__close")) close();
    });
    return el;
  }

  function open() {
    if (!modal) modal = build();
    lastFocus = document.activeElement;
    modal.classList.add("is-open");
    document.body.style.overflow = "hidden";
    var btn = modal.querySelector(".modal__close");
    if (btn) btn.focus();
  }

  function close() {
    if (!modal) return;
    modal.classList.remove("is-open");
    document.body.style.overflow = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function init() {
    document.addEventListener("click", function (e) {
      var trigger = e.target.closest('[data-open="pwa"]');
      if (trigger) {
        e.preventDefault();
        open();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  global.VC = global.VC || {};
  global.VC.pwaModal = { init: init, open: open, close: close };
})(window);
