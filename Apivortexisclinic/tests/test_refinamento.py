"""
Busca, paginação, pagamento parcial e avulso, e teto de escrita.

Nada aqui é funcionalidade nova de negócio — é o que separa um sistema que
funciona na demonstração de um que funciona com 400 pessoas cadastradas e
alguém digitando "jose" no lugar de "José".
"""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.services.sessions import agora
from tests.conftest import cadastrar, csrf

ONTEM = (agora() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture
def conta(cliente):
    r = cadastrar(cliente, nome="Clara Mendes", email="clara@exemplo.com",
                  workspace="Clínica Bem Viver", profissao="terapia_integrativa")
    assert r.status_code == 201
    return r.json()


def novo_cliente(cliente, nome, **extra):
    corpo = {"nome": nome}
    corpo.update(extra)
    return cliente.post("/workspace/clients", json=corpo, headers=csrf(cliente)).json()


# ---------------- busca ----------------
def test_busca_ignora_acento(cliente, conta):
    """Vem da collation das tabelas, não de código. Este teste é o que
    garante que continue assim se alguém mexer no schema."""
    novo_cliente(cliente, "José da Conceição")
    achados = cliente.get("/workspace/clients?busca=jose").json()
    assert len(achados) == 1
    achados = cliente.get("/workspace/clients?busca=conceicao").json()
    assert len(achados) == 1


def test_busca_ignora_maiuscula(cliente, conta):
    novo_cliente(cliente, "Ana Beatriz")
    assert len(cliente.get("/workspace/clients?busca=ANA").json()) == 1
    assert len(cliente.get("/workspace/clients?busca=beatriz").json()) == 1


def test_curinga_digitado_nao_vira_curinga(cliente, conta):
    """Quem digita '%' quer procurar '%', não listar a conta inteira."""
    novo_cliente(cliente, "Ana Beatriz")
    novo_cliente(cliente, "Bruno Alves")
    assert cliente.get("/workspace/clients?busca=%25").json() == []
    assert cliente.get("/workspace/clients?busca=_").json() == []


def test_busca_nao_atravessa_contas(cliente, conta):
    novo_cliente(cliente, "José da Conceição")
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia@exemplo.com", workspace="Clínica da Bia")
    assert cliente.get("/workspace/clients?busca=jose").json() == []


# ---------------- paginação ----------------
def test_pagina_traz_so_o_pedaco_e_o_total_vai_no_cabecalho(cliente, conta):
    for i in range(12):
        novo_cliente(cliente, f"Pessoa {i:02d}")

    r = cliente.get("/workspace/clients?limite=5&pagina=1")
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert r.headers["x-total-count"] == "12"
    assert r.headers["x-page"] == "1"

    r3 = cliente.get("/workspace/clients?limite=5&pagina=3")
    assert len(r3.json()) == 2
    assert r3.headers["x-total-count"] == "12"


def test_paginas_nao_repetem_ninguem(cliente, conta):
    for i in range(12):
        novo_cliente(cliente, f"Pessoa {i:02d}")

    vistos = []
    for pagina in (1, 2, 3):
        vistos += [c["id"] for c in
                   cliente.get(f"/workspace/clients?limite=5&pagina={pagina}").json()]
    assert len(vistos) == 12
    assert len(set(vistos)) == 12, "a mesma pessoa apareceu em duas páginas"


def test_pagina_alem_do_fim_devolve_vazio_e_nao_erro(cliente, conta):
    novo_cliente(cliente, "Sozinha")
    r = cliente.get("/workspace/clients?limite=5&pagina=9")
    assert r.status_code == 200
    assert r.json() == []
    assert r.headers["x-total-count"] == "1"


def test_o_total_respeita_o_filtro(cliente, conta):
    novo_cliente(cliente, "Ativa Um")
    inativa = novo_cliente(cliente, "Inativa Um")
    cliente.patch(f"/workspace/clients/{inativa['id']}", json={"status": "inactive"},
                  headers=csrf(cliente))
    r = cliente.get("/workspace/clients?limite=5&pagina=1&status=active")
    assert r.headers["x-total-count"] == "1"


def test_agenda_sem_pagina_continua_trazendo_a_janela_inteira(cliente, conta):
    """A agenda não pagina: ali o recorte já são as datas."""
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    for i in range(8):
        quando = agora() + timedelta(days=i + 1, hours=i)
        cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": quando.isoformat()},
                     headers=csrf(cliente))
    r = cliente.get("/workspace/appointments")
    assert len(r.json()) == 8
    assert "x-total-count" not in {k.lower() for k in r.headers}

    r = cliente.get("/workspace/appointments?limite=3&pagina=1")
    assert len(r.json()) == 3
    assert r.headers["x-total-count"] == "8"


# ---------------- pagamento parcial ----------------
@pytest.fixture
def realizado(cliente, conta):
    pessoa = novo_cliente(cliente, "Ana Beatriz", valor_sessao="200.00")
    a = cliente.post("/workspace/appointments",
                     json={"cliente_id": pessoa["id"], "inicio": ONTEM.isoformat()},
                     headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/status",
                 json={"status": "done"}, headers=csrf(cliente))
    return pessoa, a


def test_pagamento_parcial_nao_quita(cliente, realizado):
    """Metade hoje, metade na semana que vem. Marcar quitado no primeiro
    pedaço sumiria com a cobrança do resto."""
    _pessoa, a = realizado
    r = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                     json={"metodo": "pix", "valor": "80.00"}, headers=csrf(cliente))
    assert r.status_code == 201

    atendimento = cliente.get(f"/workspace/appointments/{a['id']}").json()
    assert atendimento["pagamento"] == "pending"
    assert len(cliente.get("/workspace/finance/pending").json()) == 1


def test_o_segundo_pedaco_quita(cliente, realizado):
    _pessoa, a = realizado
    cliente.post(f"/workspace/appointments/{a['id']}/payment",
                 json={"metodo": "pix", "valor": "80.00"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                     json={"metodo": "cash", "valor": "120.00"}, headers=csrf(cliente))
    assert r.status_code == 201

    atendimento = cliente.get(f"/workspace/appointments/{a['id']}").json()
    assert atendimento["pagamento"] == "paid"
    assert cliente.get("/workspace/finance/pending").json() == []
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 200.0


def test_sem_valor_o_segundo_pagamento_cobre_o_que_falta(cliente, realizado):
    _pessoa, a = realizado
    cliente.post(f"/workspace/appointments/{a['id']}/payment",
                 json={"metodo": "pix", "valor": "50.00"}, headers=csrf(cliente))
    r = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                     json={"metodo": "cash"}, headers=csrf(cliente))
    assert float(r.json()["valor"]) == 150.0, "o padrão é o que falta, não o total"


def test_estornar_um_pedaco_devolve_a_cobranca(cliente, realizado):
    """Dois pedaços cobriam o total; tirar um deixa de cobrir."""
    _pessoa, a = realizado
    primeiro = cliente.post(f"/workspace/appointments/{a['id']}/payment",
                            json={"metodo": "pix", "valor": "80.00"},
                            headers=csrf(cliente)).json()
    cliente.post(f"/workspace/appointments/{a['id']}/payment",
                 json={"metodo": "cash", "valor": "120.00"}, headers=csrf(cliente))
    assert cliente.get(f"/workspace/appointments/{a['id']}").json()["pagamento"] == "paid"

    cliente.post(f"/workspace/payments/{primeiro['id']}/refund", json={},
                 headers=csrf(cliente))
    atendimento = cliente.get(f"/workspace/appointments/{a['id']}").json()
    assert atendimento["pagamento"] == "pending"


# ---------------- pagamento avulso ----------------
def test_pagamento_avulso_entra_no_caixa(cliente, conta):
    """Pacote pago adiantado não pode precisar de um atendimento falso."""
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"valor": "900.00", "metodo": "transfer",
                           "observacao": "pacote de 5 sessões"},
                     headers=csrf(cliente))
    assert r.status_code == 201
    assert r.json()["atendimento_id"] is None

    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 900.0
    assert cliente.get("/workspace/appointments").json() == [], "não inventou atendimento"


def test_avulso_sem_valor_e_recusado(cliente, conta):
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"valor": "0", "metodo": "pix"}, headers=csrf(cliente))
    assert r.status_code == 422


def test_avulso_no_futuro_e_recusado(cliente, conta):
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    amanha = (agora() + timedelta(days=1)).isoformat()
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"valor": "100.00", "metodo": "pix", "pago_em": amanha},
                     headers=csrf(cliente))
    assert r.status_code == 422


def test_avulso_de_outra_conta_nao_existe(cliente, conta):
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    cliente.cookies.clear()
    cadastrar(cliente, nome="Bia Outra", email="bia2@exemplo.com", workspace="Clínica da Bia 2",
              profissao="terapia_integrativa")
    r = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"valor": "100.00", "metodo": "pix"}, headers=csrf(cliente))
    assert r.status_code == 404


def test_avulso_pode_ser_estornado(cliente, conta):
    pessoa = novo_cliente(cliente, "Ana Beatriz")
    p = cliente.post(f"/workspace/clients/{pessoa['id']}/payment",
                     json={"valor": "900.00", "metodo": "transfer"},
                     headers=csrf(cliente)).json()
    r = cliente.post(f"/workspace/payments/{p['id']}/refund",
                     json={"motivo": "desistiu do pacote"}, headers=csrf(cliente))
    assert r.status_code == 200
    assert float(cliente.get("/workspace/finance/summary").json()["recebido"]) == 0.0


# ---------------- teto de escrita ----------------
def test_teto_de_escrita_segura_automacao_desgovernada(cliente, conta):
    """Não é contenção de ataque — é para um laço com defeito não encher
    o banco antes de alguém perceber. Leitura não é afetada."""
    from app.config import settings
    from app.security.ratelimit import limitador

    original = settings.VC_RATE_LIMIT_WRITE
    try:
        settings.VC_RATE_LIMIT_WRITE = 3
        limitador.zerar_tudo()
        respostas = [
            cliente.post("/workspace/clients", json={"nome": f"Pessoa {i}"},
                         headers=csrf(cliente)).status_code
            for i in range(6)
        ]
        assert 429 in respostas, "o teto não travou nada"
        # E ler continua funcionando.
        assert cliente.get("/workspace/clients").status_code == 200
    finally:
        settings.VC_RATE_LIMIT_WRITE = original
        limitador.zerar_tudo()
