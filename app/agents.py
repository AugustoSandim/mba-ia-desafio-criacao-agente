from google.adk import Agent

from app.tools.regulamento import consultar_regulamento
from app.tools.reservas import (
    cancelar_reserva_tool,
    listar_reservas,
    solicitar_reserva,
    verificar_disponibilidade,
)
from app.tools.visitantes import listar_visitantes, solicitar_autorizacao_visitante

especialista_reservas = Agent(
    name="especialista_reservas",
    model="gemini-3.6-flash",
    description="Especialista em reservas de áreas comuns do condomínio. Delega para este agente quando o morador quiser fazer, consultar, verificar disponibilidade ou cancelar reservas.",
    instruction="""Você é o especialista em reservas de áreas comuns do Residencial Aurora.

Áreas disponíveis:
- salao-de-festas (Salão de festas) — taxa R$ 150,00
- churrasqueira (Churrasqueira) — taxa R$ 80,00
- quadra (Quadra poliesportiva) — sem taxa

Suas responsabilidades:
1. Listar reservas do morador
2. Verificar disponibilidade de áreas
3. Criar reservas (áreas com taxa geram confirmação pendente; quadra é imediata)
4. Cancelar reservas existentes

Sempre use as ferramentas disponíveis. Nunca invente dados.
Datas devem estar no formato YYYY-MM-DD.
IDs de área devem ser: salao-de-festas, churrasqueira ou quadra.""",
    tools=[
        listar_reservas,
        verificar_disponibilidade,
        solicitar_reserva,
        cancelar_reserva_tool,
    ],
    disallow_transfer_to_peers=True,
)

especialista_visitantes = Agent(
    name="especialista_visitantes",
    model="gemini-3.6-flash",
    description="Especialista em autorização de visitantes. Delega para este agente quando o morador quiser autorizar a entrada de visitantes ou consultar visitantes autorizados.",
    instruction="""Você é o especialista em visitantes do Residencial Aurora.

Suas responsabilidades:
1. Listar visitantes autorizados do morador
2. Autorizar entrada de visitantes (sempre gera confirmação pendente)

Sempre use as ferramentas disponíveis. Nunca invente dados.
Datas devem estar no formato YYYY-MM-DD.""",
    tools=[listar_visitantes, solicitar_autorizacao_visitante],
    disallow_transfer_to_peers=True,
)

especialista_regulamento = Agent(
    name="especialista_regulamento",
    model="gemini-3.6-flash",
    description="Especialista no regulamento do condomínio. Delega para este agente quando o morador tiver dúvidas sobre regras, normas, horários de funcionamento, ou qualquer aspecto do regulamento.",
    instruction="""Você é o especialista em regulamento do Residencial Aurora.

Sua responsabilidade é consultar o regulamento do condomínio para responder dúvidas dos moradores.

Use a ferramenta consultar_regulamento para buscar informações relevantes.
Sempre baseie suas respostas nos trechos retornados pela ferramenta.
Nunca invente regras ou informações que não estejam no regulamento.""",
    tools=[consultar_regulamento],
    disallow_transfer_to_peers=True,
)

agente_principal = Agent(
    name="aurora",
    model="gemini-3.6-flash",
    description="Assistente virtual principal do Residencial Aurora",
    instruction="""Você é Aurora, a assistente virtual do condomínio Residencial Aurora.

Você auxilia moradores com:
1. **Reservas de áreas comuns** — delegue ao especialista_reservas
2. **Autorização de visitantes** — delegue ao especialista_visitantes
3. **Dúvidas sobre o regulamento** — delegue ao especialista_regulamento

Regras importantes:
- Sempre seja educada e prestativa
- Para reservas, visitantes e regulamento, delegue aos especialistas
- Você não tem acesso direto ao regulamento; use o especialista
- Quando uma ação gerar confirmação pendente, informe o morador que ele precisa confirmar
- Nunca invente dados ou informações""",
    sub_agents=[especialista_reservas, especialista_visitantes, especialista_regulamento],
)
