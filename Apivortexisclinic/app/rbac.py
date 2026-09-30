"""
Catálogo de papéis e permissões — a fonte que o seed da migration usa.

Espelha `assets/js/types/entities.js` do painel de propósito: o front
desenha a partir desta lista, o servidor decide a partir dela. Quando
divergirem, o servidor manda.

Regra estrutural: **nenhum papel recebe "tudo"**. OWNER administra a conta
e NÃO recebe permissão da classe clínica. Se o dono também atende, ele tem
perfil profissional e recebe as permissões clínicas por isso — ou por
concessão explícita e registrada em membership_permissions.
"""
from typing import Dict, List, Tuple

# ---------------- Classes de dado ----------------
ADMINISTRATIVE = "administrative"
CLINICAL = "clinical"
ACCOUNT = "account"
AUDIT = "audit"

# chave, nome, classe
PERMISSOES: List[Tuple[str, str, str]] = [
    ("agenda.read", "Ver agenda", ADMINISTRATIVE),
    ("agenda.write", "Editar agenda", ADMINISTRATIVE),
    ("agenda.manage_others", "Gerenciar agenda de outros", ADMINISTRATIVE),

    ("patients.read", "Ver pessoas atendidas", ADMINISTRATIVE),
    ("patients.write", "Cadastrar e editar pessoas atendidas", ADMINISTRATIVE),
    ("patients.archive", "Arquivar pessoa atendida", ADMINISTRATIVE),

    ("appointments.read", "Ver atendimentos", ADMINISTRATIVE),
    ("appointments.write", "Criar e editar atendimentos", ADMINISTRATIVE),
    ("appointments.cancel", "Cancelar atendimento", ADMINISTRATIVE),

    ("finance.read", "Ver financeiro", ADMINISTRATIVE),
    ("finance.write", "Lançar e baixar pagamentos", ADMINISTRATIVE),
    ("finance.export", "Exportar financeiro", ADMINISTRATIVE),

    ("clinical_records.read", "Ver registros clínicos próprios", CLINICAL),
    ("clinical_records.write", "Escrever registro clínico", CLINICAL),
    ("clinical_records.read_others", "Ver registro clínico de outro profissional", CLINICAL),
    ("documents.read", "Ver documentos clínicos", CLINICAL),
    ("documents.write", "Enviar documentos clínicos", CLINICAL),

    ("members.manage", "Gerenciar pessoas da conta", ACCOUNT),
    ("settings.manage", "Configurações da conta", ACCOUNT),
    ("data_requests.manage", "Tratar pedidos do titular", ACCOUNT),

    ("audit.read", "Ver trilha de auditoria", AUDIT),
]

OWNER = "OWNER"
PROFESSIONAL = "PROFESSIONAL"
ASSISTANT = "ASSISTANT"

PAPEIS: Dict[str, Dict[str, str]] = {
    OWNER: {
        "name": "Dono da conta",
        "description": "Administra a conta, as pessoas e o financeiro. Não acessa conteúdo clínico alheio.",
        "scope": "all",
    },
    PROFESSIONAL: {
        "name": "Profissional",
        "description": "Atende: agenda, pessoas, atendimentos e registros clínicos dos seus.",
        "scope": "own",
    },
    ASSISTANT: {
        "name": "Apoio administrativo",
        "description": "Agenda, cadastro e financeiro. Nunca conteúdo clínico.",
        "scope": "all",
    },
}

PAPEL_PERMISSOES: Dict[str, List[str]] = {
    OWNER: [
        "agenda.read", "agenda.write", "agenda.manage_others",
        "patients.read", "patients.write", "patients.archive",
        "appointments.read", "appointments.write", "appointments.cancel",
        "finance.read", "finance.write", "finance.export",
        "members.manage", "settings.manage", "data_requests.manage",
        "audit.read",
        # Sem clinical_records.* e sem documents.*: administrar a conta não
        # abre prontuário. Dono que atende recebe isso pelo perfil
        # profissional ou por concessão explícita.
    ],
    PROFESSIONAL: [
        "agenda.read", "agenda.write",
        "patients.read", "patients.write",
        "appointments.read", "appointments.write", "appointments.cancel",
        "finance.read",
        "clinical_records.read", "clinical_records.write",
        "documents.read", "documents.write",
        # Sem clinical_records.read_others: só o que é dele.
    ],
    ASSISTANT: [
        "agenda.read", "agenda.write", "agenda.manage_others",
        "patients.read", "patients.write",
        "appointments.read", "appointments.write", "appointments.cancel",
        "finance.read", "finance.write",
        # Nunca clinical_records.* nem documents.*.
    ],
}

CLASSE_DE = {chave: classe for chave, _nome, classe in PERMISSOES}


def eh_clinica(permissao: str) -> bool:
    return CLASSE_DE.get(permissao) == CLINICAL


def permissoes_do_papel(papel: str) -> List[str]:
    return list(PAPEL_PERMISSOES.get(papel, []))
