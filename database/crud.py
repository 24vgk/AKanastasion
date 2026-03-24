from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

from sqlalchemy import select, delete, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.db import SessionLocal
from database.models import User, SupportThread, Payment


# === USERS ===

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    stmt = (select(User).where(User.telegram_id == telegram_id))
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_all_users(session: AsyncSession) -> list[User]:
    res = await session.execute(select(User))
    return list(res.scalars().all())


async def create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    full_name: str,
    phone: str,
    email: Optional[str],
) -> User:
    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
        phone=phone,
        email=email,
        balance_cents=0,
        subscription_until=None,
    )
    session.add(user)
    await session.flush()
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_info(session: AsyncSession, telegram_id: int, **kwargs) -> bool:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)
    await session.commit()
    return True


async def delete_user(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    await session.delete(user)
    await session.commit()
    return True



# === SUPPORT THREADS ===

async def get_thread_by_user(session: AsyncSession, user_id: int) -> Optional[int]:
    res = await session.execute(
        select(SupportThread.thread_id).where(SupportThread.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def save_thread(session: AsyncSession, user_id: int, thread_id: int) -> None:
    thread = SupportThread(user_id=user_id, thread_id=thread_id, created_at=func.now())
    session.add(thread)
    await session.commit()


async def delete_thread(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(SupportThread).where(SupportThread.user_id == user_id))
    await session.commit()


# === БАЛАНС/ПОДПИСКА ===
# Публичные API — сессия опциональна; внутренняя реализация выделена отдельно.

async def _topup_balance_with_session(session: AsyncSession, telegram_id: int, amount_kop: int) -> bool:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        return False
    user.add_funds_kop(amount_kop)
    try:
        session.add(Payment(user_id=user.id, amount_cents=amount_kop, kind="topup"))
    except Exception:
        # если Payment не нужен/нет миграции — не падаем
        pass
    await session.commit()
    return True


async def _buy_subscription_with_session(
    session: AsyncSession, telegram_id: int, price_kop: int, days: int
) -> Tuple[bool, str]:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        return False, "Пользователь не найден."
    if not user.charge_kop(price_kop):
        need = price_kop - (user.balance_cents or 0)
        return False, f"Недостаточно средств. Не хватает {need/100:.2f} ₽."
    try:
        session.add(Payment(user_id=user.id, amount_cents=-price_kop, kind="subscription"))
    except Exception:
        pass
    user.activate_subscription(days)
    await session.commit()
    until = user.subscription_until
    if until and until.tzinfo is not None:
        until = until.astimezone(timezone.utc)
    return True, f"Подписка активна до {until:%d.%m.%Y %H:%M} (UTC)."


async def topup_balance(telegram_id: int, amount_kop: int, *, session: AsyncSession | None = None) -> bool:
    if session is not None:
        return await _topup_balance_with_session(session, telegram_id, amount_kop)
    async with SessionLocal() as s:  # собственная сессия, если не передали
        return await _topup_balance_with_session(s, telegram_id, amount_kop)


async def buy_subscription(
    *, telegram_id: int, price_kop: int, days: int, session: AsyncSession | None = None
) -> Tuple[bool, str]:
    if session is not None:
        return await _buy_subscription_with_session(session, telegram_id, price_kop, days)
    async with SessionLocal() as s:
        return await _buy_subscription_with_session(s, telegram_id, price_kop, days)


# Автопродление: запускается раз в сутки
async def autorenew_subscriptions(price_kop: int, days: int, bot) -> int:
    now = datetime.utcnow()
    day_end = datetime(now.year, now.month, now.day) + timedelta(days=1)
    count = 0
    async with SessionLocal() as session:
        res = await session.execute(
            select(User).where(
                (User.subscription_until.is_(None)) | (User.subscription_until <= day_end)
            )
        )
        for u in res.scalars().all():
            if (u.balance_cents or 0) >= price_kop:
                u.charge_kop(price_kop)
                try:
                    session.add(Payment(user_id=u.id, amount_cents=-price_kop, kind="subscription_autorenew"))
                except Exception:
                    pass
                u.activate_subscription(days)
                count += 1
                try:
                    await bot.send_message(
                        u.telegram_id,
                        f"✅ Подписка автоматически продлена до {u.subscription_until:%d.%m.%Y %H:%M} (UTC)."
                    )
                except Exception:
                    pass
        await session.commit()
    return count


# Напоминания «за N дней до конца»
async def notify_expiring_subscriptions(days_before: int, bot) -> int:
    now = datetime.utcnow()
    start = now + timedelta(days=days_before)
    end = start + timedelta(days=1)
    count = 0
    async with SessionLocal() as session:
        res = await session.execute(
            select(User).where(
                and_(
                    User.subscription_until.is_not(None),
                    User.subscription_until >= start,
                    User.subscription_until < end,
                )
            )
        )
        for u in res.scalars().all():
            try:
                await bot.send_message(
                    u.telegram_id,
                    "⏰ Напоминание: ваша подписка заканчивается "
                    f"через {days_before} дн. (до {u.subscription_until:%d.%m.%Y %H:%M} UTC).\n"
                    "Чтобы продлить, пополните баланс или оформите продление в разделе «Монетизация»."
                )
                count += 1
            except Exception:
                pass
    return count


# === SETTINGS ===

async def get_user_with_settings_by_tg(session: AsyncSession, tg_id: int) -> Optional[User]:
    stmt = (
        select(User)
        .options(selectinload(User.settings))
        .where(User.telegram_id == tg_id)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


# --- совместимость со старым кодом ---
async def get_user_by_tg(telegram_id: int):
    """Обёртка для совместимости со старыми импортами."""
    async with SessionLocal() as session:
        return await get_user_by_telegram_id(session, telegram_id)
