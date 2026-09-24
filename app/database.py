import json
import os
import random
import sqlite3
import uuid
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aurora.db"
DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"

AREAS: dict[str, dict] = {}
APARTAMENTOS: dict[str, dict] = {}


def _load_static_data() -> None:
    global AREAS, APARTAMENTOS
    if AREAS:
        return
    with open(DADOS_DIR / "areas.json", encoding="utf-8") as f:
        for a in json.load(f):
            AREAS[a["id"]] = a
    with open(DADOS_DIR / "apartamentos.json", encoding="utf-8") as f:
        for a in json.load(f):
            APARTAMENTOS[a["numero"]] = a


_load_static_data()


def _gerar_codigo(codigos_existentes: set[str]) -> str:
    while True:
        codigo = f"RSV-{random.randint(1000, 9999)}"
        if codigo not in codigos_existentes:
            return codigo


async def get_db() -> aiosqlite.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH), timeout=30)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessoes (
                session_id TEXT PRIMARY KEY,
                apartamento TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reservas (
                codigo TEXT PRIMARY KEY,
                apartamento TEXT NOT NULL,
                area TEXT NOT NULL,
                data TEXT NOT NULL,
                UNIQUE(area, data)
            );
            CREATE TABLE IF NOT EXISTS visitantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento TEXT NOT NULL,
                nome TEXT NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS codigos_usados (
                codigo TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS confirmacoes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                detalhes TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente',
                apartamento TEXT NOT NULL
            );
        """)
        await db.commit()
    finally:
        await db.close()


async def registrar_sessao(session_id: str, apartamento: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO sessoes (session_id, apartamento) VALUES (?, ?)",
            (session_id, apartamento),
        )
        await db.commit()
    finally:
        await db.close()


async def obter_apartamento_sessao(session_id: str) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT apartamento FROM sessoes WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row["apartamento"] if row else None
    finally:
        await db.close()


async def listar_reservas_apartamento(apartamento: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT codigo, apartamento, area, data FROM reservas WHERE apartamento = ?",
            (apartamento,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def verificar_disponibilidade_area(area_id: str, data: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ?", (area_id, data)
        )
        row = await cursor.fetchone()
        return row is None
    finally:
        await db.close()


async def criar_reserva(apartamento: str, area_id: str, data: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT codigo FROM codigos_usados")
        usados = {row["codigo"] for row in await cursor.fetchall()}
        codigo = _gerar_codigo(usados)
        try:
            await db.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                (codigo, apartamento, area_id, data),
            )
            await db.execute(
                "INSERT INTO codigos_usados (codigo) VALUES (?)", (codigo,)
            )
            await db.commit()
            return {"sucesso": True, "codigo": codigo}
        except sqlite3.IntegrityError:
            return {
                "sucesso": False,
                "erro": f"A área '{area_id}' já está reservada para a data {data}.",
            }
    finally:
        await db.close()


async def cancelar_reserva(codigo: str, apartamento: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT codigo FROM reservas WHERE codigo = ? AND apartamento = ?",
            (codigo, apartamento),
        )
        row = await cursor.fetchone()
        if not row:
            return {
                "sucesso": False,
                "erro": f"Reserva '{codigo}' não encontrada para o seu apartamento.",
            }
        await db.execute("DELETE FROM reservas WHERE codigo = ?", (codigo,))
        await db.commit()
        return {"sucesso": True}
    finally:
        await db.close()


async def listar_visitantes_apartamento(apartamento: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ?", (apartamento,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )
        await db.commit()
        return {"sucesso": True}
    finally:
        await db.close()


async def criar_confirmacao(
    session_id: str, tipo: str, detalhes: dict, apartamento: str
) -> str:
    conf_id = str(uuid.uuid4())[:8]
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO confirmacoes (id, session_id, tipo, detalhes, status, apartamento) VALUES (?, ?, ?, ?, 'pendente', ?)",
            (conf_id, session_id, tipo, json.dumps(detalhes, ensure_ascii=False), apartamento),
        )
        await db.commit()
        return conf_id
    finally:
        await db.close()


async def obter_confirmacao(conf_id: str, session_id: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM confirmacoes WHERE id = ? AND session_id = ?",
            (conf_id, session_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def atualizar_confirmacao(conf_id: str, status: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE confirmacoes SET status = ? WHERE id = ?", (status, conf_id)
        )
        await db.commit()
    finally:
        await db.close()


async def listar_confirmacoes_pendentes(session_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, tipo, detalhes FROM confirmacoes WHERE session_id = ? AND status = 'pendente'",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "acao": r["tipo"],
                "detalhes": json.loads(r["detalhes"]),
            })
        return result
    finally:
        await db.close()


async def restaurar_dados() -> None:
    db = await get_db()
    try:
        await db.execute("DELETE FROM reservas")
        await db.execute("DELETE FROM visitantes")
        await db.execute("DELETE FROM confirmacoes")
        await db.execute("DELETE FROM codigos_usados")
        await db.execute("DELETE FROM sessoes")

        with open(DADOS_DIR / "reservas.json", encoding="utf-8") as f:
            reservas = json.load(f)
        for r in reservas:
            await db.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data) VALUES (?, ?, ?, ?)",
                (r["codigo"], r["apartamento"], r["area"], r["data"]),
            )
            await db.execute(
                "INSERT INTO codigos_usados (codigo) VALUES (?)", (r["codigo"],)
            )

        with open(DADOS_DIR / "visitantes.json", encoding="utf-8") as f:
            visitantes = json.load(f)
        for v in visitantes:
            await db.execute(
                "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
                (v["apartamento"], v["nome"], v["data"]),
            )

        await db.commit()
    finally:
        await db.close()
