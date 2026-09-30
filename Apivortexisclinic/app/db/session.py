"""
Sessão do banco + o filtro de tenant.

O ponto central desta etapa está aqui: qualquer SELECT que toque uma tabela
marcada como `TenantScoped` recebe, automaticamente, `WHERE tenant_id = :ctx`.
Se não houver tenant no contexto, a consulta **não roda** — levanta
TenantContextError. É o fail-closed exigido na arquitetura: esquecer o filtro
não vaza dado, quebra.
"""
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from app.config import settings
from app.db.base import TenantScoped
from app.db.context import escopo_desligado, tenant_atual, TenantContextError

log = logging.getLogger("vc.db")


def _connect_args() -> dict:
    args: dict = {"charset": "utf8mb4"}
    if settings.VC_DB_SSL_CA:
        args["ssl"] = {"ca": settings.VC_DB_SSL_CA}
    return args


engine = create_engine(
    settings.database_url,
    echo=settings.VC_DB_ECHO,
    pool_pre_ping=True,
    pool_size=settings.VC_DB_POOL_SIZE,
    pool_recycle=settings.VC_DB_POOL_RECYCLE,
    future=True,
    connect_args=_connect_args(),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


_AUSENTE = object()


def _tenant_do_escopo(state):
    """De onde sai o tenant desta consulta.

    Primeiro a própria sessão do ORM (`db.info`), depois o contextvar.

    A ordem importa: no FastAPI, dependência síncrona roda numa thread do
    pool e a rota em OUTRA. Contextvar não atravessa isso — mas o objeto
    Session é o mesmo durante toda a requisição. Por isso o escopo mora
    na sessão, que é a unidade de trabalho de verdade. O contextvar
    continua valendo para código fora de requisição: teste, seed, rotina.
    """
    tid = state.session.info.get("tenant_id", _AUSENTE)
    if tid is not _AUSENTE:
        return tid                       # inclusive None: "sem tenant" é decisão, não descuido
    return tenant_atual()


@event.listens_for(Session, "do_orm_execute")
def _aplicar_filtro_de_tenant(state):
    """Roda em TODA consulta ORM desta aplicação."""
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if escopo_desligado():
        return  # escotilha explícita (migration/seed), nunca endpoint de produto

    if not _consulta_toca_tenant(state):
        return

    tid = _tenant_do_escopo(state)
    if tid is None:
        # Nunca devolver tudo: quebrar é o comportamento correto.
        raise TenantContextError(
            "consulta em tabela tenant-scoped sem tenant no contexto"
        )

    # O valor precisa ser lido ANTES da lambda: o SQLAlchemy extrai
    # variáveis de closure como parâmetro ligado, mas não executa funções
    # dentro da expressão. Ler aqui também deixa explícito que o tenant é
    # o do contexto no momento da consulta.
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tid,
            include_aliases=True,
        )
    )


def _consulta_toca_tenant(state) -> bool:
    """True quando alguma entidade da consulta é tenant-scoped."""
    for desc in state.all_mappers:
        if issubclass(desc.class_, TenantScoped):
            return True
    return False


def definir_escopo(db: Session, tenant_id) -> None:
    """Amarra a sessão do ORM a um tenant (ou a nenhum, explicitamente)."""
    db.info["tenant_id"] = tenant_id


def get_db():
    """Dependência do FastAPI: uma sessão por requisição, sempre fechada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
