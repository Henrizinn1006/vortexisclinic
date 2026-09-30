/* =============================================================
   Documentos — recibo, declaração, cópia do prontuário e anexo.

     GET  /workspace/clients/{id}/documents
     GET  /workspace/documents/{id}/content
     POST /workspace/clients/{id}/documents/receipt
     POST /workspace/clients/{id}/documents/attendance
     POST /workspace/clients/{id}/documents/record
     POST /workspace/clients/{id}/documents         (anexo)
     GET  /workspace/finance/export                 (CSV do caixa)

   **A classe do documento decide quem abre.** Recibo é
   administrativo (recepção emite, dono confere, porque é dinheiro);
   declaração, laudo e cópia de prontuário são clínicos. O servidor
   aplica a regra; o painel só esconde o que não adianta oferecer.

   **O arquivo nunca vira link.** O download é `fetch` com
   credenciais e Blob: o cookie viaja como nas outras chamadas, a URL
   do documento não entra no histórico, e erro chega como erro.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  /* Entrega o arquivo ao navegador e some com o objeto na sequência —
     Blob URL que fica viva é memória presa com conteúdo sensível. */
  function entregar(resultado, nomePadrao) {
    var url = global.URL.createObjectURL(resultado.blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = resultado.nome || nomePadrao || "documento";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    global.setTimeout(function () { global.URL.revokeObjectURL(url); }, 1000);
  }

  VC.services.documentos = {
    listar: function (pacienteId) {
      return base.buscar("/workspace/clients/" + encodeURIComponent(pacienteId) + "/documents")
        .then(function (lista) { return (lista || []).map(mapa.documento); });
    },

    baixar: function (documento) {
      return base.escopado(function () {
        return VC.api.baixar("/workspace/documents/" +
                             encodeURIComponent(documento.id) + "/content");
      }).then(function (r) { entregar(r, documento.nomeArquivo); return r; });
    },

    recibo: function (pacienteId, periodo) {
      periodo = periodo || {};
      return base.enviar("post",
        "/workspace/clients/" + encodeURIComponent(pacienteId) + "/documents/receipt", {
          de: periodo.de ? new Date(periodo.de).toISOString() : null,
          ate: periodo.ate ? new Date(periodo.ate).toISOString() : null
        }).then(mapa.documento);
    },

    declaracao: function (pacienteId, atendimentoId) {
      return base.enviar("post",
        "/workspace/clients/" + encodeURIComponent(pacienteId) + "/documents/attendance",
        { atendimento_id: atendimentoId }).then(mapa.documento);
    },

    exportarProntuario: function (pacienteId) {
      return base.enviar("post",
        "/workspace/clients/" + encodeURIComponent(pacienteId) + "/documents/record", {})
        .then(mapa.documento);
    },

    anexar: function (pacienteId, arquivo) {
      /* base64 em JSON, e não multipart: mantém uma única forma de
         falar com a API e o mesmo caminho de cifra no servidor. */
      return new Promise(function (resolve, reject) {
        var leitor = new FileReader();
        leitor.onerror = function () { reject(new Error("Não foi possível ler o arquivo.")); };
        leitor.onload = function () {
          var resultado = String(leitor.result || "");
          resolve(resultado.slice(resultado.indexOf(",") + 1));
        };
        leitor.readAsDataURL(arquivo);
      }).then(function (base64) {
        return base.enviar("post",
          "/workspace/clients/" + encodeURIComponent(pacienteId) + "/documents", {
            nome_arquivo: arquivo.name,
            conteudo_base64: base64,
            mime: arquivo.type || null
          }).then(mapa.documento);
      });
    },

    /* CSV do livro-caixa — para conferir com o extrato ou mandar ao contador. */
    exportarCaixa: function (periodo) {
      periodo = periodo || {};
      return base.escopado(function () {
        return VC.api.baixar("/workspace/finance/export" + base.query({
          de: periodo.de ? new Date(periodo.de).toISOString() : "",
          ate: periodo.ate ? new Date(periodo.ate).toISOString() : ""
        }));
      }).then(function (r) { entregar(r, "caixa.csv"); return r; });
    }
  };
})(window);
