/* =============================================================
   Janela modal — usada por formulários e confirmações.
   Prende o foco enquanto aberta e fecha no Esc.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;
  var caixa = null;
  var focoAnterior = null;

  function garantir() {
    if (caixa) return caixa;
    caixa = document.createElement("div");
    caixa.className = "modal";
    caixa.setAttribute("role", "dialog");
    caixa.setAttribute("aria-modal", "true");
    document.body.appendChild(caixa);
    caixa.addEventListener("click", function (e) {
      if (e.target === caixa || e.target.closest("[data-fechar]")) fechar();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && caixa.classList.contains("is-open")) fechar();
    });
    return caixa;
  }

  function abrir(opcoes) {
    var o = opcoes || {};
    var box = garantir();
    focoAnterior = document.activeElement;
    box.setAttribute("aria-label", o.titulo || "Janela");
    VC.safe.render(box, html`
      <div class="modal__card">
        <div class="modal__head">
          <div>
            <h2>${o.titulo || ""}</h2>
            ${o.subtitulo ? html`<p class="muted" style="font-size:var(--fs-sm)">${o.subtitulo}</p>` : html.vazio}
          </div>
          <button class="btn btn--quiet btn--icon" type="button" data-fechar aria-label="Fechar">✕</button>
        </div>
        <div class="modal__body">${o.corpo || html.vazio}</div>
        <div class="modal__foot">
          <button class="btn btn--ghost" type="button" data-fechar>${o.cancelar || "Fechar"}</button>
          ${o.confirmar ? html`<button class="btn btn--accent" type="button" data-confirmar>${o.confirmar}</button>` : html.vazio}
        </div>
      </div>`);

    box.classList.add("is-open");
    document.body.style.overflow = "hidden";

    var primeiro = box.querySelector("input, select, textarea, button:not([data-fechar])");
    (primeiro || box.querySelector("[data-fechar]")).focus();

    if (o.aoConfirmar) {
      var b = box.querySelector("[data-confirmar]");
      if (b) b.addEventListener("click", function () { o.aoConfirmar(box); });
    }
  }

  function fechar() {
    if (!caixa) return;
    caixa.classList.remove("is-open");
    document.body.style.overflow = "";
    if (focoAnterior && focoAnterior.focus) focoAnterior.focus();
  }

  VC.modal = { abrir: abrir, fechar: fechar };
})(window);
