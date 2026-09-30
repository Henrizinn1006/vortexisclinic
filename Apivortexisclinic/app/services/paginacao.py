"""
Paginação por página e tamanho.

**Por que página e não cursor**

Cursor é melhor para feed infinito e para consistência sob escrita
concorrente. Aqui as listas são "as pessoas que atendo", "os atendimentos
do mês", "o livro-caixa" — coisas que se lê em ordem alfabética ou
cronológica, com a pessoa querendo ir para a página 3 e voltar. Página é
o que casa com isso, e o custo (um `COUNT` a mais) é o que paga por
mostrar "134 pessoas" em vez de "134+".

**O total vai no cabeçalho, não no corpo**

`X-Total-Count` e `X-Page`. Assim a resposta continua sendo uma lista, e
nenhuma tela existente quebra ao ganhar paginação — que é a diferença
entre acrescentar um recurso e refazer o painel.
"""
from typing import Tuple

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

TAMANHO_PADRAO = 50
TAMANHO_MAXIMO = 500


def limites(pagina: int = 1, tamanho: int = TAMANHO_PADRAO) -> Tuple[int, int]:
    """(offset, limite) saneados. Página inválida vira a primeira."""
    tamanho = max(1, min(int(tamanho or TAMANHO_PADRAO), TAMANHO_MAXIMO))
    pagina = max(1, int(pagina or 1))
    return (pagina - 1) * tamanho, tamanho


def total(db: Session, consulta: Select) -> int:
    """Conta as linhas da consulta sem trazer nenhuma.

    `order_by` é removido de propósito: ordenar para contar é trabalho
    jogado fora, e alguns bancos recusam `ORDER BY` dentro de subconsulta
    sem `LIMIT`.
    """
    sem_ordem = consulta.order_by(None).limit(None).offset(None)
    return int(db.execute(
        select(func.count()).select_from(sem_ordem.subquery())
    ).scalar_one())


def cabecalhos(resposta, *, total_de_linhas: int, pagina: int, tamanho: int) -> None:
    """Põe o total no cabeçalho. O corpo continua sendo uma lista."""
    if resposta is None:
        return
    resposta.headers["X-Total-Count"] = str(total_de_linhas)
    resposta.headers["X-Page"] = str(max(1, pagina))
    resposta.headers["X-Page-Size"] = str(tamanho)
    # Sem isto, o navegador não deixa o JavaScript ler os cabeçalhos
    # numa resposta de outra origem — e em desenvolvimento a API e o
    # painel estão em portas diferentes.
    resposta.headers["Access-Control-Expose-Headers"] = "X-Total-Count, X-Page, X-Page-Size"
