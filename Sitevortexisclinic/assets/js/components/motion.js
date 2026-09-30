/* =============================================================
   MOTION — toda a animação do site em um lugar só.
   Nada aqui é essencial: sem JS (ou com "movimento reduzido"
   ligado no sistema) a página continua completa e estática.
   ============================================================= */
(function (global) {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var reduced =
    global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- utilidades ---------- */
  function all(sel, ctx) {
    return [].slice.call((ctx || doc).querySelectorAll(sel));
  }

  /* Aplica atraso em cascata nos irmãos de um mesmo grupo. */
  function stagger(items, step, base) {
    items.forEach(function (el, i) {
      el.style.setProperty("--anim-delay", (base || 0) + i * (step || 80) + "ms");
    });
  }

  /* ---------- 1. Revelação no scroll ---------- */
  function revealOnScroll() {
    var targets = all("[data-anim], .line-mask, .app-chart, .app-panel, .devices");
    if (!targets.length) return;

    if (!("IntersectionObserver" in global)) {
      targets.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }

    /* cascata automática entre irmãos que animam juntos */
    all(".grid, .trust-strip__grid, .contact-grid, .feature-grid, .other-products, .mark-list")
      .forEach(function (group) {
        var kids = all("[data-anim]", group).filter(function (k) { return k.parentNode === group; });
        if (kids.length > 1) stagger(kids, 85);
      });

    var obs = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          e.target.classList.add("is-in");
          obs.unobserve(e.target);
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.12 }
    );
    targets.forEach(function (el) { obs.observe(el); });

    /* rede de segurança: nada fica invisível se algo falhar */
    global.setTimeout(function () {
      targets.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < global.innerHeight * 1.2) el.classList.add("is-in");
      });
    }, 2200);
  }

  /* ---------- 2. Entrada do topo no carregamento ---------- */
  function heroIntro() {
    var hero = doc.querySelector(".hero");
    if (!hero) return;
    var seq = all("[data-intro]", hero);
    seq.forEach(function (el, i) {
      el.style.setProperty("--anim-delay", 120 + i * 110 + "ms");
    });
    global.requestAnimationFrame(function () {
      global.requestAnimationFrame(function () {
        seq.forEach(function (el) { el.classList.add("is-in"); });
      });
    });
  }

  /* ---------- 3. Contadores do mockup ---------- */
  function counters() {
    var els = all("[data-count]");
    if (!els.length) return;
    if (reduced || !("IntersectionObserver" in global)) {
      els.forEach(function (el) { el.textContent = el.getAttribute("data-count") + (el.getAttribute("data-suffix") || ""); });
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        obs.unobserve(el);
        var alvo = parseFloat(el.getAttribute("data-count"));
        var suf = el.getAttribute("data-suffix") || "";
        var pad = el.getAttribute("data-pad") === "true";
        var t0 = null;
        var dur = 1200;
        el.setAttribute("data-running", "1");
        function passo(ts) {
          if (!t0) t0 = ts;
          var p = Math.min((ts - t0) / dur, 1);
          var v = Math.round(alvo * (1 - Math.pow(1 - p, 3)));
          el.textContent = (pad && v < 10 ? "0" + v : v) + suf;
          if (p < 1) global.requestAnimationFrame(passo);
        }
        global.requestAnimationFrame(passo);
      });
    }, { threshold: 0.35 });
    els.forEach(function (el) { obs.observe(el); });

    /* se o observer não disparar, mostra o número final mesmo assim */
    global.setTimeout(function () {
      els.forEach(function (el) {
        if (!el.getAttribute("data-running")) {
          el.textContent = el.getAttribute("data-count") + (el.getAttribute("data-suffix") || "");
        }
      });
    }, 2600);
  }

  /* ---------- 4. Inclinação 3D do mockup ---------- */
  function tilt() {
    var alvo = doc.querySelector(".mockup");
    if (!alvo || reduced || !global.matchMedia("(hover: hover)").matches) return;

    var raf = null;
    alvo.addEventListener("mousemove", function (e) {
      if (raf) return;
      raf = global.requestAnimationFrame(function () {
        raf = null;
        var r = alvo.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        alvo.style.setProperty("--ry", (-4 + x * 9).toFixed(2) + "deg");
        alvo.style.setProperty("--rx", (2 - y * 7).toFixed(2) + "deg");
      });
    });
    alvo.addEventListener("mouseleave", function () {
      alvo.style.setProperty("--ry", "-4deg");
      alvo.style.setProperty("--rx", "2deg");
    });
  }

  /* ---------- 5. Brilho dos cards seguindo o cursor ---------- */
  function cardGlow() {
    if (reduced || !global.matchMedia("(hover: hover)").matches) return;
    doc.addEventListener("mousemove", function (e) {
      var card = e.target.closest && e.target.closest(".card--hover");
      if (!card) return;
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    }, { passive: true });
  }

  /* ---------- 6. Barra de progresso ---------- */
  function progress() {
    if (reduced) return;
    var bar = doc.createElement("div");
    bar.className = "progress-bar";
    doc.body.appendChild(bar);
    var ticking = false;
    function upd() {
      var h = doc.documentElement.scrollHeight - global.innerHeight;
      var p = h > 0 ? global.scrollY / h : 0;
      bar.style.transform = "scaleX(" + p.toFixed(4) + ")";
      ticking = false;
    }
    global.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; global.requestAnimationFrame(upd); }
    }, { passive: true });
    upd();
  }

  /* ---------- 7. Linha do roadmap preenchendo ---------- */
  function roadmapFill() {
    var lista = doc.querySelector("[data-component='roadmap']");
    if (!lista || reduced) return;
    var ticking = false;
    function upd() {
      var r = lista.getBoundingClientRect();
      var p = (global.innerHeight * 0.82 - r.top) / (r.height || 1);
      lista.style.setProperty("--fill", Math.max(0, Math.min(1, p)) * 100 + "%");
      ticking = false;
    }
    global.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; global.requestAnimationFrame(upd); }
    }, { passive: true });
    upd();
  }

  function init() {
    /* Sem IntersectionObserver o site fica estático, e não quebrado. */
    if (!("IntersectionObserver" in global)) return;
    root.classList.add("js-motion");
    try {
      revealOnScroll();
      heroIntro();
      counters();
      tilt();
      cardGlow();
      progress();
      roadmapFill();
    } catch (e) {
      root.classList.remove("js-motion");
    }
  }

  global.VC = global.VC || {};
  global.VC.motion = { init: init, stagger: stagger };
})(window);
