from datetime import datetime, timezone

from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from Lexicon import button, lexicon
from database.crud import get_user_by_telegram_id, buy_subscription
from database.db import SessionLocal
from handlers.all_handlers.monetization import cfg
from handlers.all_handlers.states import EditProfile
from keyboards.inline import selection_keyboard
from utils.telegram import safe_edit_message

router = Router()

keyboard_start_reg = selection_keyboard(2, **button.start_reg_selection)
keyboard_profile = selection_keyboard(2, **button.profile_selection)
keyboard_edit_profile = selection_keyboard(1, **button.edit_profile_selection)

DEFAULT_PHOTO_ID = "AgACAgIAAxkBAAIJ7Gj57HHSpgtEGChTqxPeIYgYRsx_AAK_AAEyG91myEtFKa0piToJ8wEAAwIAA3kAAzYE"  # <-- твой file_id

def _fmt_money_rub_kop(kop: int) -> str:
    return f"{kop/100:.2f} ₽"

async def _safe_edit(
    cb: types.CallbackQuery,
    text: str,
    kb: types.InlineKeyboardMarkup | None = None,
    photo_id: str | None = None,
):
    photo=types.FSInputFile("img/profile.jpg")

    try:
        if cb.message and cb.message.photo:
            await cb.message.edit_media(
                media=types.InputMediaPhoto(media=photo, caption=text, parse_mode="HTML"),
                reply_markup=kb,
            )
        else:
            await cb.message.answer_photo(photo, caption=text, reply_markup=kb)
        await cb.answer()
    except Exception:
        await cb.message.answer_photo(photo, caption=text, reply_markup=kb)
        await cb.answer()

@router.callback_query(F.data == "profile")
async def on_edit_profile(callback: CallbackQuery):
    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        now = datetime.now(timezone.utc)
        sub_until = (
            user.subscription_until.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
            if user.subscription_until else "не активна"
        )
        active = bool(user.subscription_until and user.subscription_until > now)
        days_left = ((user.subscription_until - now).days if active else 0)

        text = (
            "🧾 <b>Профиль</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>\n"
            f"🧑 <b>Имя:</b> {user.full_name}\n"
            f"📱 <b>Телефон:</b> {user.phone}\n"
            f"📧 <b>Email:</b> {user.email or 'не указан'}\n"
            f"💰 <b>Баланс:</b> {user.balance_rub:.2f} ₽\n"
        )
        if active and days_left > 0:
            text += f"\n⏳ Осталось: <b>{days_left} дн.</b>"
        if not active:
            text += f"\n\nСтоимость продления: <b>{_fmt_money_rub_kop(cfg.tariff.sub_price_kop)}</b> на {cfg.tariff.sub_duration_days} дн."

        await _safe_edit(callback, text, keyboard_profile)

@router.callback_query(F.data == "profile_renew")
async def on_profile_renew(callback: CallbackQuery):
    """
    Попытаться списать стоимость подписки и продлить её.
    Если не хватает средств — предложим перейти в монетизацию (пополнение).
    """
    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        # если уже активна — просто обновим профиль
        now = datetime.now(timezone.utc)
        if user.subscription_until and user.subscription_until > now:
            await _safe_edit(callback, "🎟 Подписка уже активна. Обновляю профиль…", keyboard_profile)
            await on_edit_profile(callback)
            return

        ok, msg = await buy_subscription(
            telegram_id=callback.from_user.id,
            price_kop=cfg.tariff.sub_price_kop,
            days=cfg.tariff.sub_duration_days
        )

        if ok:
            # успешно — покажем свежие данные профиля
            await _safe_edit(callback, f"✅ {msg}", keyboard_profile)
            await on_edit_profile(callback)
        else:
            # не удалось списать — вероятно, недостаточно средств
            kb = InlineKeyboardBuilder()
            kb.button(text="Пополнить баланс", callback_data="monetization_menu")
            kb.button(text="Назад в профиль", callback_data="profile")
            kb.adjust(1, 1)
            await _safe_edit(
                callback,
                "❌ Не удалось продлить подписку.\n"
                "Вероятно, недостаточно средств на балансе.\n\n"
                f"Стоимость: <b>{_fmt_money_rub_kop(cfg.tariff.sub_price_kop)}</b> на {cfg.tariff.sub_duration_days} дн.",
                kb.as_markup()
            )

@router.callback_query(F.data.in_({"edit_profile"}))
async def on_edit_profile(callback: CallbackQuery, state: FSMContext):
    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    text = (
        "🛠 <b>Редактирование профиля</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"🧑 Имя: {user.full_name}\n"
        f"📱 Телефон: {user.phone}\n"
        f"📧 Email: {user.email or 'не указан'}\n"
        f"💰 Баланс: <b>{user.balance_rub:.2f} ₽</b>\n"
    )

    await safe_edit_message(
        message=callback.message,
        text=text,
        reply_markup=keyboard_edit_profile,
        parse_mode="HTML"
    )

    await state.set_state(EditProfile.choosing_field)