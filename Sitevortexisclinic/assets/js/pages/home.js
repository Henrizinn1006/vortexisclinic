/* =============================================================
   Home: grade de soluções + roadmap da seção de expansão.
   ============================================================= */
(function (global) {
  "use strict";

  function renderRoadmap(host) {
    if (!host) return;
    host.innerHTML = global.VC.content.roadmap
      .map(function (item) {
        return (
          '<li class="roadmap__item"><span class="roadmap__dot"></span>' +
          "<b>" + item.title + "</b><span>" + item.note + "</span></li>"
        );
      })
      .join("");
  }

  function init() {
    global.VC.renderProductGrid(document.querySelector("[data-component='product-grid']"));
    renderRoadmap(document.querySelector("[data-component='roadmap']"));
  }

  global.VC = global.VC || {};
  global.VC.pages = global.VC.pages || {};
  global.VC.pages.home = { init: init };
})(window);
