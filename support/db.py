# support/db.py
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# =====================================================
#  Настройки БД
# =====================================================
# Пример строки подключения:
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/mydb
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ Не задан DATABASE_URL в .env")

# =====================================================
#  Инициализация движка и фабрики сессий
# =====================================================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,         # True — если нужно видеть SQL-запросы
    future=True,
    pool_pre_ping=True,  # проверяет соединение перед использованием
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # данные остаются доступны после commit
    autoflush=False,
    autocommit=False,
)

# =====================================================
#  Базовый класс для моделей
# =====================================================
Base = declarative_base()


# =====================================================
#  Функция инициализации БД (создание таблиц)
# =====================================================
async def init_db():
    """
    Создаёт таблицы, если их нет.
    Обычно вызывается один раз при старте бота.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
