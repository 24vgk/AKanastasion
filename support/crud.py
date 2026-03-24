from typing import Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String

Base = declarative_base()


class ThreadLink(Base):
    __tablename__ = "thread_links"

    user_id = Column(BigInteger, primary_key=True, index=True)
    thread_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), default="active", index=True)  # active | pending | closed | spam
    pinned_message_id = Column(Integer, nullable=True)
    unread = Column(Integer, default=0)  # 0 = прочитано, 1 = новое сообщение


async def get_thread_by_user(session: AsyncSession, user_id: int) -> Optional[int]:
    result = await session.execute(
        select(ThreadLink.thread_id).where(ThreadLink.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_thread(session: AsyncSession, thread_id: int) -> Optional[int]:
    result = await session.execute(
        select(ThreadLink.user_id).where(ThreadLink.thread_id == thread_id)
    )
    return result.scalar_one_or_none()


async def save_thread(session: AsyncSession, user_id: int, thread_id: int) -> None:
    result = await session.execute(
        select(ThreadLink).where(ThreadLink.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.thread_id = thread_id
        existing.status = "active"
    else:
        session.add(ThreadLink(user_id=user_id, thread_id=thread_id, status="active"))
    await session.commit()


async def update_status(session: AsyncSession, thread_id: int, status: str) -> None:
    await session.execute(
        update(ThreadLink).where(ThreadLink.thread_id == thread_id).values(status=status)
    )
    await session.commit()


async def delete_thread(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(ThreadLink).where(ThreadLink.user_id == user_id))
    await session.commit()


async def init_db():
    from db import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
