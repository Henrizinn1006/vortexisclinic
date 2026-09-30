/* =============================================================
   Header + navegação (desktop e mobile).
   Renderiza em: <header class="site-header" data-component="header"></header>
   ============================================================= */
(function (global) {
  "use strict";

  function navLinks(items, extraClass) {
    return items
      .map(function (item) {
        var href = item.page ? global.VC.url(item.page) : global.VC.anchor(item.href);
        return '<a class="nav__link' + (extraClass || "") + '" href="' + href + '">' + item.label + "</a>";
      })
      .join("");
  }

  function authButtons(onMobile) {
    var site = global.VC.site;
    var size = onMobile ? "" : " btn--sm";
    if (site.features.auth) {
      return (
        '<a class="btn btn--ghost' + size + '" href="' + site.links.login + '">Entrar</a>' +
        '<a class="btn btn--primary' + size + '" href="' + site.links.signup + '">Criar conta</a>'
      );
    }
    /* Fase 1: presentes visualmente, ativados quando o app existir. */
    return (
      '<span class="btn btn--ghost' + size + '" aria-disabled="true" title="Disponível em breve">Entrar</span>' +
      '<a class="btn btn--primary' + size + '" href="' + global.VC.anchor("#solucoes") + '">Conhecer soluções</a>'
    );
  }

  function render(host) {
    var site = global.VC.site;

    host.innerHTML =
      '<div class="container site-header__inner">' +
      global.VC.logo({}) +
      '<nav class="nav header__desktop" aria-label="Navegação principal">' + navLinks(site.nav) + "</nav>" +
      '<div class="header__actions header__desktop">' + authButtons(false) + "</div>" +
      '<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav" aria-label="Abrir menu">' +
      "<span></span></button>" +
      "</div>" +
      '<nav class="mobile-nav" id="mobile-nav" aria-label="Navegação principal (celular)">' +
      navLinks(site.nav) +
      '<div class="mobile-nav__actions">' + authButtons(true) + "</div>" +
      "</nav>";

    var toggle = host.querySelector(".nav-toggle");
    var mobile = host.querySelector(".mobile-nav");

    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      toggle.setAttribute("aria-label", open ? "Abrir menu" : "Fechar menu");
      mobile.classList.toggle("is-open", !open);
    });

    mobile.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        toggle.setAttribute("aria-expanded", "false");
        mobile.classList.remove("is-open");
      }
    });

    var onScroll = function () {
      host.classList.toggle("is-stuck", global.scrollY > 8);
    };
    onScroll();
    global.addEventListener("scroll", onScroll, { passive: true });

    /* Destaque do item visivel (apenas na home) */
    var sections = [].slice.call(document.querySelectorAll("main section[id]"));
    if (sections.length && "IntersectionObserver" in global) {
      var links = [].slice.call(host.querySelectorAll('.nav__link[href*="#"]'));
      var obs = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            links.forEach(function (l) {
              l.classList.toggle("is-active", l.getAttribute("href").indexOf("#" + entry.target.id) > -1);
            });
          });
        },
        { rootMargin: "-45% 0px -50% 0px" }
      );
      sections.forEach(function (s) { obs.observe(s); });
    }
  }

  global.VC = global.VC || {};
  global.VC.renderHeader = render;
})(window);
