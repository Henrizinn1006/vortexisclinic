"""
Equipe: convidar, aceitar, e mexer no acesso de quem já está dentro.

Este arquivo é curto e cheio de recusa. É de propósito: gestão de acesso é
onde uma falha não aparece como erro, aparece como alguém lendo o que não
devia.

**As travas que valem a leitura**

1. **Ninguém convida para um lugar melhor do que o seu.** Só quem é OWNER
   convida outro OWNER. Quem administra sem ser dono pode montar equipe,
   não pode fabricar um par.

2. **A conta nunca fica sem dono.** Rebaixar, suspender ou remover o
   último OWNER ativo é recusado. Sem isso, um clique deixa a conta sem
   quem consiga administrá-la — e não há caminho de volta pela aplicação.

3. **Ninguém edita a própria membership.** Nem para se promover, nem para
   se rebaixar por engano. Mudança no próprio acesso passa por outra
   pessoa.

4. **Aceitar não escolhe nada.** Papel, escopo e profissão vêm decididos
   do convite. A rota de aceite não lê nenhum desses campos do corpo da
   requisição, então não existe forma de pedir mais do que foi oferecido.

5. **O convite é para um e-mail.** Aceitar logado com outra conta é
   recusado: link vazado não vira porta de entrada.
"""
from datetime import timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import errors, rbac
from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.profession import Profession
from app.models.professional import Professional
from app.models.user import User
from app.security import tokens as tk
from app.services import permissions as servico_permissoes
from app.services import tenants as servico_tenants
from app.services.sessions import agora

VALIDADE_DIAS = 7


# ---------------- leitura ----------------
def listar(db: Session, ctx) -> List[Tuple[Membership, User, Optional[Professional]]]:
    linhas = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == ctx.tenant_id)
        .order_by(Membership.id)
    ).all()

    perfis = {
        p.membership_id: p
        for p in db.execute(select(Professional)).scalars()
        if p.membership_id
    }
    return [(m, u, perfis.get(m.id)) for m, u in linhas]


def convites_abertos(db: Session, ctx) -> List[Invitation]:
    with sem_escopo_de_tenant():
        return list(db.execute(
            select(Invitation)
            .where(Invitation.tenant_id == ctx.tenant_id, Invitation.status == "pending")
            .order_by(Invitation.id.desc())
        ).scalars())


def _donos_ativos(db: Session, tenant_id: int) -> int:
    from app.models.rbac import Role

    return int(db.execute(
        select(func.count(Membership.id))
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.tenant_id == tenant_id,
               Membership.status == "active",
               Role.key == rbac.OWNER)
    ).scalar_one())


def _membership(db: Session, ctx, public_id: str) -> Membership:
    achada = db.execute(
        select(Membership).where(Membership.public_id == public_id,
                                 Membership.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()
    if achada is None:
        raise errors.nao_encontrado("membro")
    return achada


# ---------------- convidar ----------------
def convidar(db: Session, ctx, dados) -> Tuple[Invitation, str]:
    """Cria o convite e devolve (linha, token em claro).

    O token em claro sai daqui uma vez só — vai para o link e não volta a
    existir. Guardado fica o sha256.
    """
    from app.services import billing

    # O limite é conferido no CONVITE, não no aceite: recusar alguém que
    # já clicou no link seria a pior hora possível para descobrir isso.
    billing.conferir_membro(db, ctx.tenant_id)

    email = (dados.email or "").strip().lower()
    if "@" not in email:
        raise errors.dados_invalidos("E-mail inválido.")

    papel = (dados.papel or rbac.PROFESSIONAL).upper()
    if papel not in rbac.PAPEL_PERMISSOES:
        raise errors.dados_invalidos("Papel não reconhecido.")

    # Trava 1: só dono cria dono.
    if papel == rbac.OWNER and ctx.membership.role.key != rbac.OWNER:
        raise errors.sem_permissao()

    escopo = dados.escopo or ("all" if papel in (rbac.OWNER, rbac.ASSISTANT) else "own")
    if escopo not in ("all", "own"):
        raise errors.dados_invalidos("Escopo de dados não reconhecido.")

    profissao = None
    if dados.profissao:
        profissao = db.execute(
            select(Profession).where(Profession.slug == dados.profissao)
        ).scalar_one_or_none()
        if profissao is None:
            raise errors.dados_invalidos("Profissão não reconhecida.")

    with sem_escopo_de_tenant():
        # Já está dentro? Responder isso é seguro: quem convida administra
        # a conta e já enxerga a lista de membros.
        ja_dentro = db.execute(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == ctx.tenant_id, User.email == email)
        ).first()
        if ja_dentro:
            raise errors.conflito("ja_e_membro", "Esta pessoa já faz parte da conta.")

        pendente = db.execute(
            select(Invitation).where(Invitation.tenant_id == ctx.tenant_id,
                                     Invitation.email == email,
                                     Invitation.status == "pending")
        ).scalar_one_or_none()
        if pendente is not None and pendente.vigente(agora()):
            raise errors.conflito("convite_pendente",
                                  "Já existe um convite aberto para este e-mail.")
        if pendente is not None:
            pendente.status = "revoked"       # vencido: some para dar lugar ao novo
            pendente.revoked_at = agora()

        token = tk.novo_token()
        convite = Invitation(
            public_id=novo_ulid(),
            tenant_id=ctx.tenant_id,
            email=email,
            role_id=servico_tenants.papel(db, papel).id,
            data_scope=escopo,
            profession_id=profissao.id if profissao else None,
            token_hash=tk.hash_token(token),
            status="pending",
            expires_at=agora() + timedelta(days=VALIDADE_DIAS),
            invited_by_user_id=ctx.usuario.id,
            message=(dados.mensagem or None),
        )
        db.add(convite)
        db.flush()
    return convite, token


def revogar(db: Session, ctx, public_id: str) -> Invitation:
    with sem_escopo_de_tenant():
        convite = db.execute(
            select(Invitation).where(Invitation.public_id == public_id,
                                     Invitation.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if convite is None:
            raise errors.nao_encontrado("convite")
        if convite.status != "pending":
            raise errors.conflito("convite_encerrado", "Este convite já foi encerrado.")
        convite.status = "revoked"
        convite.revoked_at = agora()
    return convite


# ---------------- aceitar ----------------
def por_token(db: Session, token: str) -> Invitation:
    """Busca o convite pelo token. Vencido, usado ou revogado: não existe.

    Resposta única para todos os casos de propósito: quem tem um link
    quebrado não precisa saber se ele nunca existiu, se expirou ou se
    alguém já usou.
    """
    with sem_escopo_de_tenant():
        convite = db.execute(
            select(Invitation).where(Invitation.token_hash == tk.hash_token(token or ""))
        ).scalar_one_or_none()
    if convite is None or not convite.vigente(agora()):
        raise errors.nao_encontrado("convite")
    return convite


def aceitar(db: Session, convite: Invitation, usuario: User) -> Membership:
    """Cria a membership exatamente como o convite definiu.

    Nenhum campo de acesso vem de fora: papel, escopo e profissão saem da
    linha do convite. Pedir mais no corpo da requisição não tem onde
    encostar.
    """
    if usuario.email.strip().lower() != convite.email:
        # Convite é para um endereço. Link vazado não vira porta de entrada.
        raise errors.conflito("convite_de_outro_email",
                              "Este convite foi enviado para outro e-mail.")

    with sem_escopo_de_tenant():
        existente = db.execute(
            select(Membership).where(Membership.tenant_id == convite.tenant_id,
                                     Membership.user_id == usuario.id)
        ).scalar_one_or_none()
        if existente is not None:
            convite.status = "accepted"
            convite.accepted_at = agora()
            convite.accepted_user_id = usuario.id
            return existente

        membership = Membership(
            public_id=novo_ulid(),
            tenant_id=convite.tenant_id,
            user_id=usuario.id,
            role_id=convite.role_id,
            data_scope=convite.data_scope,
            status="active",
        )
        db.add(membership)
        db.flush()

        if convite.profession_id is not None:
            profissao = db.get(Profession, convite.profession_id)
            db.add(Professional(
                public_id=novo_ulid(),
                tenant_id=convite.tenant_id,
                membership_id=membership.id,
                profession_id=convite.profession_id,
                display_name=usuario.name,
                council=profissao.council_label if profissao and profissao.requires_council else None,
                active=True,
            ))
            db.flush()
            # Perfil profissional criado por convite recebe o mesmo acesso
            # clínico do titular que atende: concessão explícita, com
            # motivo — e nunca `read_others`.
            servico_permissoes.conceder_clinicas_ao_titular(db, membership)

        convite.status = "accepted"
        convite.accepted_at = agora()
        convite.accepted_user_id = usuario.id
        db.flush()
    return membership


# ---------------- mexer em quem já está dentro ----------------
def alterar(db: Session, ctx, public_id: str, dados) -> Membership:
    membership = _membership(db, ctx, public_id)

    # Trava 3: ninguém edita o próprio acesso.
    if membership.id == ctx.membership.id:
        raise errors.conflito("nao_edita_a_si",
                              "Mudança no seu próprio acesso precisa passar por outra pessoa.")

    if dados.papel is not None:
        papel = dados.papel.upper()
        if papel not in rbac.PAPEL_PERMISSOES:
            raise errors.dados_invalidos("Papel não reconhecido.")
        # Trava 1, de novo: promover a OWNER só quem já é OWNER.
        if papel == rbac.OWNER and ctx.membership.role.key != rbac.OWNER:
            raise errors.sem_permissao()
        membership.role_id = servico_tenants.papel(db, papel).id

    if dados.escopo is not None:
        if dados.escopo not in ("all", "own"):
            raise errors.dados_invalidos("Escopo de dados não reconhecido.")
        membership.data_scope = dados.escopo

    if dados.status is not None:
        if dados.status not in ("active", "suspended"):
            raise errors.dados_invalidos("Situação não reconhecida.")
        membership.status = dados.status

    db.flush()
    # O papel mudou por id; a relação carregada continuava apontando para o
    # papel antigo e a resposta sairia com o valor velho.
    db.refresh(membership)

    # Trava 2: a conta não fica sem dono ativo. A checagem é feita DEPOIS
    # da mudança, contando o resultado — assim ela pega qualquer caminho
    # (rebaixar, suspender, ou os dois na mesma chamada) sem precisar
    # adivinhar qual foi. A rota desfaz a transação ao receber o erro.
    if _donos_ativos(db, ctx.tenant_id) == 0:
        raise errors.conflito(
            "ultimo_dono",
            "A conta precisa de pelo menos um dono ativo. Promova outra pessoa antes.")

    return membership
