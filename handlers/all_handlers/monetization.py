from __future__ import annotations

from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import load_config
from database.crud import get_user_by_tg, topup_balance, buy_subscription

router = Router()
cfg = load_config()


def monetization_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # ⚠️ callback_data совпадают с фильтрами ниже
    kb.button(text="Пополнить", callback_data="topup_amount")
    # kb.button(text="Купить подписку", callback_data="buy_sub")
    kb.button(text="Назад", callback_data="profile")
    kb.adjust(2, 1)
    return kb.as_markup()


async def safe_edit(cb: CallbackQuery, text: str, kb: types.InlineKeyboardMarkup | None = None):
    """Безопасное редактирование — одна реализация на файл."""
    try:
        if cb.message and cb.message.text is not None:
            await cb.message.edit_text(text=text, reply_markup=kb)
        elif cb.message and cb.message.caption is not None:
            await cb.message.edit_caption(caption=text, reply_markup=kb)
        else:
            await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
    except TelegramBadRequest as e:
        s = str(e)
        if "message is not modified" in s:
            await cb.answer()
        elif "no text in the message to edit" in s:
            await cb.message.answer(text, reply_markup=kb)
            await cb.answer()
        else:
            raise


@router.callback_query(F.data == "monetization_menu")
async def monetization_menu(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    cents = int(user.balance_cents or 0) if user else 0
    bal = f"{cents / 100:.2f} ₽"
    text = (
        "💳 <b>Кошелек</b>\n"
        f"Баланс: <b>{bal}</b>\n\n"
        "Пополните Ваш баланс…"
    )
    await safe_edit(cb, text, monetization_kb())


# ─────────────────────────────
# Шаг 1. Выбор суммы пополнения
# ─────────────────────────────
def choose_amount_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for rub in (100, 300, 500):
        kb.button(text=f"{rub} ₽", callback_data=f"topup_{rub}")
    kb.button(text="Назад", callback_data="monetization_menu")
    kb.adjust(3, 1)
    return kb.as_markup()


@router.callback_query(F.data == "topup_amount")
async def choose_amount(cb: CallbackQuery):
    """Показывает выбор суммы пополнения."""
    await safe_edit(cb, "💰 Выбери сумму пополнения:", choose_amount_kb())


# ─────────────────────────────
# Шаг 2. Заглушка для оплаты
# ─────────────────────────────
@router.callback_query(F.data.regexp(r"^topup_\d+$"))
async def topup_process(cb: CallbackQuery):
    """Заглушка под интеграцию с системой оплаты."""
    amount_rub = int(cb.data.split("_")[1])
    amount_kop = amount_rub * 100

    # 🧩 Здесь в будущем можно создать реальный платёж и показать ссылку
    # payment_url = create_payment_link(user_id=cb.from_user.id, amount=amount_rub)
    # await safe_edit(cb, f"Оплата {amount_rub} ₽. Перейдите по ссылке:\n{payment_url}")

    # Пока просто симулируем успешное пополнение
    ok = await topup_balance(cb.from_user.id, amount_kop)
    msg = f"✅ Баланс пополнен на {amount_rub} ₽." if ok else "❌ Не удалось пополнить баланс."
    await safe_edit(cb, msg, monetization_kb())


@router.callback_query(F.data == "buy_sub")
async def do_buy_sub(cb: CallbackQuery):
    ok, msg = await buy_subscription(
        telegram_id=cb.from_user.id,
        price_kop=cfg.tariff.sub_price_kop,
        days=cfg.tariff.sub_duration_days,
    )
    await safe_edit(cb, ("✅ " if ok else "❌ ") + msg, monetization_kb())
