"""
Contratos de entrada e saída (Pydantic).

Validação de entrada acontece aqui, antes de qualquer serviço: tamanho,
formato de e-mail, campo obrigatório. O que sai também é declarado — a
resposta nunca é "o modelo do banco serializado", para hash de senha e id
interno não escaparem por descuido.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------- entrada ----------------
class CadastroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=200)
    workspace: str = Field(min_length=2, max_length=140)
    tipo_workspace: Literal["solo", "office", "clinic"] = "solo"
    profissao: Optional[str] = Field(default=None, max_length=60)
    conselho: Optional[str] = Field(default=None, max_length=20)
    registro: Optional[str] = Field(default=None, max_length=40)

    @field_validator("nome", "workspace")
    @classmethod
    def _limpar(cls, v: str) -> str:
        return " ".join(v.split())


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)


class TrocarWorkspaceIn(BaseModel):
    workspace_id: str = Field(min_length=26, max_length=26)


class NovoWorkspaceIn(BaseModel):
    nome: str = Field(min_length=2, max_length=140)
    tipo: Literal["solo", "office", "clinic"] = "solo"
    profissao: Optional[str] = Field(default=None, max_length=60)


class EsqueciSenhaIn(BaseModel):
    email: EmailStr


class VerificarEmailIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class RedefinirSenhaIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    senha: str = Field(min_length=8, max_length=200)


# ---------------- saída ----------------
class ProfissaoOut(BaseModel):
    slug: str
    nome: str
    exige_conselho: bool
    rotulo_conselho: Optional[str] = None
    rotulo_registro: Optional[str] = None


class WorkspaceOut(BaseModel):
    id: str
    nome: str
    slug: str
    tipo: str
    papel: str
    papel_nome: str
    escopo: str
    ativo: bool


class PerfilOut(BaseModel):
    id: str
    nome_exibicao: str
    profissao: Optional[str] = None
    conselho: Optional[str] = None
    registro: Optional[str] = None


class UsuarioOut(BaseModel):
    id: str
    nome: str
    email: EmailStr
    email_verificado: bool


class MeOut(BaseModel):
    usuario: UsuarioOut
    workspace_ativo: Optional[WorkspaceOut] = None
    workspaces: List[WorkspaceOut]
    permissoes: List[str]
    perfil: Optional[PerfilOut] = None
    csrf_token: Optional[str] = None


class MensagemOut(BaseModel):
    ok: bool = True
    mensagem: str = ""


# ---------------- equipe ----------------
PAPEIS = Literal["OWNER", "PROFESSIONAL", "ASSISTANT"]
ESCOPOS = Literal["all", "own"]


class ConviteIn(BaseModel):
    """Quem convida decide o acesso. Aceitar não escolhe nada."""

    email: EmailStr
    papel: PAPEIS = "PROFESSIONAL"
    escopo: Optional[ESCOPOS] = None          # None = padrão do papel
    profissao: Optional[str] = Field(default=None, max_length=60)
    mensagem: Optional[str] = Field(default=None, max_length=300)


class AceitarConviteIn(BaseModel):
    """Só o necessário para criar a conta de quem ainda não tem uma.

    Papel, escopo e profissão NÃO estão aqui de propósito: eles vêm da
    linha do convite. Não existe campo por onde pedir mais acesso.
    """

    nome: Optional[str] = Field(default=None, min_length=2, max_length=120)
    senha: Optional[str] = Field(default=None, min_length=8, max_length=200)


class MembroIn(BaseModel):
    papel: Optional[PAPEIS] = None
    escopo: Optional[ESCOPOS] = None
    status: Optional[Literal["active", "suspended"]] = None


class ConviteOut(BaseModel):
    id: str
    email: str
    papel: str
    escopo: str
    profissao: Optional[str] = None
    mensagem: Optional[str] = None
    expira_em: datetime
    convidado_por: Optional[str] = None
    # Só na criação, uma vez. Depois disso o token não existe mais em lugar nenhum.
    link: Optional[str] = None


class ConvitePublicoOut(BaseModel):
    """O que a tela de aceite mostra antes de haver sessão.

    Nome da conta e papel, e nada além disso: quem tem o link não precisa
    saber quem mais está na conta nem qual o e-mail de quem convidou.
    """

    workspace: str
    papel: str
    papel_nome: str
    email: str
    mensagem: Optional[str] = None
    expira_em: datetime
    ja_tem_conta: bool


class MembroDetalheOut(BaseModel):
    id: str
    nome: str
    email: str
    papel: str
    papel_nome: str
    escopo: str
    status: str
    sou_eu: bool = False
    atende: bool = False
    profissional_id: Optional[str] = None


class EquipeOut(BaseModel):
    membros: List[MembroDetalheOut]
    convites: List[ConviteOut]


# ---------------- configurações da conta ----------------
class ConfiguracoesIn(BaseModel):
    jornada_inicio: Optional[str] = Field(default=None, max_length=8)
    jornada_fim: Optional[str] = Field(default=None, max_length=8)
    dias_da_semana: Optional[List[int]] = None
    duracao_padrao: Optional[int] = Field(default=None, ge=1, le=1440)
    intervalo: Optional[int] = Field(default=None, ge=0, le=600)
    tolerancia_falta: Optional[int] = Field(default=None, ge=0, le=8760)
    meta_mensal: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("99999999.99"))
    limpar_meta: bool = False
    fuso: Optional[str] = Field(default=None, max_length=64)
    # Dicionário fechado; chave fora do catálogo é ignorada, e rótulo com
    # marcação é recusado — no painel e de novo aqui.
    terminologia: Optional[dict] = None


class ConfiguracoesOut(BaseModel):
    jornada_inicio: str
    jornada_fim: str
    dias_da_semana: List[int]
    duracao_padrao: int
    intervalo: int
    tolerancia_falta: int
    meta_mensal: Optional[Decimal] = None
    moeda: str
    fuso: str
    terminologia: dict = {}
    # Chaves que o servidor recusou na última gravação (marcação, tamanho,
    # ou fora do catálogo). A tela avisa em vez de fingir que gravou.
    recusados: List[str] = []
