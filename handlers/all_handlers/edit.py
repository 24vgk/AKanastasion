import asyncio
from time import sleep

from Lexicon import button, lexicon
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from Lexicon import button
from database.db import SessionLocal
from database.crud import update_user_info, get_user_by_telegram_id
from keyboards.inline import selection_keyboard
from .states import EditProfile
import re

router = Router()

PHONE_REGEX = re.compile(r"^\+?\d{10,15}$")
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")


keyboard_start_reg = selection_keyboard(2, **button.start_reg_selection)
keyboard_edit_profile = selection_keyboard(1, **button.edit_profile_selection)


# Хэндлер выбора поля
@router.callback_query(F.data.startswith("edit_"), StateFilter(EditProfile.choosing_field))
async def choose_field(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data[5:]

    if field == "cancel":
        await callback.message.edit_caption(caption="❌ Редактирование отменено.")

        async with SessionLocal() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)

            await asyncio.sleep(2)
            caption = lexicon.start_zak if user.role == 'заказчик' else lexicon.start_isp
            await callback.message.edit_caption(caption=caption, reply_markup=keyboard_start_reg)

        await state.clear()
        return

    # Сохраняем field + идентификаторы сообщения
    await state.update_data(
        field=field,
        message_id=callback.message.message_id,
        chat_id=callback.message.chat.id
    )

    await callback.message.edit_caption(
        caption=f"✏️ Введите новое значение для «{field.replace('_', ' ')}»:"
    )

    await state.set_state(EditProfile.editing_field)


@router.message(StateFilter(EditProfile.editing_field))
async def process_new_value(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    field = data.get("field")
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    new_value = message.text.strip()

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception as e:
        print(f"Не удалось удалить сообщение: {e}")

    # Валидация
    if field == "phone":
        if not PHONE_REGEX.match(new_value):
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption="❌ Неверный формат телефона. Попробуйте ещё раз."
            )
            return

    elif field == "email":
        if new_value != "-" and not EMAIL_REGEX.match(new_value):
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption="❌ Неверный формат email. Попробуйте ещё раз или введите «-» для очистки."
            )
            return

    # Обновляем данные
    async with SessionLocal() as session:
        success = await update_user_info(
            session,
            telegram_id=message.from_user.id,
            **{field: None if new_value == "-" else new_value}
        )

    if success:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=f"✅ Поле «{field.replace('_', ' ')}» успешно обновлено!",
            reply_markup=keyboard_edit_profile
        )
    else:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption="❌ Ошибка обновления. Попробуйте позже."
        )

    await state.clear()


# @router.callback_query(F.data == "edit_cancel")
# async def edit_cancel(callback: types.CallbackQuery):
#     async with SessionLocal() as session:
#         user = await get_user_by_telegram_id(session, callback.from_user.id)
#
#         caption = lexicon.start_zak if user.role == 'заказчик' else lexicon.start_isp
#         await callback.message.edit_caption(
#             caption=caption,
#             reply_markup=keyboard_start_reg
#         )