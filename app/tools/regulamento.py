import re
import unicodedata
from pathlib import Path

from google.adk.tools import ToolContext

REGULAMENTO_PATH = (
    Path(__file__).resolve().parent.parent.parent / "dados" / "regulamento.md"
)

# Termos sem valor de assunto. Sem esse filtro, palavras como "que" e "aos"
# pontuam capítulos por coincidência e devolvem assuntos fora da pergunta.
PALAVRAS_IRRELEVANTES = {
    "a",
    "o",
    "as",
    "os",
    "um",
    "uma",
    "uns",
    "umas",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "pelo",
    "pela",
    "pelos",
    "pelas",
    "para",
    "pra",
    "pro",
    "ao",
    "aos",
    "com",
    "sem",
    "sobre",
    "entre",
    "ate",
    "apos",
    "sob",
    "e",
    "ou",
    "mas",
    "porem",
    "se",
    "ja",
    "tambem",
    "que",
    "quem",
    "qual",
    "quais",
    "quanto",
    "quantos",
    "quantas",
    "como",
    "quando",
    "onde",
    "porque",
    "pois",
    "eu",
    "voce",
    "vc",
    "ele",
    "ela",
    "eles",
    "elas",
    "meu",
    "minha",
    "seu",
    "sua",
    "me",
    "te",
    "lhe",
    "lhes",
    "isso",
    "isto",
    "alguem",
    "ser",
    "estar",
    "ter",
    "haver",
    "fazer",
    "poder",
    "dever",
    "ir",
    "vir",
    "sou",
    "esta",
    "sao",
    "era",
    "foi",
    "foram",
    "ha",
    "tem",
    "tinha",
    "posso",
    "pode",
    "podem",
    "devo",
    "deve",
    "devem",
    "quero",
    "quer",
    "gostaria",
    "preciso",
    "precisa",
    "saber",
    "sei",
    "dizer",
    "falar",
    "explicar",
    "ajudar",
    "hora",
    "horas",
    "horario",
    "horarios",
    "funcionamento",
    "funciona",
    "funcionar",
    "abre",
    "fecha",
    "aberto",
    "aberta",
    "fechado",
    "fechada",
    "disponivel",
    "dia",
    "dias",
}

# Peso de um termo achado no título do capítulo (concentra o assunto) e
# relevância mínima para devolver o capítulo — um termo solto no conteúdo não basta.
PESO_TITULO = 10
LIMIAR_RELEVANCIA = 2


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


def _termos_relevantes(pergunta: str) -> list[str]:
    termos = re.findall(r"[a-z0-9]+", _normalizar(pergunta))
    return [t for t in termos if len(t) > 2 and t not in PALAVRAS_IRRELEVANTES]


def _pontuar_capitulo(capitulo: dict, termos: list[str]) -> int:
    titulo = _normalizar(capitulo["titulo"])
    conteudo = _normalizar(capitulo["conteudo"])
    score = 0
    for termo in termos:
        if termo in titulo:
            score += PESO_TITULO
        elif termo in conteudo:
            score += 1
    return score


async def consultar_regulamento(pergunta: str, tool_context: ToolContext) -> str:
    """Consulta o regulamento do condomínio para responder dúvidas sobre regras e normas.

    Args:
        pergunta: A pergunta ou tema sobre o regulamento que deseja consultar
    """
    capitulos = _carregar_capitulos()
    termos = _termos_relevantes(pergunta)

    if not termos:
        return "Não encontrei informações relevantes no regulamento para essa consulta."

    pontuados = []
    for cap in capitulos:
        score = _pontuar_capitulo(cap, termos)
        if score > 0:
            pontuados.append((score, cap))

    pontuados.sort(key=lambda x: x[0], reverse=True)

    if not pontuados or pontuados[0][0] < LIMIAR_RELEVANCIA:
        return "Não encontrei informações relevantes no regulamento para essa consulta."

    melhor = pontuados[0][1]
    return "Trecho relevante do regulamento:\n\n" + melhor["conteudo"]
