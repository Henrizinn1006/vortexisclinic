/* =============================================================
   FORMULÁRIOS
   -------------------------------------------------------------
   Peças de formulário em um lugar só, pelo mesmo motivo de sempre:
   quando cada tela monta o seu, a décima fica diferente das nove
   primeiras.

   Tudo aqui sai por `html``` — valor de campo, rótulo e opção de
   select são escapados. Nem um `innerHTML` com texto cru.

   A validação daqui é conforto: avisa antes de ir à rede. Quem
   valida de verdade é o servidor, que recusa de novo o que passar.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var html = VC.safe.html;

  function campo(o) {
    var valor = o.valor === null || o.valor === undefined ? "" : o.valor;
    var obrigatorio = o.obrigatorio !== false;

    var entrada;
    if (o.tipo === "textarea") {
      entrada = obrigatorio
        ? html`<textarea id="${o.nome}" name="${o.nome}" rows="${o.linhas || 3}" required>${valor}</textarea>`
        : html`<textarea id="${o.nome}" name="${o.nome}" rows="${o.linhas || 3}">${valor}</textarea>`;
    } else if (o.tipo === "select") {
      var opcoes = (o.opcoes || []).map(function (op) {
        return String(op.valor) === String(valor)
          ? html`<option value="${op.valor}" selected>${op.rotulo}</option>`
          : html`<option value="${op.valor}">${op.rotulo}</option>`;
      });
      entrada = html`<select id="${o.nome}" name="${o.nome}">${html.juntar(opcoes)}</select>`;
    } else {
      var tipo = o.tipo || "text";
      entrada = obrigatorio
        ? html`<input id="${o.nome}" name="${o.nome}" type="${tipo}" value="${valor}"
                 step="${o.passo || ""}" min="${o.minimo || ""}" autocomplete="off" required>`
        : html`<input id="${o.nome}" name="${o.nome}" type="${tipo}" value="${valor}"
                 step="${o.passo || ""}" min="${o.minimo || ""}" autocomplete="off">`;
    }

    return html`
      <label class="campo" for="${o.nome}">
        <span>${o.rotulo}${obrigatorio ? html`<i aria-hidden="true"> *</i>` : html.vazio}</span>
        ${entrada}
        ${o.dica ? html`<small>${o.dica}</small>` : html.vazio}
      </label>`;
  }

  function erro(mensagem) {
    return mensagem
      ? html`<div class="campo__erro" role="alert" data-erro>${mensagem}</div>`
      : html`<div data-erro hidden></div>`;
  }

  /* Lê o formulário inteiro. Campo vazio vira undefined, não "" —
     assim um PATCH não apaga o que a pessoa não quis mexer. */
  function valores(escopo) {
    var saida = {};
    VC.dom.els("input, select, textarea", escopo).forEach(function (el) {
      if (!el.name) return;
      var v = (el.value || "").trim();
      saida[el.name] = v === "" ? undefined : v;
    });
    return saida;
  }

  function mostrarErro(escopo, mensagem) {
    var alvo = VC.dom.el("[data-erro]", escopo);
    if (!alvo) return;
    alvo.hidden = !mensagem;
    alvo.className = mensagem ? "campo__erro" : "";
    VC.safe.texto(alvo, mensagem || "");
  }

  /* Mensagem de erro para a pessoa, a partir da resposta da API.
     Nunca mostra detalhe interno: o servidor já manda frase curta. */
  function mensagemDe(e) {
    if (!e) return "Não foi possível concluir.";
    if (e.status === 0) return "Sem conexão com o servidor.";
    if (e.code === "conflito_de_horario") {
      return "Já existe um atendimento desse profissional nesse horário.";
    }
    if (e.code === "transicao_invalida") return e.message || "Essa mudança não é possível.";
    if (e.status === 403) return "Seu acesso não permite esta ação.";
    if (e.status === 404) return "Não encontramos este registro.";
    if (e.status === 422) return e.message || "Confira os campos.";
    return e.message || "Não foi possível concluir.";
  }

  /* Data e hora do formulário -> Date. O navegador devolve
     "2026-09-30T14:00" no fuso local, que é o que a pessoa digitou. */
  function dataHora(valor) {
    if (!valor) return null;
    var d = new Date(valor);
    return isNaN(d.getTime()) ? null : d;
  }

  VC.form = {
    campo: campo,
    erro: erro,
    valores: valores,
    mostrarErro: mostrarErro,
    mensagemDe: mensagemDe,
    dataHora: dataHora
  };
})(window);
