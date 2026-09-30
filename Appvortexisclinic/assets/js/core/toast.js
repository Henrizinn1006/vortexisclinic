/* =============================================================
   Avisos rápidos de ação (salvo, erro, desfazer).
   Anuncia por aria-live para leitores de tela.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var caixa = null;

  function garantirCaixa() {
    if (caixa) return caixa;
    caixa = document.createElement("div");
    caixa.className = "toasts";
    caixa.setAttribute("role", "status");
    caixa.setAttribute("aria-live", "polite");
    document.body.appendChild(caixa);
    return caixa;
  }

  function mostrar(titulo, detalhe, tipo, ms) {
    var box = garantirCaixa();
    var t = document.createElement("div");
    t.className = "toast" + (tipo ? " toast--" + tipo : "");
    var html = VC.safe.html;
    VC.safe.render(t, html`<div><b>${titulo}</b>${detalhe ? html`<span>${detalhe}</span>` : html.vazio}</div>`);
    box.appendChild(t);

    global.setTimeout(function () {
      t.classList.add("is-out");
      global.setTimeout(function () { t.remove(); }, 220);
    }, ms || 3200);
  }

  VC.toast = {
    info: function (t, d) { mostrar(t, d, "", 3200); },
    ok: function (t, d) { mostrar(t, d, "ok", 3200); },
    aviso: function (t, d) { mostrar(t, d, "warn", 4200); },
    erro: function (t, d) { mostrar(t, d, "danger", 5000); }
  };
})(window);
