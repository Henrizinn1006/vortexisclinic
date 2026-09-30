/* =============================================================
   MÉTRICAS — auxiliares de apresentação
   -------------------------------------------------------------
   ATENÇÃO, mudou na etapa 4: a AUTORIDADE dos números é o
   servidor (`app/domain/metrics.py`). Recebido, pendente,
   presença, resumo do dia e da semana chegam calculados da API —
   é o que impede tela e relatório divergirem.

   O que continua aqui são derivações sobre uma lista que a tela
   JÁ tem em mãos: filtrar cancelados, somar o que está visível,
   contar por status. As definições são as mesmas do servidor, de
   propósito, e há teste dos dois lados com o mesmo exemplo para
   que não se soltem uma da outra.

   Regras (iguais às do backend):
   - cancelado não conta em volume nem em receita;
   - presença = realizados / (realizados + faltas);
   - isento não é receita nem pendência.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  var STATUS_CANCELADO = "cancelado";
  var STATUS_REALIZADO = "realizado";
  var STATUS_FALTA = "falta";

  function data(a) { return a.inicio instanceof Date ? a.inicio : new Date(a.inicio); }
  function ativos(lista) { return lista.filter(function (a) { return a.status !== STATUS_CANCELADO; }); }
  function soma(lista) { return lista.reduce(function (s, a) { return s + (a.valor || 0); }, 0); }
  function mesmoDia(a, b) {
    a = a instanceof Date ? a : new Date(a); b = b instanceof Date ? b : new Date(b);
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  /* ---------- Contagens ---------- */
  function contagens(lista) {
    return {
      total: ativos(lista).length,
      agendados: lista.filter(function (a) { return a.status === "agendado" || a.status === "confirmado"; }).length,
      realizados: lista.filter(function (a) { return a.status === STATUS_REALIZADO; }).length,
      faltas: lista.filter(function (a) { return a.status === STATUS_FALTA; }).length,
      cancelados: lista.filter(function (a) { return a.status === STATUS_CANCELADO; }).length
    };
  }

  /* ---------- Presença ---------- */
  function presenca(realizados, faltas) {
    var base = realizados + faltas;
    return base ? Math.round((realizados / base) * 100) : null;
  }

  function presencaDe(lista) {
    var c = contagens(lista);
    return presenca(c.realizados, c.faltas);
  }

  /* ---------- Dinheiro ---------- */
  function receita(lista, agora) {
    agora = agora || new Date();
    var validos = ativos(lista);
    var pagos = validos.filter(function (a) { return a.pagamento === "pago"; });
    var vencidos = validos.filter(function (a) { return a.pagamento === "pendente" && data(a) < agora; });
    var futuros = validos.filter(function (a) { return a.pagamento === "pendente" && data(a) >= agora; });

    var recebido = soma(pagos);
    var pendente = soma(vencidos);
    var previsto = soma(futuros);

    return {
      recebido: recebido,
      pendente: pendente,
      previsto: previsto,
      total: recebido + pendente + previsto,
      quantidadeRecebida: pagos.length,
      quantidadePendente: vencidos.length
    };
  }

  function percentualMeta(recebido, meta) {
    if (!meta) return null;
    return Math.min(100, Math.round((recebido / meta) * 100));
  }

  function variacao(atual, anterior) {
    if (!anterior) return null;
    return Math.round(((atual - anterior) / anterior) * 100);
  }

  /* ---------- Recortes de período ---------- */
  function resumoDoDia(lista, agora) {
    agora = agora || new Date();
    var doDia = ativos(lista);
    var c = contagens(lista);
    return {
      total: doDia.length,
      realizados: c.realizados,
      faltas: c.faltas,
      restantes: doDia.filter(function (a) { return data(a) >= agora; }).length,
      previsto: soma(doDia)
    };
  }

  function resumoDaSemana(lista, inicioSemana) {
    var dias = [];
    for (var i = 0; i < 7; i++) {
      var d = new Date(inicioSemana);
      d.setDate(d.getDate() + i);
      var doDia = lista.filter(function (a) { return mesmoDia(data(a), d); });
      var c = contagens(doDia);
      dias.push({
        data: d,
        total: c.total,
        realizados: c.realizados,
        faltas: c.faltas,
        cancelados: c.cancelados,
        hoje: mesmoDia(d, new Date())
      });
    }
    var geral = contagens(lista);
    return {
      inicio: inicioSemana,
      fim: dias[6].data,
      dias: dias,
      agendados: geral.total,
      realizados: geral.realizados,
      faltas: geral.faltas,
      cancelados: geral.cancelados,
      presenca: presenca(geral.realizados, geral.faltas)
    };
  }

  /* ---------- Pendências ---------- */
  function emAberto(lista, agora) {
    agora = agora || new Date();
    return ativos(lista).filter(function (a) {
      return a.pagamento === "pendente" && data(a) < agora;
    });
  }

  function diasEmAberto(atendimento, agora) {
    agora = agora || new Date();
    var ms = agora.setHours(0, 0, 0, 0) - new Date(data(atendimento)).setHours(0, 0, 0, 0);
    return Math.max(0, Math.round(ms / 86400000));
  }

  function totalEmAberto(lista) { return soma(lista); }

  /* ---------- Por pessoa atendida ---------- */
  function resumoDoCliente(lista, agora) {
    agora = agora || new Date();
    var passados = lista.filter(function (a) { return data(a) < agora; });
    var futuros = ativos(lista)
      .filter(function (a) { return data(a) >= agora; })
      .sort(function (a, b) { return data(a) - data(b); });
    var c = contagens(passados);
    var abertos = emAberto(lista, agora);

    return {
      total: lista.length,
      realizados: c.realizados,
      faltas: c.faltas,
      cancelados: c.cancelados,
      presenca: passados.length ? presenca(c.realizados, c.faltas) : null,
      ultimo: passados.length ? passados[passados.length - 1] : null,
      proximo: futuros.length ? futuros[0] : null,
      valorEmAberto: soma(abertos),
      atendimentosEmAberto: abertos.length
    };
  }

  VC.domain = VC.domain || {};
  VC.domain.metrics = {
    ativos: ativos,
    soma: soma,
    contagens: contagens,
    presenca: presenca,
    presencaDe: presencaDe,
    receita: receita,
    percentualMeta: percentualMeta,
    variacao: variacao,
    resumoDoDia: resumoDoDia,
    resumoDaSemana: resumoDaSemana,
    emAberto: emAberto,
    diasEmAberto: diasEmAberto,
    totalEmAberto: totalEmAberto,
    resumoDoCliente: resumoDoCliente
  };
})(window);
