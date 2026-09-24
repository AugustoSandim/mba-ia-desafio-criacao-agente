import re
import unicodedata
from pathlib import Path

from google.adk.tools import ToolContext

REGULAMENTO_PATH = Path(__file__).resolve().parent.parent.parent / "dados" / "regulamento.md"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower()


def _carregar_capitulos() -> list[dict]:
    conteudo = REGULAMENTO_PATH.read_text(encoding="utf-8")
    partes = re.split(r"(?=^## )", conteudo, flags=re.MULTILINE)
    capitulos = []
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        primeira_linha = parte.split("\n")[0]
        capitulos.append({"titulo": primeira_linha, "conteudo": parte})
    return capitulos


def _pontuar_capitulo(capitulo: dict, termos: list[str]) -> int:
    texto_normalizado = _normalizar(capitulo["conteudo"])
    score = 0
    for termo in termos:
        score += texto_normalizado.count(termo)
    return score


async def consultar_regulamento(pergunta: str, tool_context: ToolContext) -> str:
    """Consulta o regulamento do condomínio para responder dúvidas sobre regras e normas.

    Args:
        pergunta: A pergunta ou tema sobre o regulamento que deseja consultar
    """
    capitulos = _carregar_capitulos()
    termos = _normalizar(pergunta).split()
    termos = [t for t in termos if len(t) > 2]

    pontuados = []
    for cap in capitulos:
        score = _pontuar_capitulo(cap, termos)
        if score > 0:
            pontuados.append((score, cap))

    pontuados.sort(key=lambda x: x[0], reverse=True)

    if not pontuados:
        return "Não encontrei informações relevantes no regulamento para essa consulta."

    top = pontuados[:3]
    trechos = []
    for _, cap in top:
        trechos.append(cap["conteudo"])

    return "Trechos relevantes do regulamento:\n\n" + "\n\n---\n\n".join(trechos)
