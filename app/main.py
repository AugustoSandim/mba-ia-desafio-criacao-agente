import json
from contextlib import asynccontextmanager
from pathlib import Path

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from google.adk import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from pydantic import BaseModel

from app.agents import agente_principal
from app.database import (
    AREAS,
    atualizar_confirmacao,
    autorizar_visitante,
    criar_reserva,
    init_db,
    listar_confirmacoes_pendentes,
    listar_reservas_apartamento,
    listar_visitantes_apartamento,
    obter_apartamento_sessao,
    obter_confirmacao,
    registrar_sessao,
)

APP_NAME = "residencial_aurora"
SESSIONS_DB = Path(__file__).resolve().parent.parent / "data" / "sessions.db"


session_service: DatabaseSessionService
runner: Runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session_service, runner
    await init_db()
    SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    session_service = DatabaseSessionService(
        db_url=f"sqlite+aiosqlite:///{SESSIONS_DB}"
    )
    runner = Runner(
        agent=agente_principal,
        app_name=APP_NAME,
        session_service=session_service,
    )
    yield


app = FastAPI(title="Residencial Aurora - Assistente Virtual", lifespan=lifespan)


class CriarSessaoRequest(BaseModel):
    apartamento: str


class MensagemRequest(BaseModel):
    texto: str


class ConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


@app.post("/sessoes", status_code=201)
async def criar_sessao(req: CriarSessaoRequest):
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=f"apt-{req.apartamento}",
        state={"apartamento": req.apartamento},
    )
    await registrar_sessao(session.id, req.apartamento)
    return {"session_id": session.id}


async def _verificar_sessao(session_id: str) -> str:
    apartamento = await obter_apartamento_sessao(session_id)
    if apartamento is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return apartamento


async def _executar_agente(session_id: str, texto: str, user_id: str) -> dict:
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=texto)]
    )
    resposta = ""
    ultima_resposta_modelo = ""
    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            if event.content and event.content.parts:
                partes_texto = [p.text for p in event.content.parts if p.text]
                if partes_texto:
                    texto_evento = "\n".join(partes_texto)
                    if event.is_final_response():
                        resposta = texto_evento
                    elif event.author and event.author != "user":
                        ultima_resposta_modelo = texto_evento
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao comunicar com o modelo: {e}")
    if not resposta:
        resposta = ultima_resposta_modelo

    pendentes = await listar_confirmacoes_pendentes(session_id)
    return {"resposta": resposta, "confirmacoes_pendentes": pendentes}


@app.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, req: MensagemRequest):
    apartamento = await _verificar_sessao(session_id)
    return await _executar_agente(
        session_id, req.texto, user_id=f"apt-{apartamento}"
    )


@app.post("/sessoes/{session_id}/confirmacoes")
async def processar_confirmacao(session_id: str, req: ConfirmacaoRequest):
    apartamento = await _verificar_sessao(session_id)

    conf = await obter_confirmacao(req.id, session_id)
    if conf is None or conf["status"] != "pendente":
        raise HTTPException(
            status_code=409,
            detail="Não existe confirmação pendente com esse id nesta sessão",
        )

    detalhes = json.loads(conf["detalhes"])

    if req.confirmado:
        await atualizar_confirmacao(req.id, "aprovada")
        if conf["tipo"] == "reserva":
            resultado = await criar_reserva(
                apartamento, detalhes["area_id"], detalhes["data"]
            )
            if resultado["sucesso"]:
                area_nome = AREAS.get(detalhes["area_id"], {}).get(
                    "nome", detalhes["area_id"]
                )
                msg_sistema = (
                    f"[Sistema] Confirmação aprovada. Reserva criada com sucesso! "
                    f"Código: {resultado['codigo']}. Área: {area_nome}, "
                    f"Data: {detalhes['data']}, Taxa: R$ {detalhes['taxa']:.2f}."
                )
            else:
                msg_sistema = f"[Sistema] Confirmação aprovada, mas a reserva falhou: {resultado['erro']}"
        elif conf["tipo"] == "visitante":
            await autorizar_visitante(
                apartamento, detalhes["nome"], detalhes["data"]
            )
            msg_sistema = (
                f"[Sistema] Confirmação aprovada. Visitante '{detalhes['nome']}' "
                f"autorizado para {detalhes['data']}."
            )
        else:
            msg_sistema = "[Sistema] Confirmação aprovada."
    else:
        await atualizar_confirmacao(req.id, "rejeitada")
        if conf["tipo"] == "reserva":
            area_nome = AREAS.get(detalhes["area_id"], {}).get(
                "nome", detalhes["area_id"]
            )
            msg_sistema = (
                f"[Sistema] Confirmação rejeitada. A reserva de '{area_nome}' "
                f"para {detalhes['data']} foi cancelada pelo morador."
            )
        elif conf["tipo"] == "visitante":
            msg_sistema = (
                f"[Sistema] Confirmação rejeitada. A autorização de entrada para "
                f"'{detalhes['nome']}' em {detalhes['data']} foi cancelada pelo morador."
            )
        else:
            msg_sistema = "[Sistema] Confirmação rejeitada."

    return await _executar_agente(
        session_id, msg_sistema, user_id=f"apt-{apartamento}"
    )


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str):
    apartamento = await _verificar_sessao(session_id)
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=f"apt-{apartamento}",
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    eventos = []
    for event in session.events:
        evento = {"autor": event.author}
        if event.content and event.content.parts:
            partes = []
            for part in event.content.parts:
                if part.text:
                    partes.append({"texto": part.text})
                elif part.function_call:
                    partes.append({
                        "function_call": {
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {},
                        }
                    })
                elif part.function_response:
                    partes.append({
                        "function_response": {
                            "name": part.function_response.name,
                            "response": part.function_response.response,
                        }
                    })
            evento["conteudo"] = partes
        eventos.append(evento)
    return eventos


@app.get("/apartamentos/{numero}/reservas")
async def listar_reservas_endpoint(numero: str):
    reservas = await listar_reservas_apartamento(numero)
    return [
        {"codigo": r["codigo"], "area": r["area"], "data": r["data"]}
        for r in reservas
    ]


@app.get("/apartamentos/{numero}/visitantes")
async def listar_visitantes_endpoint(numero: str):
    visitantes = await listar_visitantes_apartamento(numero)
    return [{"nome": v["nome"], "data": v["data"]} for v in visitantes]
