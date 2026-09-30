/* =============================================================
   Estado da aplicação — objeto simples com assinatura de mudanças.
   Guarda só preferências de interface e caches curtos; dados de
   negócio ficam nos services.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var CHAVE = "vc.clinic.ui";

  var estado = {
    privacidade: false,       // borra nomes em tela (consultório compartilhado)
    menuAberto: false,
    ultimaRota: null
  };

  var ouvintes = [];

  function carregar() {
    try {
      var salvo = JSON.parse(localStorage.getItem(CHAVE) || "{}");
      if (typeof salvo.privacidade === "boolean") estado.privacidade = salvo.privacidade;
    } catch (e) { /* localStorage indisponível: segue com o padrão */ }
  }

  function persistir() {
    try {
      localStorage.setItem(CHAVE, JSON.stringify({ privacidade: estado.privacidade }));
    } catch (e) { /* ignora */ }
  }

  function get(chave) { return chave ? estado[chave] : estado; }

  function set(chave, valor) {
    if (estado[chave] === valor) return;
    estado[chave] = valor;
    persistir();
    ouvintes.forEach(function (fn) { fn(chave, valor, estado); });
  }

  function subscribe(fn) {
    ouvintes.push(fn);
    return function () { ouvintes = ouvintes.filter(function (f) { return f !== fn; }); };
  }

  carregar();
  VC.store = { get: get, set: set, subscribe: subscribe };
})(window);
