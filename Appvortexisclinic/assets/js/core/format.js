/* =============================================================
   Formatação — moeda, datas, nomes. Tudo pt-BR em um lugar só.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var LOCALE = "pt-BR";

  var moeda = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "BRL" });
  var diaSemanaCurto = new Intl.DateTimeFormat(LOCALE, { weekday: "short" });
  var diaMes = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit" });
  var dataLonga = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "long", year: "numeric" });
  var mesAno = new Intl.DateTimeFormat(LOCALE, { month: "long", year: "numeric" });

  function toDate(v) { return v instanceof Date ? v : new Date(v); }

  function hoje() {
    var d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function mesmoDia(a, b) {
    a = toDate(a); b = toDate(b);
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function diasEntre(a, b) {
    return Math.round((toDate(b).setHours(0, 0, 0, 0) - toDate(a).setHours(0, 0, 0, 0)) / 86400000);
  }

  /* "Hoje", "Amanhã", "Ontem" ou 12/09 */
  function dataRelativa(v) {
    var d = diasEntre(hoje(), v);
    if (d === 0) return "Hoje";
    if (d === 1) return "Amanhã";
    if (d === -1) return "Ontem";
    return diaMes.format(toDate(v));
  }

  function hora(v) {
    var d = toDate(v);
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function duracao(min) {
    if (min < 60) return min + " min";
    var h = Math.floor(min / 60), m = min % 60;
    return m ? h + "h" + String(m).padStart(2, "0") : h + "h";
  }

  /* Iniciais para avatar e para o modo privacidade */
  function iniciais(nome) {
    var partes = String(nome || "").trim().split(/\s+/);
    if (!partes[0]) return "--";
    var a = partes[0][0] || "";
    var b = partes.length > 1 ? partes[partes.length - 1][0] : "";
    return (a + b).toUpperCase();
  }

  /* Primeiro nome + inicial do sobrenome: usado em telas que podem
     ser vistas de relance por terceiros (dashboard, agenda). */
  function nomeCurto(nome) {
    var partes = String(nome || "").trim().split(/\s+/);
    if (partes.length < 2) return partes[0] || "";
    return partes[0] + " " + partes[partes.length - 1][0] + ".";
  }

  function capitalizar(s) {
    s = String(s || "");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  /* Para <input type="datetime-local">: o campo espera o horário
     LOCAL sem fuso ("2026-09-30T14:00"), e não ISO com Z. */
  function paraCampoDataHora(v) {
    var d = toDate(v);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
           "T" + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function dataHora(v) {
    var d = toDate(v);
    return diaMes.format(d) + " às " + hora(d);
  }

  VC.fmt = {
    paraCampoDataHora: paraCampoDataHora,
    dataHora: dataHora,
    moeda: function (v) { return moeda.format(v || 0); },
    numero: function (v) { return new Intl.NumberFormat(LOCALE).format(v || 0); },
    porcento: function (v) { return Math.round(v || 0) + "%"; },
    diaSemana: function (v) { return capitalizar(diaSemanaCurto.format(toDate(v)).replace(".", "")); },
    diaMes: function (v) { return diaMes.format(toDate(v)); },
    dataLonga: function (v) { return dataLonga.format(toDate(v)); },
    mesAno: function (v) { return capitalizar(mesAno.format(toDate(v))); },
    dataRelativa: dataRelativa,
    hora: hora,
    duracao: duracao,
    iniciais: iniciais,
    nomeCurto: nomeCurto,
    capitalizar: capitalizar,
    hoje: hoje,
    mesmoDia: mesmoDia,
    diasEntre: diasEntre,
    toDate: toDate
  };
})(window);
