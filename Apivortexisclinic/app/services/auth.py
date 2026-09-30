"""
Cadastro, login e recuperação de senha.

O cadastro é uma transação só:

    usuário → workspace → membership OWNER → perfil profissional

Se qualquer passo falhar, nada fica. Não existe estado "tenant criado pela
metade": ou a conta nasce inteira, ou o e-mail continua livre.
"""
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import rbac
from app.config import settings
from app.db.context import sem_escopo_de_tenant
from app.ids import novo_ulid
from app.models.membership import Membership
from app.models.profession import Profession
from app.models.professional import Professional
from app.models.security import PasswordResetToken
from app.models.user import User
from app.security import passwords, tokens
from app.services import tenants as servico_tenants
from app.services.sessions import agora


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def buscar_por_email(db: Session, email: str) -> Optional[User]:
    return db.execute(
        select(User).where(User.email == normalizar_email(email))
    ).scalar_one_or_none()


def validar_senha(senha: str) -> None:
    from app.errors import dados_invalidos

    if len(senha or "") < settings.VC_PASSWORD_MIN_LENGTH:
        raise dados_invalidos(
            f"A senha precisa de pelo menos {settings.VC_PASSWORD_MIN_LENGTH} caracteres."
        )
    if senha.strip() == "":
        raise dados_invalidos("Senha inválida.")


def profissao_por_slug(db: Session, slug: Optional[str]) -> Optional[Profession]:
    if not slug:
        return None
    return db.execute(
        select(Profession).where(Profession.slug == slug, Profession.active.is_(True))
    ).scalar_one_or_none()


def criar_usuario(db: Session, *, nome: str, email: str, senha: str,
                  ja_normalizado: bool = False) -> User:
    """Cria a conta de pessoa, sem workspace.

    Existe separada de `cadastrar` porque quem entra por convite ganha uma
    conta e **nenhum** workspace próprio: o workspace dela é a conta que
    convidou. Juntar as duas coisas criaria um consultório fantasma para
    cada recepcionista contratada.
    """
    if not ja_normalizado:
        email = normalizar_email(email)
        validar_senha(senha)

    usuario = User(
        public_id=novo_ulid(),
        name=(nome or "").strip()[:120],
        email=email,
        password_hash=passwords.gerar_hash(senha),
        status="active",
        # Verificação de e-mail: a coluna existe e o fluxo entra na etapa
        # do envio de e-mail. Hoje a conta nasce utilizável.
        email_verified_at=None,
    )
    db.add(usuario)
    db.flush()
    return usuario


def cadastrar(
    db: Session,
    *,
    nome: str,
    email: str,
    senha: str,
    nome_workspace: str,
    tipo_workspace: str = "solo",
    profissao_slug: Optional[str] = None,
    conselho: Optional[str] = None,
    registro: Optional[str] = None,
) -> Tuple[User, Membership]:
    """Cria a conta inteira. Sem commit: a rota controla a transação."""
    from app.errors import conflito, dados_invalidos

    email = normalizar_email(email)
    validar_senha(senha)

    if buscar_por_email(db, email) is not None:
        # Aqui o vazamento é inevitável (a pessoa está criando a conta) e
        # aceitável: sem isso, não dá para explicar por que falhou.
        raise conflito("email_em_uso", "Já existe uma conta com este e-mail.")

    profissao = profissao_por_slug(db, profissao_slug)
    if profissao_slug and profissao is None:
        raise dados_invalidos("Profissão não reconhecida.")

    if profissao is not None and profissao.requires_council and not (registro or "").strip():
        raise dados_invalidos(
            f"{profissao.registration_label or 'Registro profissional'} é obrigatório para {profissao.name}."
        )

    usuario = criar_usuario(db, nome=nome, email=email, senha=senha, ja_normalizado=True)

    membership = servico_tenants.criar_workspace(
        db,
        user_id=usuario.id,
        nome=nome_workspace,
        tipo=tipo_workspace,
        profession_id=profissao.id if profissao else None,
    )

    preparar_titular(db, usuario, membership, profissao, conselho=conselho, registro=registro)
    return usuario, membership


def preparar_titular(db: Session, usuario: User, membership: Membership, profissao,
                     *, conselho: Optional[str] = None, registro: Optional[str] = None) -> None:
    """Dá ao titular que ATENDE o perfil profissional e o acesso clínico.

    Duas coisas acontecem aqui, e a segunda é a que importa para a
    arquitetura de privacidade:

    1. Nasce a linha em `professionals` — sem ela, `data_scope` e autoria
       de registro clínico não têm a quem se referir.
    2. Nasce a **concessão explícita** das permissões clínicas em
       `membership_permissions`, com motivo e autoria.

    O acesso clínico do dono não vem do papel: a matriz do OWNER continua
    sem nada da classe clínica, porque afrouxá-la para atender o caso do
    consultório de uma pessoa só apagaria a regra para todas as clínicas.
    Vem de uma linha que a auditoria mostra e que um UPDATE remove.

    Quem cria conta sem declarar profissão não recebe nada disto — e é
    assim que a recepção e o administrador continuam do lado de fora.
    """
    if profissao is None:
        return

    from app.services import billing
    from app.services import permissions as servico_permissoes

    billing.conferir_profissional(db, membership.tenant_id)

    # Professional é tenant-scoped: a escrita acontece com escopo
    # explicitamente desligado porque o tenant pode ter acabado de nascer
    # e ainda não haver contexto de requisição para ele.
    with sem_escopo_de_tenant():
        db.add(
            Professional(
                public_id=novo_ulid(),
                tenant_id=membership.tenant_id,
                membership_id=membership.id,
                profession_id=profissao.id,
                display_name=usuario.name,
                council=(conselho or profissao.council_label or None) if profissao.requires_council else None,
                registration_number=(registro or None) if profissao.requires_council else None,
                active=True,
            )
        )
        db.flush()

    servico_permissoes.conceder_clinicas_ao_titular(db, membership)
    db.flush()


def autenticar(db: Session, email: str, senha: str) -> Optional[User]:
    """Devolve o usuário quando as credenciais batem; None caso contrário.

    Quando o e-mail não existe, ainda assim gasta o tempo de um Argon2 —
    senão o relógio da resposta diz quais e-mails têm conta.
    """
    usuario = buscar_por_email(db, email)
    if usuario is None:
        passwords.gastar_tempo_equivalente(senha or "")
        return None

    if not passwords.conferir(usuario.password_hash, senha or ""):
        return None

    if usuario.status != "active":
        return None

    if passwords.precisa_rehash(usuario.password_hash):
        usuario.password_hash = passwords.gerar_hash(senha)

    usuario.last_login_at = agora()
    return usuario


# ---------------- recuperação de senha ----------------
def criar_token_de_reset(db: Session, usuario: User) -> str:
    from datetime import timedelta

    token = tokens.novo_token()
    db.add(
        PasswordResetToken(
            public_id=novo_ulid(),
            user_id=usuario.id,
            token_hash=tokens.hash_token(token),
            expires_at=agora() + timedelta(minutes=settings.VC_PASSWORD_RESET_TTL_MINUTES),
        )
    )
    db.flush()
    return token


def consumir_token_de_reset(db: Session, token: str) -> Optional[User]:
    registro = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == tokens.hash_token(token))
    ).scalar_one_or_none()
    if registro is None or registro.used_at is not None or registro.expires_at <= agora():
        return None
    registro.used_at = agora()
    return db.get(User, registro.user_id)


# ---------------- verificação de e-mail ----------------
def criar_token_de_verificacao(db: Session, usuario: User) -> str:
    """Token de confirmação de endereço. Mesmo desenho do reset de senha.

    Guarda o e-mail junto: se a pessoa trocar de endereço antes de clicar
    no link, o token deixa de valer — senão o clique confirmaria um
    endereço que já não é o dela.
    """
    from datetime import timedelta

    from app.models.email import EmailVerification

    token = tokens.novo_token()
    db.add(
        EmailVerification(
            public_id=novo_ulid(),
            user_id=usuario.id,
            email=usuario.email,
            token_hash=tokens.hash_token(token),
            expires_at=agora() + timedelta(hours=settings.VC_EMAIL_VERIFY_TTL_HOURS),
        )
    )
    db.flush()
    return token


def confirmar_email(db: Session, token: str) -> Optional[User]:
    """Consome o token e marca o e-mail como verificado.

    Devolve None para token errado, vencido, já usado, ou emitido para um
    endereço que não é mais o da conta. Um caso só de resposta: distinguir
    ajudaria apenas quem está testando links.
    """
    from app.models.email import EmailVerification

    registro = db.execute(
        select(EmailVerification).where(
            EmailVerification.token_hash == tokens.hash_token(token or ""))
    ).scalar_one_or_none()
    if registro is None or not registro.vigente(agora()):
        return None

    usuario = db.get(User, registro.user_id)
    if usuario is None or usuario.email != registro.email:
        return None

    registro.used_at = agora()
    usuario.email_verified_at = agora()
    db.flush()
    return usuario
