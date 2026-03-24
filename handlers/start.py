import re

import aiohttp
from aiogram import Router, F, types
from aiogram.filters import StateFilter, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select

from Lexicon import button, lexicon
from config import Config, load_config
from database.crud import get_user_by_telegram_id, create_user
from database.db import SessionLocal
from database.models import Order
from handlers.all_handlers.states import Register
from keyboards.inline import selection_keyboard

PHONE_REGEX = re.compile(r"^\+?\d{10,15}$")
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")

router = Router()


keyboard_start = selection_keyboard(1, **button.role_selection)
keyboard_start_reg = selection_keyboard(2, **button.start_reg_selection)
keyboard_start_reg_admin = selection_keyboard(2, **button.start_reg_selection_admin)
keyboard_start_reg_order = selection_keyboard(2, **button.start_reg_selection)

config: Config = load_config()

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

# Стартовое меню

async def render_start_menu(message: types.Message, state: FSMContext):
    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)

        if user:
            await message.answer_photo(
                photo=types.FSInputFile("img/640_360.png"),
                caption=lexicon.start,
                reply_markup=keyboard_start_reg
            )
            await state.clear()
            return

        await message.answer(
            "Привет!\nВы ещё не зарегистрированы.\nПожалуйста, пройдите регистрацию:",
            reply_markup=keyboard_start
        )
        await state.set_state(Register.choosing_role)

@router.callback_query(F.data.startswith("registration"), Register.choosing_role)
async def choose_role(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(f"Введите ваше ФИО:")
    await state.set_state(Register.waiting_name)

@router.message(Register.waiting_name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите ваш номер телефона:")
    await state.set_state(Register.waiting_phone)

@router.message(StateFilter(Register.waiting_phone))
async def get_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    if not PHONE_REGEX.match(phone):
        await message.answer("❌ Неверный формат телефона. Введите номер, например:\n+71234567890 или 89123456789")
        return

    await state.update_data(phone=phone)
    await message.answer("Введите ваш email (или напишите «-», если не хотите указывать):")
    await state.set_state(Register.waiting_email)


@router.message(StateFilter(Register.waiting_email))
async def get_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if email != "-" and not EMAIL_REGEX.match(email):
        await message.answer(
            "❌ Неверный формат email. Попробуйте снова или введите «-», если не хотите указывать почту."
        )
        return

    user_data = await state.get_data()

    async with SessionLocal() as session:
        user = await create_user(
            session,
            telegram_id=message.from_user.id,
            full_name=user_data["full_name"],
            phone=user_data["phone"],
            email=None if email == "-" else email,
        )

    await message.answer("✅ Регистрация завершена! Спасибо.")
    # Возвращаем пользователя в стартовое меню
    await send_start_menu(message, user, state)


async def send_start_menu(message: types.Message, user, state: FSMContext):
    """Отправляет стартовое меню в зависимости от роли пользователя."""

    await message.answer_photo(
        photo=types.FSInputFile("img/640_360.png"),
        caption=lexicon.start + f'\n{user.full_name}',
        reply_markup=keyboard_start_reg
    )
    await state.clear()


@router.callback_query(F.data == "contact")
async def support(callback: CallbackQuery):
    # Создаём кнопку для перехода в бот поддержки
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Перейти в бот поддержки",
                url="https://t.me/AKanastashn_support_bot"
            )],
            [InlineKeyboardButton(
                text="Назад в Меню",
                callback_data="edit_cancel"
            )]
        ]
    )

    await callback.message.edit_caption(
        caption="Для связи с поддержкой, пожалуйста, перейдите по кнопке ниже:",
        reply_markup=kb
    )

    # Закрываем callback
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def start_cmd(event: types.Message | types.CallbackQuery, callback: types.CallbackQuery):
    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        # унификация: определяем, кто пользователь и в какое сообщение отвечать
        if isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id  # <-- правильный user_id из callback
            msg = event.message  # сюда будем отвечать/редактировать
            is_callback = True
        else:
            user_id = event.from_user.id  # из обычного сообщения
            msg = event
            is_callback = False
        caption = lexicon.start + f"\n{user.full_name}"
        if user.is_admin:
            if is_callback and msg:
                await msg.edit_media(
                    media=types.InputMediaPhoto(
                        media=types.FSInputFile("img/640_360.png"),
                        caption=caption
                    ),
                    reply_markup=keyboard_start_reg_admin
                )
                await event.answer()
            else:
                await msg.answer_photo(
                    photo=types.FSInputFile("img/640_360.png"),
                    caption=caption,
                    reply_markup=keyboard_start_reg_admin
                )
            return
        else:
            if is_callback and msg:
                await msg.edit_media(
                    media=types.InputMediaPhoto(
                        media=types.FSInputFile("img/640_360.png"),
                        caption=caption
                    ),
                    reply_markup=keyboard_start_reg
                )
                await event.answer()
            else:
                await msg.answer_photo(
                    photo=types.FSInputFile("img/640_360.png"),
                    caption=caption,
                    reply_markup=keyboard_start_reg
                )
            return




# --- 1) Общая функция рендера стартового экрана ---
async def render_start(event: types.Message | types.CallbackQuery,
                       state: FSMContext | None = None) -> None:
    # унификация: определяем, кто пользователь и в какое сообщение отвечать
    if isinstance(event, types.CallbackQuery):
        user_id = event.from_user.id           # <-- правильный user_id из callback
        msg = event.message                    # сюда будем отвечать/редактировать
        is_callback = True
    else:
        user_id = event.from_user.id           # из обычного сообщения
        msg = event
        is_callback = False

    async with SessionLocal() as session:
        user = await get_user_by_telegram_id(session, user_id)

        if user:
            caption = lexicon.start + f"\n{user.full_name}"
            if user.is_admin:
                if is_callback and msg:
                    await msg.edit_media(
                        media=types.InputMediaPhoto(
                            media=types.FSInputFile("img/640_360.png"),
                            caption=caption
                        ),
                        reply_markup=keyboard_start_reg_admin
                    )
                    await event.answer()
                else:
                    await msg.answer_photo(
                        photo=types.FSInputFile("img/640_360.png"),
                        caption=caption,
                        reply_markup=keyboard_start_reg_admin
                    )
                return
            else:
                if is_callback and msg:
                    await msg.edit_media(
                        media=types.InputMediaPhoto(
                            media=types.FSInputFile("img/640_360.png"),
                            caption=caption
                        ),
                        reply_markup=keyboard_start_reg
                    )
                    await event.answer()
                else:
                    await msg.answer_photo(
                        photo=types.FSInputFile("img/640_360.png"),
                        caption=caption,
                        reply_markup=keyboard_start_reg
                    )
                return

        # не зарегистрирован
        await msg.answer(
            "Привет! Вы ещё не зарегистрированы.\nПожалуйста, выберите вашу роль:",
            reply_markup=keyboard_start
        )
        if state is not None:
            from handlers.all_handlers.states import Register
            await state.set_state(Register.choosing_role)


# /start и "тест"
@router.message(StateFilter(default_state), F.text.in_({"/start", "тест"}))
async def start_cmd(message: types.Message, state: FSMContext):
    await render_start(message, state)


# edit_cancel из callback
@router.callback_query(F.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await render_start(callback, state)

# @router.channel_post()
# async def channel_handler(message: types.Message):
#     print("КАНАЛ")
#     print(f"ID канала: {message.chat.id}")


# @router.message(F.photo)
# async def get_photo_id(message: types.Message):
#     photo_id = message.photo[-1].file_id
#     await message.answer(f"📎 file_id этого изображения:\n<code>{photo_id}</code>", parse_mode="HTML")