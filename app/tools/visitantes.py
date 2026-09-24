from google.adk.tools import ToolContext

from app.database import (
    criar_confirmacao,
    listar_visitantes_apartamento,
)


async def listar_visitantes(tool_context: ToolContext) -> str:
    """Lista todos os visitantes autorizados do apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    visitantes = await listar_visitantes_apartamento(apartamento)
    if not visitantes:
        return f"Não há visitantes autorizados para o apartamento {apartamento}."
    linhas = []
    for v in visitantes:
        linhas.append(f"- Nome: {v['nome']}, Data: {v['data']}")
    return f"Visitantes autorizados do apartamento {apartamento}:\n" + "\n".join(linhas)


async def solicitar_autorizacao_visitante(nome: str, data: str, tool_context: ToolContext) -> str:
    """Solicita autorização de entrada para um visitante.

    Args:
        nome: Nome completo do visitante
        data: Data da visita no formato YYYY-MM-DD
    """
    apartamento = tool_context.state["apartamento"]
    session_id = tool_context.session.id

    conf_id = await criar_confirmacao(
        session_id=session_id,
        tipo="visitante",
        detalhes={"nome": nome, "data": data},
        apartamento=apartamento,
    )
    return (
        f"A autorização de entrada para '{nome}' em {data} requer confirmação. "
        f"ID da confirmação: {conf_id}. O morador precisa confirmar para prosseguir."
    )
