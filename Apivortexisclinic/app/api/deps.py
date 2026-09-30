"""
Dependências do FastAPI — onde a segurança de cada requisição é montada.

Ordem fixa, a mesma da arquitetura aprovada:

    1. autenticado?          → senão 401
    2. pertence ao tenant?   → senão 404 (nunca 403: 403 confirma existência)
    3. pode a ação?          → senão 403

O tenant ativo vem SEMPRE da linha da sessão no banco. Não existe caminho
em que um `tenant_id` enviado pelo navegador vire contexto.
"""
import ipaddress
from dataclasses import dataclass
from typing import Optional, Set

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import errors
from app.config import settings
from app.db import context
from app.db.session import definir_escopo, get_db
from app.models.membership import Membership
from app.models.user import User
from app.security import tokens as tk
from app.services import permissions as servico_permissoes
from app.services import sessions as servico_sessoes
from app.services import tenants as servico_tenants

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def ip_binario(request: Request) -> Optional[bytes]:
    cliente = request.client.host if request.client else None
    if not cliente:
        return None
    try:
        return ipaddress.ip_address(cliente).packed
    except ValueError:
        return None


@dataclass
class Contexto:
    """O que uma rota autenticada recebe pronto."""

    db: Session
    usuario: User
    sessao: object
    membership: Optional[Membership]
    permissoes: Set[str]
    # Perfil profissional da pessoa NESTA conta. None para quem não atende
    # (recepção, por exemplo) — e é isso que torna o escopo "own" vazio
    # para ela, em vez de virar "tudo" por acidente.
    professional_id: Optional[int] = None
    _fuso: object = None

    @property
    def tenant_id(self) -> Optional[int]:
        return self.membership.tenant_id if self.membership else None

    @property
    def fuso(self):
        """Fuso da conta. É ele que decide onde "hoje" começa.

        Lido uma vez por requisição e guardado: a conversão acontece na
        borda (rotas e domínio), nunca no meio de um cálculo.
        """
        if self._fuso is None:
            from app.services.settings import fuso_do_tenant

            self._fuso = fuso_do_tenant(self.db, self.tenant_id) if self.membership else None
        return self._fuso

    @property
    def escopo(self) -> str:
        return self.membership.data_scope if self.membership else "own"

    @property
    def ve_tudo(self) -> bool:
        return self.escopo == "all"

    def pode(self, permissao: str) -> bool:
        return permissao in self.permissoes


def _conferir_csrf(request: Request, sessao) -> None:
    """Double submit: cabeçalho precisa bater com o hash guardado na sessão."""
    if request.method in METODOS_SEGUROS:
        return
    enviado = request.headers.get("x-csrf-token", "")
    if not enviado or not tk.confere(enviado, sessao.csrf_hash):
        raise errors.csrf_invalido()


def sessao_atual(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.VC_SESSION_COOKIE_NAME, "")
    sessao = servico_sessoes.buscar_vigente(db, token)
    if sessao is None:
        raise errors.nao_autenticado()
    _conferir_csrf(request, sessao)
    servico_sessoes.tocar(db, sessao)
    db.commit()
    return sessao


def _limitar_escrita(request: Request, user_id: int) -> None:
    """Teto de escrita por pessoa, por minuto.

    Não é contenção de ataque — para isso existe o limite do login e a
    barreira na frente do servidor. É para uma automação com defeito (ou
    um botão que ficou preso) não encher o banco antes de alguém
    perceber. O teto é generoso de propósito: quem está atendendo e
    lançando pagamento não pode esbarrar nele.
    """
    if request.method in METODOS_SEGUROS:
        return
    from app.security.ratelimit import limitador

    permitido, espera = limitador.registrar_e_checar(
        f"escrita:{user_id}", settings.VC_RATE_LIMIT_WRITE, settings.VC_RATE_LIMIT_WRITE_WINDOW
    )
    if not permitido:
        raise errors.excesso_de_tentativas(espera)


def contexto(request: Request, db: Session = Depends(get_db)) -> Contexto:
    """Autenticação + contexto de tenant. Use em toda rota protegida."""
    sessao = sessao_atual(request, db)
    usuario = sessao.user
    if usuario is None or usuario.status != "active":
        raise errors.nao_autenticado()

    _limitar_escrita(request, usuario.id)

    context.definir_usuario(usuario.id)

    membership = None
    if sessao.active_tenant_id is not None:
        # Revalidar a cada requisição: a membership pode ter sido suspensa
        # depois que a sessão nasceu.
        membership = servico_tenants.membership_por_tenant_id(db, usuario.id, sessao.active_tenant_id)
        if membership is None:
            # Perdeu o vínculo: a sessão continua, o workspace sai.
            sessao.active_tenant_id = None
            db.commit()

    # O escopo vai para a sessão do ORM (atravessa o threadpool do FastAPI)
    # e também para o contextvar, que serve ao código fora de requisição.
    definir_escopo(db, membership.tenant_id if membership else None)
    context.definir_tenant(membership.tenant_id if membership else None)

    permissoes = servico_permissoes.efetivas(db, membership) if membership else set()

    # O perfil profissional é lido DEPOIS do escopo estar definido: a
    # consulta é tenant-scoped como qualquer outra.
    professional_id = None
    if membership is not None:
        from sqlalchemy import select

        from app.models.professional import Professional

        professional_id = db.execute(
            select(Professional.id).where(Professional.membership_id == membership.id)
        ).scalar_one_or_none()

    return Contexto(db=db, usuario=usuario, sessao=sessao, membership=membership,
                    permissoes=permissoes, professional_id=professional_id)


def com_tenant(ctx: Contexto = Depends(contexto)) -> Contexto:
    """Rota tenant-scoped: sem workspace ativo, não executa. Fail-closed."""
    if ctx.membership is None:
        raise errors.sem_contexto_de_tenant()
    return ctx


def exigir(permissao: str):
    """Dependência de permissão. `Depends(exigir("patients.read"))`."""

    def _dep(ctx: Contexto = Depends(com_tenant)) -> Contexto:
        if not ctx.pode(permissao):
            raise errors.sem_permissao(permissao)
        return ctx

    return _dep
