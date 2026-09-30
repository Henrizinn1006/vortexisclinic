/* =============================================================
   RENDERIZAÇÃO SEGURA
   -------------------------------------------------------------
   Regra do projeto: nenhum dado dinâmico entra no DOM sem passar
   por aqui. Nada que venha do banco, da API ou do que o usuário
   digitou é confiável.

   Como funciona: `html` é uma tag de template que escapa TODA
   interpolação automaticamente. O resultado é um SafeHtml — e
   `render()` só aceita SafeHtml. Concatenar string crua e jogar
   no innerHTML deixa de compilar mentalmente: render() recusa.

       render(alvo, html`<h1>${nomeDoPaciente}</h1>`);

   Fragmentos já seguros (produzidos por outro componente) são
   interpolados sem escapar de novo, porque já são SafeHtml.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  function SafeHtml(valor) { this.value = valor; }
  SafeHtml.prototype.toString = function () { return this.value; };

  var MAPA = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" };

  function escapar(v) {
    return String(v).replace(/[&<>"'`]/g, function (c) { return MAPA[c]; });
  }

  /* Converte um valor interpolado em texto seguro. */
  function normalizar(v) {
    if (v instanceof SafeHtml) return v.value;
    if (v === null || v === undefined || v === false) return "";
    if (Array.isArray(v)) return v.map(normalizar).join("");
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    return escapar(v);
  }

  /* html`<p>${dado}</p>` -> SafeHtml */
  function html(partes) {
    var saida = partes[0];
    for (var i = 1; i < arguments.length; i++) {
      saida += normalizar(arguments[i]) + partes[i];
    }
    return new SafeHtml(saida);
  }

  /* Marca markup ESTÁTICO do próprio projeto como seguro.
     Só pode receber literal escrito por nós — nunca dado externo.
     Se receber algo que não seja string literal, falha. */
  html.estatico = function (markup) {
    if (typeof markup !== "string") throw new TypeError("html.estatico espera string literal");
    if (/\$\{/.test(markup)) throw new Error("html.estatico não aceita interpolação");
    return new SafeHtml(markup);
  };

  /* Junta uma lista de SafeHtml (map + join sem perder a marcação). */
  html.juntar = function (lista, separador) {
    return new SafeHtml(lista.map(normalizar).join(separador === undefined ? "" : normalizar(separador)));
  };

  html.vazio = new SafeHtml("");

  /* Valor para atributo: escapa e envolve em aspas.
     Uso: html`<div class=${attr(classe)}>` */
  function attr(v) {
    return new SafeHtml('"' + escapar(v === null || v === undefined ? "" : v) + '"');
  }

  /* Única porta de entrada para innerHTML no projeto. */
  function render(node, conteudo) {
    if (!node) return null;
    if (!(conteudo instanceof SafeHtml)) {
      throw new TypeError("render() só aceita html``. Recebeu: " + typeof conteudo);
    }
    node.innerHTML = conteudo.value;
    return node;
  }

  /* Texto puro: caminho preferido quando não há marcação envolvida. */
  function texto(node, valor) {
    if (node) node.textContent = valor === null || valor === undefined ? "" : String(valor);
    return node;
  }

  /* Criação por DOM API, para casos sem marcação estruturada. */
  function criar(tag, props, filhos) {
    var el = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "texto") el.textContent = String(v);
        else if (k === "dataset") Object.keys(v).forEach(function (d) { el.dataset[d] = v[d]; });
        else if (k.indexOf("on") === 0 && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
        else el.setAttribute(k, String(v));
      });
    }
    (filhos || []).forEach(function (f) {
      el.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return el;
  }

  VC.safe = {
    SafeHtml: SafeHtml,
    html: html,
    attr: attr,
    render: render,
    texto: texto,
    criar: criar,
    escapar: escapar,
    eSeguro: function (v) { return v instanceof SafeHtml; }
  };

  /* atalhos usados em todo o app */
  global.html = html;
  global.attr = attr;
})(window);
