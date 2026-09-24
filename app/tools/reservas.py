import json

from google.adk.tools import ToolContext

from app.database import (
    AREAS,
    cancelar_reserva,
    criar_confirmacao,
    criar_reserva,
    listar_reservas_apartamento,
    verificar_disponibilidade_area,
)


async def listar_reservas(tool_context: ToolContext) -> str:
    """Lista todas as reservas do apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    reservas = await listar_reservas_apartamento(apartamento)
    if not reservas:
        return f"Não há reservas registradas para o apartamento {apartamento}."
    linhas = []
    for r in reservas:
        area_nome = AREAS.get(r["area"], {}).get("nome", r["area"])
        linhas.append(f"- Código: {r['codigo']}, Área: {area_nome}, Data: {r['data']}")
    return f"Reservas do apartamento {apartamento}:\n" + "\n".join(linhas)


async def verificar_disponibilidade(area_id: str, data: str, tool_context: ToolContext) -> str:
    """Verifica se uma área comum está disponível em uma data específica.

    Args:
        area_id: ID da área (salao-de-festas, churrasqueira, quadra)
        data: Data no formato YYYY-MM-DD
    """
    if area_id not in AREAS:
        return f"Área '{area_id}' não encontrada. Áreas disponíveis: {', '.join(AREAS.keys())}"
    disponivel = await verificar_disponibilidade_area(area_id, data)
    area_nome = AREAS[area_id]["nome"]
    if disponivel:
        return f"A área '{area_nome}' está DISPONÍVEL para {data}."
    return f"A área '{area_nome}' NÃO está disponível para {data} (já reservada)."


async def solicitar_reserva(area_id: str, data: str, tool_context: ToolContext) -> str:
    """Solicita a reserva de uma área comum para uma data específica.

    Args:
        area_id: ID da área (salao-de-festas, churrasqueira, quadra)
        data: Data no formato YYYY-MM-DD
    """
    if area_id not in AREAS:
        return f"Área '{area_id}' não encontrada. Áreas disponíveis: {', '.join(AREAS.keys())}"

    apartamento = tool_context.state["apartamento"]
    area = AREAS[area_id]
    taxa = area["taxa"]

    if taxa == 0:
        resultado = await criar_reserva(apartamento, area_id, data)
        if resultado["sucesso"]:
            return f"Reserva criada com sucesso! Código: {resultado['codigo']}. Área: {area['nome']}, Data: {data}. Sem taxa."
        return resultado["erro"]

    disponivel = await verificar_disponibilidade_area(area_id, data)
    if not disponivel:
        return f"A área '{area['nome']}' NÃO está disponível para {data} (já reservada)."

    session_id = tool_context.session.id
    conf_id = await criar_confirmacao(
        session_id=session_id,
        tipo="reserva",
        detalhes={"area_id": area_id, "data": data, "taxa": taxa},
        apartamento=apartamento,
    )
    return (
        f"A reserva de '{area['nome']}' para {data} requer o pagamento de uma taxa de R$ {taxa:.2f}. "
        f"Uma confirmação foi gerada (ID: {conf_id}). O morador precisa confirmar para prosseguir."
    )


async def cancelar_reserva_tool(codigo: str, tool_context: ToolContext) -> str:
    """Cancela uma reserva existente pelo código.

    Args:
        codigo: Código da reserva (ex: RSV-1234)
    """
    apartamento = tool_context.state["apartamento"]
    resultado = await cancelar_reserva(codigo, apartamento)
    if resultado["sucesso"]:
        return f"Reserva '{codigo}' cancelada com sucesso."
    return resultado["erro"]
