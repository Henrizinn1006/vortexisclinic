"""
Gerador de PDF mínimo, sem dependência.

**Por que escrever isto em vez de instalar uma biblioteca**

Os PDFs que este sistema emite são recibo, declaração de comparecimento e
cópia de prontuário: texto em A4, uma ou poucas páginas, sem imagem, sem
tabela complexa, sem fonte embutida. Para isso, uma biblioteca de
diagramação seria um megabyte de dependência — e, no caso do prontuário,
uma dependência a mais passando perto de conteúdo clínico.

PDF é formato de texto. As 14 fontes padrão (Helvetica entre elas) não
precisam ser embutidas, e `WinAnsiEncoding` cobre o português inteiro. O
que sobra é montar os objetos e o `xref` — que é o que este arquivo faz.

**O que ele não faz**: imagem, tabela com bordas, quebra automática de
página no meio de um parágrafo (a quebra é por linha), fonte fora das
padrão. Quando alguma dessas fizer falta, aí sim vale a dependência.
"""
from typing import List, Optional, Tuple

A4 = (595.28, 841.89)          # pontos
MARGEM = 56                    # ~2 cm
ENTRELINHA = 15

REGULAR = "F1"
NEGRITO = "F2"
ITALICO = "F3"


def _escapar(texto: str) -> bytes:
    """Escapa o que é sintaxe dentro de uma string PDF."""
    saida = texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    # WinAnsi ≈ cp1252: cobre acento, cedilha, travessão e aspas curvas.
    return saida.encode("cp1252", errors="replace")


def _largura(texto: str, tamanho: float, negrito: bool = False) -> float:
    """Largura aproximada. Helvetica tem métrica própria por caractere;
    a média serve para quebrar linha sem carregar a tabela inteira."""
    fator = 0.54 if negrito else 0.5
    return len(texto) * tamanho * fator


def quebrar(texto: str, largura: float, tamanho: float, negrito: bool = False) -> List[str]:
    """Quebra por palavra. Palavra maior que a linha é cortada."""
    linhas = []
    for paragrafo in (texto or "").split("\n"):
        if not paragrafo.strip():
            linhas.append("")
            continue
        atual = ""
        for palavra in paragrafo.split(" "):
            tentativa = (atual + " " + palavra).strip()
            if _largura(tentativa, tamanho, negrito) <= largura or not atual:
                atual = tentativa
            else:
                linhas.append(atual)
                atual = palavra
            while _largura(atual, tamanho, negrito) > largura:
                corte = max(1, int(largura / (tamanho * (0.54 if negrito else 0.5))))
                linhas.append(atual[:corte])
                atual = atual[corte:]
        linhas.append(atual)
    return linhas


class Documento:
    """Acumula linhas e fecha em bytes de PDF.

    O modelo é deliberadamente simples: uma pilha de linhas, cada uma com
    fonte e tamanho. Quem chama decide o texto; isto decide onde a página
    acaba.
    """

    def __init__(self, titulo: str = "", autor: str = ""):
        self.titulo = titulo
        self.autor = autor
        # Cada linha guarda (texto, x, y, fonte, tamanho): a posição é
        # decidida na hora de escrever, não reconstruída no fechamento.
        self.paginas: List[List[Tuple[str, float, float, str, float]]] = [[]]
        self.y = A4[1] - MARGEM
        self.largura_util = A4[0] - 2 * MARGEM

    # ---------------- escrita ----------------
    def _nova_pagina(self) -> None:
        self.paginas.append([])
        self.y = A4[1] - MARGEM

    def espaco(self, altura: float = ENTRELINHA) -> None:
        self.y -= altura
        if self.y < MARGEM:
            self._nova_pagina()

    def linha(self, texto: str, *, tamanho: float = 11, fonte: str = REGULAR,
              recuo: float = 0) -> None:
        if self.y - ENTRELINHA < MARGEM:
            self._nova_pagina()
        self.y -= ENTRELINHA
        self.paginas[-1].append((texto, MARGEM + recuo, self.y, fonte, tamanho))

    def paragrafo(self, texto: str, *, tamanho: float = 11, fonte: str = REGULAR,
                  recuo: float = 0) -> None:
        for parte in quebrar(texto, self.largura_util - recuo, tamanho, fonte == NEGRITO):
            self.linha(parte, tamanho=tamanho, fonte=fonte, recuo=recuo)

    def titulo_secao(self, texto: str) -> None:
        self.espaco(8)
        self.linha(texto, tamanho=13, fonte=NEGRITO)
        self.espaco(4)

    def regua(self) -> None:
        """Separador visual feito de caracteres — sem primitivas de desenho."""
        self.linha("_" * 78, tamanho=8)

    # ---------------- fechamento ----------------
    def bytes(self) -> bytes:
        objetos: List[bytes] = []

        def add(corpo: bytes) -> int:
            objetos.append(corpo)
            return len(objetos)

        fontes = {
            REGULAR: b"/Helvetica",
            NEGRITO: b"/Helvetica-Bold",
            ITALICO: b"/Helvetica-Oblique",
        }
        ids_fontes = {}
        for chave, nome in fontes.items():
            ids_fontes[chave] = add(
                b"<< /Type /Font /Subtype /Type1 /BaseFont " + nome +
                b" /Encoding /WinAnsiEncoding >>"
            )

        recursos = b"<< /Font << " + b" ".join(
            f"/{chave} {ids_fontes[chave]} 0 R".encode() for chave in fontes
        ) + b" >> >>"

        paginas_ids = []
        conteudo_ids = []
        for linhas in self.paginas:
            partes = [b"BT\n"]
            fonte_atual = None
            for texto, x, y, fonte, tamanho in linhas:
                chave = (fonte, tamanho)
                if chave != fonte_atual:
                    partes.append(f"/{fonte} {tamanho} Tf\n".encode())
                    fonte_atual = chave
                partes.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm\n".encode())
                partes.append(b"(" + _escapar(texto) + b") Tj\n")
            partes.append(b"ET")
            fluxo = b"".join(partes)
            conteudo_ids.append(add(
                b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream"
            ))

        raiz_paginas = len(objetos) + len(self.paginas) + 1
        for indice, conteudo in enumerate(conteudo_ids):
            paginas_ids.append(add(
                f"<< /Type /Page /Parent {raiz_paginas} 0 R /MediaBox [0 0 {A4[0]:.2f} {A4[1]:.2f}] "
                f"/Resources ".encode() + recursos +
                f" /Contents {conteudo} 0 R >>".encode()
            ))

        id_paginas = add(
            b"<< /Type /Pages /Count " + str(len(paginas_ids)).encode() +
            b" /Kids [" + b" ".join(f"{i} 0 R".encode() for i in paginas_ids) + b"] >>"
        )
        id_info = add(
            b"<< /Title (" + _escapar(self.titulo) + b") /Author (" +
            _escapar(self.autor) + b") /Producer (Vortexis Clinic) >>"
        )
        id_raiz = add(b"<< /Type /Catalog /Pages " + str(id_paginas).encode() + b" 0 R >>")

        # ---- montagem ----
        saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posicoes = [0]
        for numero, corpo in enumerate(objetos, 1):
            posicoes.append(len(saida))
            saida += str(numero).encode() + b" 0 obj\n" + corpo + b"\nendobj\n"

        inicio_xref = len(saida)
        saida += b"xref\n0 " + str(len(objetos) + 1).encode() + b"\n"
        saida += b"0000000000 65535 f \n"
        for pos in posicoes[1:]:
            saida += f"{pos:010d} 00000 n \n".encode()
        saida += (b"trailer\n<< /Size " + str(len(objetos) + 1).encode() +
                  b" /Root " + str(id_raiz).encode() + b" 0 R /Info " +
                  str(id_info).encode() + b" 0 R >>\nstartxref\n" +
                  str(inicio_xref).encode() + b"\n%%EOF\n")
        return bytes(saida)
