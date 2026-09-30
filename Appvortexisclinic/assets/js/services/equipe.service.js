/* =============================================================
   Equipe — quem está na conta e quem foi convidado.

     GET   /workspace/team
     POST  /workspace/invitations
     POST  /workspace/invitations/{id}/revoke
     PATCH /workspace/members/{id}
     GET   /invitations/{token}            (público)
     POST  /invitations/{token}/accept     (público)

   Duas observações que valem para quem mexer aqui.

   **O link do convite volta uma vez só.** Ele vem na resposta da
   criação e some — o servidor guarda só o hash do token. Se a
   pessoa fechar a janela sem copiar, o caminho é revogar e
   convidar de novo. É o mesmo desenho da redefinição de senha.

   **Aceitar não escolhe acesso.** Papel, escopo e profissão vêm
   decididos do convite; o corpo do aceite carrega, no máximo, nome
   e senha de quem ainda não tem conta. Mandar "papel" aqui não faz
   nada — e existe teste no servidor provando isso.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});
  var base = VC.services._base;
  var mapa = VC.mapa;

  VC.services.equipe = {
    listar: function () {
      return base.buscar("/workspace/team").then(function (r) {
        return {
          membros: (r.membros || []).map(mapa.membro),
          convites: (r.convites || []).map(mapa.convite)
        };
      });
    },

    convidar: function (dados) {
      dados = dados || {};
      return base.enviar("post", "/workspace/invitations", {
        email: dados.email,
        papel: dados.papel || "PROFESSIONAL",
        escopo: dados.escopo || null,
        profissao: dados.profissao || null,
        mensagem: dados.mensagem || null
      }).then(mapa.convite);
    },

    revogar: function (id) {
      return base.enviar("post",
        "/workspace/invitations/" + encodeURIComponent(id) + "/revoke", {}).then(mapa.convite);
    },

    alterar: function (id, dados) {
      return base.enviar("patch", "/workspace/members/" + encodeURIComponent(id), {
        papel: dados.papel || null,
        escopo: dados.escopo || null,
        status: dados.status || null
      }).then(mapa.membro);
    },

    /* ---------- aceite: fora do painel, sem workspace ativo ----------
       Estas duas NÃO passam por `escopado()`: elas existem
       justamente para quem ainda não tem conta nem sessão. */
    verConvite: function (token) {
      return VC.api.get("/invitations/" + encodeURIComponent(token))
        .then(mapa.convitePublico);
    },

    aceitar: function (token, dados) {
      dados = dados || {};
      var corpo = {};
      if (dados.nome) corpo.nome = dados.nome;
      if (dados.senha) corpo.senha = dados.senha;
      return VC.api.post("/invitations/" + encodeURIComponent(token) + "/accept", corpo);
    }
  };
})(window);
