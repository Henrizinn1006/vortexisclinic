"""
Rate limit de login e cadastro — janela deslizante em memória.

Limitação conhecida e assumida nesta etapa: o contador vive no processo.
Com mais de um worker, cada um conta o seu. Está registrado como dívida
técnica; a troca por Redis é uma implementação desta mesma interface.

Duas chaves são contadas por tentativa de login: o IP e o e-mail. Só IP
deixa passar ataque distribuído contra uma conta; só e-mail deixa passar
varredura de muitas contas a partir de um IP.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class JanelaDeslizante:
    def __init__(self) -> None:
        self._eventos: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def registrar_e_checar(self, chave: str, limite: int, janela_s: int) -> Tuple[bool, int]:
        """Registra a tentativa. Devolve (permitido, segundos_para_liberar)."""
        agora = time.time()
        with self._lock:
            fila = self._eventos[chave]
            while fila and agora - fila[0] > janela_s:
                fila.popleft()
            if len(fila) >= limite:
                espera = int(janela_s - (agora - fila[0])) + 1
                return False, max(espera, 1)
            fila.append(agora)
            return True, 0

    def limpar(self, chave: str) -> None:
        """Chamado em login bem-sucedido: acerto zera o contador daquela chave."""
        with self._lock:
            self._eventos.pop(chave, None)

    def zerar_tudo(self) -> None:
        with self._lock:
            self._eventos.clear()


limitador = JanelaDeslizante()
