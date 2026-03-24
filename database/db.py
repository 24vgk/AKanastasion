from __future__ import annotations

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from config import Config, load_config

config: Config = load_config()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL is not set. Put it in /root/Bot_You_Do1/.env or systemd Environment.")

# DB_URL должен быть вида:
# postgresql+asyncpg://vrabote:ПАРОЛЬ@localhost:5432/vrabote
engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    from database.models import Base  # локальный импорт, чтобы не ловить циклы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# мини-проверка соединения (можно дернуть при старте)
async def ping():
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
