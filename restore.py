"""Restaura os dados iniciais do banco de dados a partir dos arquivos JSON."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import init_db, restaurar_dados


async def main():
    print("Inicializando banco de dados...")
    await init_db()
    print("Restaurando dados iniciais...")
    await restaurar_dados()
    print("Dados restaurados com sucesso!")
    print("  - Reservas: dados/reservas.json")
    print("  - Visitantes: dados/visitantes.json")


if __name__ == "__main__":
    asyncio.run(main())
