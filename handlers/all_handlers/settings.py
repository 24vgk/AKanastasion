# handlers/isp_handlers/settings.py
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

from database.db import SessionLocal
from database.crud import (
    get_user_with_settings_by_tg,
)
from utils.dates import is_active_until
from utils.safe_edit import safe_edit

router = Router()


def render_settings_text(*, autosub: bool, ads_effective: bool, ads_user_value: bool, sub_until) -> str:
    sub_str = sub_until.strftime("%Y-%m-%d %H:%M UTC") if sub_until else "нет"
    lock = "" if sub_until else " (недоступно без активной подписки)"
    return (
        "⚙️ <b>Настройки профиля</b>\n\n"
        f"• Автопродление: <b>{'Да' if autosub else 'Нет'}</b>\n"
        f"• Реклама (эффективно): <b>{'Получать' if ads_effective else 'Не получать'}</b>\n"
        f"• Реклама (ваше значение): <b>{'Получать' if ads_user_value else 'Не получать'}</b>{lock}\n"
        f"• Подписка до: <b>{sub_str}</b>\n"
    )


def build_settings_keyboard(*, is_sub: bool, autosub: bool, ads_value: bool) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=f"Автопродление: {'Да' if autosub else 'Нет'} ↔️", callback_data="settings:toggle_autorenew")],
    ]
    if is_sub:
        kb.append(
            [InlineKeyboardButton(text=f"Реклама: {'Получать' if ads_value else 'Не получать'} ↔️", callback_data="settings:toggle_ads")]
        )
    else:
        kb.append(
            [InlineKeyboardButton(text="Реклама: Получать (требуется подписка)", callback_data="settings:noop")]
        )
    kb.append([InlineKeyboardButton(text="« Назад", callback_data="profile")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.callback_query(F.data == "settings_menu")
async def open_settings(cb: types.CallbackQuery):
    async with SessionLocal() as session:
        user = await get_user_with_settings_by_tg(session, cb.from_user.id)
        if not user:
            await cb.answer("Пользователь не найден", show_alert=True)
            return

        st = await get_or_create_settings(session, user.id)

        # Эффективная логика показа рекламы:
        # - без подписки: всегда «получать» (True)
        # - с подпиской: берём пользовательский флаг
        is_sub = is_active_until(user.subscription_until)
        ads_effective = bool(st.ads_opt_in) if is_sub else True

        text = render_settings_text(
            autosub=bool(st.auto_subscribe),
            ads_effective=ads_effective,
            ads_user_value=bool(st.ads_opt_in),
            sub_until=user.subscription_until,
        )
        kb = build_settings_keyboard(is_sub=is_sub, autosub=bool(st.auto_subscribe), ads_value=bool(st.ads_opt_in))

    # ВАЖНО: после выхода из with мы больше не трогаем user/st — только готовые text/kb
    await safe_edit(cb, text, kb)


@router.callback_query(F.data == "settings:toggle_autorenew")
async def toggle_autorenew(cb: types.CallbackQuery):
    async with SessionLocal() as session:
        user = await get_user_with_settings_by_tg(session, cb.from_user.id)
        if not user:
            await cb.answer("Пользователь не найден", show_alert=True)
            return

        new_autosub = await toggle_auto_subscribe(session, user.id)
        # Пересобираем состояние целиком (стабильно)
        st = await get_or_create_settings(session, user.id)
        is_sub = is_active_until(user.subscription_until)
        ads_effective = bool(st.ads_opt_in) if is_sub else True

        text = render_settings_text(
            autosub=new_autosub,
            ads_effective=ads_effective,
            ads_user_value=bool(st.ads_opt_in),
            sub_until=user.subscription_until,
        )
        kb = build_settings_keyboard(is_sub=is_sub, autosub=new_autosub, ads_value=bool(st.ads_opt_in))
        await session.commit()

    await safe_edit(cb, text, kb)


@router.callback_query(F.data == "settings:toggle_ads")
async def toggle_ads(cb: types.CallbackQuery):
    async with SessionLocal() as session:
        user = await get_user_with_settings_by_tg(session, cb.from_user.id)
        if not user:
            await cb.answer("Пользователь не найден", show_alert=True)
            return

        is_sub = is_active_until(user.subscription_until)
        if not is_sub:
            await cb.answer("Изменение недоступно без активной подписки.", show_alert=True)
            return

        new_ads = await toggle_ads_opt_in(session, user.id)
        st = await get_or_create_settings(session, user.id)

        text = render_settings_text(
            autosub=bool(st.auto_subscribe),
            ads_effective=new_ads,  # с подпиской эффективно == пользовательскому
            ads_user_value=new_ads,
            sub_until=user.subscription_until,
        )
        kb = build_settings_keyboard(is_sub=True, autosub=bool(st.auto_subscribe), ads_value=new_ads)
        await session.commit()

    await safe_edit(cb, text, kb)


@router.callback_query(F.data == "settings:noop")
async def settings_noop(cb: types.CallbackQuery):
    await cb.answer("Опция доступна при активной подписке.", show_alert=True)
