"""
Contratos dos módulos de negócio.

O JSON fala português, como o resto da API — o inglês da decisão 5 vale para
tabela e código, não para a resposta. O painel consome estes nomes.

Valores em dinheiro saem como número (o `Decimal` vira float no JSON com
duas casas); datas saem em ISO 8601, sempre UTC.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.domain.calendario import normalizar_utc

# Toda data-hora de ENTRADA usa Instante, nunca `datetime` puro: o banco guarda
# DATETIME sem fuso, sempre UTC, e quem chama a API de fora do painel pode
# mandar `-03:00` ou `Z`. Campo novo de data-hora num modelo *In → Instante.
Instante = Annotated[datetime, AfterValidator(normalizar_utc)]

FREQUENCIAS = Literal["weekly", "biweekly", "monthly", "irregular"]
MODALIDADES = Literal["in_person", "online"]
STATUS_CLIENTE = Literal["active", "inactive", "archived"]
STATUS_ATENDIMENTO = Literal["scheduled", "confirmed", "done", "no_show", "cancelled"]
PAGAMENTOS = Literal["pending", "paid", "waived"]


# ---------------- entrada ----------------
class ClienteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=140)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=30)
    nascimento: Optional[date] = None
    frequencia: Optional[FREQUENCIAS] = "weekly"
    modalidade: Optional[MODALIDADES] = "in_person"
    valor_sessao: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    desde: Optional[date] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("nome")
    @classmethod
    def _limpar(cls, v: str) -> str:
        return " ".join(v.split())


class ClienteUpdateIn(BaseModel):
    """Tudo opcional: PATCH muda só o que veio."""

    nome: Optional[str] = Field(default=None, min_length=2, max_length=140)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=30)
    nascimento: Optional[date] = None
    frequencia: Optional[FREQUENCIAS] = None
    modalidade: Optional[MODALIDADES] = None
    valor_sessao: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    desde: Optional[date] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[Literal["active", "inactive"]] = None


class AtendimentoIn(BaseModel):
    cliente_id: str = Field(min_length=26, max_length=26)
    inicio: Instante
    duracao_min: Optional[int] = Field(default=50, ge=5, le=480)
    modalidade: Optional[MODALIDADES] = None
    valor: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    observacao: Optional[str] = Field(default=None, max_length=2000)
    # Só tem efeito para quem enxerga a conta toda; em escopo "own" o
    # profissional é sempre o próprio.
    profissional_id: Optional[str] = Field(default=None, min_length=26, max_length=26)


class AtendimentoUpdateIn(BaseModel):
    modalidade: Optional[MODALIDADES] = None
    valor: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    observacao: Optional[str] = Field(default=None, max_length=2000)


METODOS_PAGAMENTO = Literal["pix", "card", "cash", "transfer", "other"]


class BaixaIn(BaseModel):
    """Baixa de pagamento de um atendimento."""

    metodo: METODOS_PAGAMENTO
    # Vazio = agora. Serve para lançar no dia certo o que foi recebido ontem.
    pago_em: Optional[Instante] = None
    # Vazio = o valor do atendimento.
    valor: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("99999999.99"))
    observacao: Optional[str] = Field(default=None, max_length=200)


class MotivoIn(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=200)


class ReagendarIn(BaseModel):
    inicio: Instante
    duracao_min: Optional[int] = Field(default=None, ge=5, le=480)


class StatusIn(BaseModel):
    status: STATUS_ATENDIMENTO
    motivo: Optional[str] = Field(default=None, max_length=200)


# ---------------- saída ----------------
class ResumoClienteOut(BaseModel):
    total: int
    realizados: int
    faltas: int
    presenca: Optional[float] = None
    ultimo: Optional[datetime] = None
    proximo: Optional[datetime] = None
    valor_em_aberto: Decimal
    quantidade_em_aberto: int


class ClienteResumidoOut(BaseModel):
    id: str
    nome: str
    status: STATUS_CLIENTE


class ClienteOut(BaseModel):
    id: str
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    nascimento: Optional[date] = None
    status: STATUS_CLIENTE
    frequencia: FREQUENCIAS
    modalidade: MODALIDADES
    valor_sessao: Optional[Decimal] = None
    desde: Optional[date] = None
    observacao: Optional[str] = None
    # Preenchido quando o cadastro foi anonimizado a pedido do titular.
    # A tela precisa saber para não oferecer a ação de novo.
    anonimizado_em: Optional[datetime] = None
    resumo: Optional[ResumoClienteOut] = None


class AtendimentoOut(BaseModel):
    id: str
    inicio: datetime
    duracao_min: int
    modalidade: MODALIDADES
    status: STATUS_ATENDIMENTO
    valor: Optional[Decimal] = None
    pagamento: PAGAMENTOS
    metodo_pagamento: Optional[str] = None
    pago_em: Optional[datetime] = None
    observacao: Optional[str] = None
    cliente: ClienteResumidoOut
    profissional_id: str


class PendenciaOut(AtendimentoOut):
    dias_em_aberto: int


class PagamentoOut(BaseModel):
    id: str
    valor: Decimal
    metodo: METODOS_PAGAMENTO
    status: Literal["paid", "refunded"]
    pago_em: datetime
    observacao: Optional[str] = None
    estornado_em: Optional[datetime] = None
    motivo_estorno: Optional[str] = None
    cliente: ClienteResumidoOut
    atendimento_id: Optional[str] = None


class ContagemClientesOut(BaseModel):
    total: int
    ativos: int
    inativos: int
    arquivados: int


class ResumoDiaOut(BaseModel):
    total: int
    realizados: int
    faltas: int
    cancelados: int
    restantes: int
    previsto: Decimal
    presenca: Optional[float] = None


class DiaDaSemanaOut(BaseModel):
    data: date
    total: int
    realizados: int
    faltas: int
    hoje: bool


class ResumoSemanaOut(BaseModel):
    inicio: date
    fim: date
    dias: List[DiaDaSemanaOut]
    agendados: int
    realizados: int
    faltas: int
    presenca: Optional[float] = None


class ResumoFinanceiroOut(BaseModel):
    """Recebido é regime de CAIXA (data do pagamento).

    Pendente e previsto vêm do atendimento. Os dois recortes são do mesmo
    mês, por datas diferentes — ver `app/domain/metrics.py`.
    """

    referencia: date
    recebido: Decimal
    pendente: Decimal
    previsto: Decimal
    total: Decimal
    quantidade_recebida: int
    quantidade_pendente: int
    meta: Optional[Decimal] = None
    percentual_meta: Optional[float] = None
    variacao_mes_anterior: Optional[float] = None


class PontoDaSerieOut(BaseModel):
    mes: date
    valor: Decimal
    quantidade: int


class DashboardOut(BaseModel):
    """Tudo o que a tela inicial precisa, numa chamada só.

    Os números vêm calculados do servidor — é o que impede tela e
    relatório divergirem.
    """

    hoje: List[AtendimentoOut]
    resumo_dia: ResumoDiaOut
    proximos: List[AtendimentoOut]
    clientes: ContagemClientesOut
    financeiro: Optional[ResumoFinanceiroOut] = None
    pendencias: List[PendenciaOut]
    semana: ResumoSemanaOut


# ---------------- prontuário ----------------
TIPOS_NOTA = Literal["session", "assessment", "plan", "note"]
STATUS_NOTA = Literal["draft", "signed"]


class NotaIn(BaseModel):
    """Entrada do registro clínico.

    `conteudo` é texto puro — nada de HTML. A tela escreve e lê texto, e
    o painel renderiza com escape automático. Não existe caminho em que
    marcação vinda daqui vire elemento no navegador de alguém.
    """

    conteudo: str = Field(min_length=1, max_length=20000)
    tipo: Optional[TIPOS_NOTA] = "session"
    ocorrido_em: Optional[Instante] = None
    atendimento_id: Optional[str] = Field(default=None, max_length=26)


class NotaEdicaoIn(BaseModel):
    conteudo: str = Field(min_length=1, max_length=20000)
    # Obrigatório quando a nota já está assinada: adendo sem motivo é rasura.
    motivo: Optional[str] = Field(default=None, max_length=200)


class VersaoOut(BaseModel):
    """Metadado da versão. Conteúdo não sai por aqui — só em /content.

    Não tem autor porque não precisa: só o autor da nota escreve versões
    dela. Quem mais passou por ali aparece na trilha de acesso.
    """

    versao: int
    criado_em: datetime
    motivo: Optional[str] = None
    impressao: str


class NotaOut(BaseModel):
    id: str
    tipo: TIPOS_NOTA
    status: STATUS_NOTA
    ocorrido_em: datetime
    versao_atual: int
    assinada_em: Optional[datetime] = None
    conteudo_apagado_em: Optional[datetime] = None
    autor: Optional[str] = None
    autor_id: Optional[str] = None
    sou_o_autor: bool = False
    atendimento_id: Optional[str] = None
    cliente: Optional[ClienteResumidoOut] = None


class ConteudoOut(BaseModel):
    """A única resposta da API que carrega conteúdo clínico.

    Cache-Control: no-store vale para toda a API; aqui ele é o que separa
    "dado sensível na memória da aba" de "dado sensível no disco de quem
    usou o computador depois".
    """

    id: str
    versao: int
    conteudo: str
    impressao: str
    criado_em: datetime


class AcessoOut(BaseModel):
    """Uma linha da trilha. Nunca contém conteúdo."""

    id: str
    quando: datetime
    acao: str
    resultado: str
    motivo: Optional[str] = None
    quem: Optional[str] = None
    nota_id: Optional[str] = None


# ---------------- agenda: recorrência e bloqueios ----------------
FREQUENCIAS_SERIE = Literal["weekly", "biweekly", "monthly"]
TIPOS_BLOQUEIO = Literal["vacation", "holiday", "break", "other"]


class SerieIn(BaseModel):
    """Recorrência. O horizonte é finito de propósito.

    Recorrência infinita vira agenda infinita — e agenda infinita é agenda
    que ninguém consegue limpar depois.
    """

    cliente_id: str = Field(min_length=26, max_length=26)
    inicio: Instante
    frequencia: FREQUENCIAS_SERIE = "weekly"
    ocorrencias: int = Field(default=8, ge=1, le=52)
    ate: Optional[date] = None
    duracao_min: Optional[int] = Field(default=None, ge=10, le=480)
    modalidade: Optional[MODALIDADES] = None
    valor: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    profissional_id: Optional[str] = Field(default=None, max_length=26)
    observacao: Optional[str] = Field(default=None, max_length=200)


class EncerrarSerieIn(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=200)
    cancelar_futuros: bool = True


class ConflitoOut(BaseModel):
    """Ocorrência que não pôde ser criada — e por quê.

    A série não é recusada inteira por causa de um horário ocupado: as
    outras são criadas e esta volta aqui, para a pessoa decidir.
    """

    inicio: datetime
    motivo: str
    detalhe: Optional[str] = None


class SerieOut(BaseModel):
    id: str
    frequencia: FREQUENCIAS_SERIE
    inicio: datetime
    duracao_min: int
    modalidade: MODALIDADES
    valor: Optional[Decimal] = None
    ocorrencias: int
    ate: Optional[date] = None
    status: str
    cliente: Optional[ClienteResumidoOut] = None
    observacao: Optional[str] = None


class SerieCriadaOut(BaseModel):
    serie: SerieOut
    criados: List[AtendimentoOut]
    conflitos: List[ConflitoOut] = []


class BloqueioIn(BaseModel):
    inicio: Instante
    fim: Instante
    titulo: str = Field(min_length=1, max_length=120)
    tipo: TIPOS_BLOQUEIO = "other"
    profissional_id: Optional[str] = Field(default=None, max_length=26)
    # Sem isto, o bloqueio é da SUA agenda. Fechar a clínica inteira é
    # uma decisão que precisa ser dita — e exige enxergar a conta toda.
    conta_inteira: bool = False
    # Bloquear por cima de atendimento marcado exige confirmação — e
    # mesmo assim os atendimentos continuam de pé.
    forcar: bool = False


class BloqueioOut(BaseModel):
    id: str
    inicio: datetime
    fim: datetime
    titulo: str
    tipo: TIPOS_BLOQUEIO
    profissional_id: Optional[str] = None
    da_conta_inteira: bool = False


class BloqueioCriadoOut(BaseModel):
    bloqueio: BloqueioOut
    # Atendimentos que já estavam no período. Continuam marcados: o
    # sistema não cancela sessão de ninguém por conta própria.
    atendimentos_no_periodo: List[AtendimentoOut] = []


# ---------------- documentos ----------------
TIPOS_DOCUMENTO = Literal["receipt", "attendance", "report", "record_copy", "upload"]


class ReciboIn(BaseModel):
    """Recibo do que foi RECEBIDO no período — regime de caixa.

    Recibo é comprovante de dinheiro que entrou, não de atendimento que
    aconteceu. Vazio usa os últimos 30 dias.
    """

    de: Optional[Instante] = None
    ate: Optional[Instante] = None


class DeclaracaoIn(BaseModel):
    atendimento_id: str = Field(min_length=26, max_length=26)


class AnexoIn(BaseModel):
    nome_arquivo: str = Field(min_length=1, max_length=160)
    conteudo_base64: str = Field(min_length=4)
    mime: Optional[str] = Field(default=None, max_length=100)
    titulo: Optional[str] = Field(default=None, max_length=160)


class DocumentoOut(BaseModel):
    id: str
    tipo: TIPOS_DOCUMENTO
    classe: Literal["administrative", "clinical"]
    titulo: str
    nome_arquivo: str
    tamanho: int
    criado_em: datetime
    impressao: str
    conteudo_apagado_em: Optional[datetime] = None
    cliente: Optional[ClienteResumidoOut] = None


# ---------------- direitos do titular ----------------
TIPOS_CONSENTIMENTO = Literal["terms", "privacy", "clinical_treatment", "image", "communication"]
TIPOS_PEDIDO = Literal["access", "portability", "rectification", "erasure",
                       "restriction", "revoke_consent", "information"]
ALVOS_DE_DADO = Literal["registration", "appointments", "payments", "clinical",
                        "documents", "other"]
DECISOES = Literal["export", "anonymize", "erase", "keep", "restrict"]


class ConsentimentoIn(BaseModel):
    tipo: TIPOS_CONSENTIMENTO
    versao: Optional[str] = Field(default="1", max_length=40)
    # O texto apresentado. Não é guardado — só o sha256 dele, que é o que
    # prova QUAL texto foi aceito.
    texto: Optional[str] = Field(default=None, max_length=20000)
    em: Optional[Instante] = None
    origem: Optional[Literal["in_person", "online", "imported"]] = "in_person"
    observacao: Optional[str] = Field(default=None, max_length=300)


class ConsentimentoOut(BaseModel):
    id: str
    tipo: TIPOS_CONSENTIMENTO
    versao: str
    aceito_em: datetime
    revogado_em: Optional[datetime] = None
    vigente: bool
    origem: str
    observacao: Optional[str] = None


class PedidoIn(BaseModel):
    tipo: TIPOS_PEDIDO
    solicitante: Optional[str] = Field(default="titular", max_length=120)
    em: Optional[Instante] = None
    # Prazo de resposta: fica vazio quando ninguém definiu. Nenhum número
    # é chutado pelo sistema.
    prazo: Optional[Instante] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)


class DecisaoIn(BaseModel):
    alvo: ALVOS_DE_DADO
    decisao: DECISOES
    # Obrigatório inclusive para "manter": manter prontuário contra um
    # pedido de exclusão é legítimo, e precisa estar escrito.
    motivo: str = Field(min_length=3, max_length=300)
    base_legal: Optional[str] = Field(default=None, max_length=200)


class EncerrarPedidoIn(BaseModel):
    status: Literal["done", "refused"]
    observacao: Optional[str] = Field(default=None, max_length=2000)


class DecisaoOut(BaseModel):
    id: str
    alvo: ALVOS_DE_DADO
    decisao: DECISOES
    motivo: str
    base_legal: Optional[str] = None
    aplicado_em: Optional[datetime] = None
    resultado: Optional[str] = None


class PedidoOut(BaseModel):
    id: str
    tipo: TIPOS_PEDIDO
    status: str
    solicitante: str
    pedido_em: datetime
    prazo: Optional[datetime] = None
    encerrado_em: Optional[datetime] = None
    observacao: Optional[str] = None
    desfecho: Optional[str] = None
    cliente: Optional[ClienteResumidoOut] = None
    decisoes: List[DecisaoOut] = []


class PoliticaIn(BaseModel):
    alvo: ALVOS_DE_DADO
    profissao: Optional[str] = Field(default=None, max_length=60)
    # Nulo = sem prazo definido. É o padrão, e é proposital.
    meses: Optional[int] = Field(default=None, ge=1, le=1200)
    base_legal: Optional[str] = Field(default=None, max_length=300)
    observacao: Optional[str] = Field(default=None, max_length=300)


class PoliticaOut(BaseModel):
    id: str
    alvo: ALVOS_DE_DADO
    profissao: Optional[str] = None
    meses: Optional[int] = None
    base_legal: Optional[str] = None
    observacao: Optional[str] = None
    # Só vale para apagar algo quando tem prazo E base legal.
    aplicavel: bool = False


class EventoOut(BaseModel):
    """Uma linha da trilha de segurança. Nunca conteúdo."""

    id: str
    quando: datetime
    acao: str
    resultado: str
    quem: Optional[str] = None
    detalhe: Optional[str] = None


class PagamentoAvulsoIn(BaseModel):
    """Pagamento que não nasce de um atendimento: pacote, sinal, acerto."""

    valor: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    metodo: METODOS_PAGAMENTO = "pix"
    pago_em: Optional[Instante] = None
    observacao: Optional[str] = Field(default=None, max_length=200)
