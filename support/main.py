import asyncio
import logging
import os
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatType, ChatAction
from aiogram.filters import CommandStart, Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from crud import (
    init_db, get_thread_by_user, save_thread, delete_thread,
    get_user_by_thread, update_status, ThreadLink
)
from db import SessionLocal

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

TOPIC_COLORS = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]
TOPIC_EMOJIS = ["💬", "🧑", "📩", "🤝", "📞", "🛠", "🗣"]

WAIT_TIMERS = {}
WAIT_TIMEOUT = 10 * 60
AUTO_CLOSE_TIMERS = {}
AUTO_CLOSE_TIMEOUT = 24 * 60 * 60

STATUS_NAMES = {
    "active": "🟢 Активна",
    "pending": "🕓 В ожидании",
    "closed": "🔒 Закрыта",
    "spam": "🚫 Спам",
}

# ================== утилиты ==================
class StatusCallback(CallbackData, prefix="status"):
    thread_id: int
    status: str

def admin_topic_buttons(thread_id: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Активна", callback_data=f"set_status:{thread_id}:active"),
            InlineKeyboardButton(text="В ожидании", callback_data=f"set_status:{thread_id}:pending"),
            InlineKeyboardButton(text="Закрыта", callback_data=f"set_status:{thread_id}:closed")
        ],
        [
            InlineKeyboardButton(text="Спам", callback_data=f"set_status:{thread_id}:spam")
        ]
    ])
    return kb

async def tg_retry(coro_func, *args, **kwargs):
    """Простой ретрай на TelegramRetryAfter, до 3 попыток."""
    for i in range(3):
        try:
            return await coro_func(*args, **kwargs)
        except TelegramRetryAfter as e:
            delay = int(getattr(e, "retry_after", 1)) + 1
            logger.warning("Flood control: retry after %s s (try %s/3)", delay, i+1)
            await asyncio.sleep(delay)
    # финальная попытка — пусть падёт, чтобы увидеть реальную ошибку
    return await coro_func(*args, **kwargs)

# ================== ТЕМЫ ==================
async def get_or_create_thread(session: AsyncSession, bot: Bot, user: types.User) -> int:
    """
    ТВОЯ логика + убрали 'send_chat_action' (он и вызывал flood).
    Валидацию 'живости' темы делаем в момент реальной отправки (см. send_in_topic_safe).
    """
    thread_id = await get_thread_by_user(session, user.id)

    # (Убрали send_chat_action как проверку «живости» темы)
    if thread_id:
        try:
            thread_id = int(thread_id)
            return thread_id
        except Exception:
            await delete_thread(session, user.id)
            thread_id = None

    emoji = random.choice(TOPIC_EMOJIS)
    color = random.choice(TOPIC_COLORS)

    topic = await tg_retry(bot.create_forum_topic,
                           chat_id=GROUP_ID,
                           name=f"{emoji} {user.full_name}",
                           icon_color=color)
    thread_id = topic.message_thread_id
    await save_thread(session, user.id, thread_id)

    text_message = (
        f"{emoji} <b>Создана новая тема поддержки!</b>\n\n"
        f"👤 Пользователь: <b>{user.full_name}</b>\n"
        f"🆔 <code>{user.id}</code>\n"
        f"📅 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>\n\n"
        "💬 Все сообщения из ЛС будут появляться здесь."
    )

    photos = await tg_retry(bot.get_user_profile_photos, user_id=user.id, limit=1)
    if photos.total_count > 0:
        file_id = photos.photos[0][-1].file_id
        msg = await tg_retry(bot.send_photo,
                             chat_id=GROUP_ID,
                             message_thread_id=thread_id,
                             photo=file_id,
                             caption=text_message,
                             parse_mode="HTML",
                             reply_markup=admin_topic_buttons(thread_id))
    else:
        msg = await tg_retry(bot.send_message,
                             chat_id=GROUP_ID,
                             message_thread_id=thread_id,
                             text=text_message,
                             parse_mode="HTML",
                             reply_markup=admin_topic_buttons(thread_id))

    t = await session.get(ThreadLink, user.id)
    t.pinned_message_id = msg.message_id
    await session.commit()

    return thread_id

async def send_in_topic_safe(session: AsyncSession, user: types.User, send_factory):
    """
    Пытается отправить в текущую тему; если получаем 'message thread not found' / 'TOPIC_ID_INVALID' —
    удаляем связку, создаём новую тему и повторяем отправку; в крайнем случае — без темы.
    send_factory(tid_or_None) -> coroutine
    """
    thread_id = await get_thread_by_user(session, user.id)
    try:
        if thread_id:
            return await tg_retry(send_factory, int(thread_id))
        else:
            new_tid = await get_or_create_thread(session, bot, user)
            return await tg_retry(send_factory, new_tid)
    except TelegramBadRequest as e:
        if "message thread not found" in str(e).lower() or "TOPIC_ID_INVALID" in str(e):
            await delete_thread(session, user.id)
            new_tid = await get_or_create_thread(session, bot, user)
            try:
                return await tg_retry(send_factory, new_tid)
            except TelegramBadRequest:
                # финальная попытка — без темы
                return await tg_retry(send_factory, None)
        raise

# ================== PIN-карточка ==================
async def update_topic_card(session: AsyncSession, thread_id: int):
    user_id = await get_user_by_thread(session, thread_id)
    if not user_id:
        return

    t_link = await session.get(ThreadLink, user_id)
    if not t_link:
        return

    try:
        user = await tg_retry(bot.get_chat, user_id)
        full_name = user.full_name
    except Exception:
        full_name = str(user_id)

    status_text = STATUS_NAMES.get(t_link.status, t_link.status)
    marker = "🔴 НОВОЕ!" if t_link.unread else ""

    caption = (
        f"{marker}\n"
        f"👤 <b>{full_name}</b>\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📅 <i>{datetime.now().strftime('%d.%m.%Y %H:%M')}</i>\n\n"
        f"💬 Все сообщения из ЛС будут появляться здесь.\n"
        f"Статус: {status_text}"
    )

    photos = await tg_retry(bot.get_user_profile_photos, user_id=user_id, limit=1)
    has_photo = photos.total_count > 0
    file_id = photos.photos[0][-1].file_id if has_photo else None

    kb = admin_topic_buttons(thread_id)

    try:
        if t_link.pinned_message_id:
            # редактируем существующее сообщение
            if has_photo:
                await tg_retry(bot.edit_message_media,
                               chat_id=GROUP_ID,
                               message_id=t_link.pinned_message_id,
                               media=InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML"),
                               reply_markup=kb)
            else:
                await tg_retry(bot.edit_message_text,
                               chat_id=GROUP_ID,
                               message_id=t_link.pinned_message_id,
                               text=caption,
                               parse_mode="HTML",
                               reply_markup=kb)
        else:
            # создаём новое pinned-сообщение
            if has_photo:
                msg = await tg_retry(bot.send_photo,
                                     chat_id=GROUP_ID,
                                     message_thread_id=thread_id,
                                     photo=file_id,
                                     caption=caption,
                                     parse_mode="HTML",
                                     reply_markup=kb)
            else:
                msg = await tg_retry(bot.send_message,
                                     chat_id=GROUP_ID,
                                     message_thread_id=thread_id,
                                     text=caption,
                                     parse_mode="HTML",
                                     reply_markup=kb)
            t_link.pinned_message_id = msg.message_id
            await session.commit()
    except TelegramBadRequest as e:
        # если сообщение удалили — создадим заново
        if "message to edit not found" in str(e).lower():
            t_link.pinned_message_id = None
            await session.commit()
            await update_topic_card(session, thread_id)
        # если тема умерла — пересоздаём и повторяем
        elif "message thread not found" in str(e).lower() or "TOPIC_ID_INVALID" in str(e):
            await delete_thread(session, user_id)
            new_tid = await get_or_create_thread(session, bot, types.User(id=user_id, is_bot=False, first_name=full_name))
            await update_topic_card(session, new_tid)
        else:
            logger.warning("Не удалось обновить pinned-сообщение темы: %s", e)

# ================== КНОПКИ СТАТУСА ==================
@dp.callback_query(F.data.startswith("set_status:"))
async def handle_status_button(callback: types.CallbackQuery):
    try:
        _, thread_id_str, status = callback.data.split(":")
        thread_id = int(thread_id_str)
    except Exception:
        await callback.answer("Некорректные данные кнопки", show_alert=True)
        return

    async with SessionLocal() as session:
        user_id = await get_user_by_thread(session, thread_id)
        if not user_id:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        await set_thread_status(session, thread_id, status, callback.from_user)

    await callback.answer(f"Статус темы изменён на {STATUS_NAMES[status]}")

# ================== СТАТУС ТЕМЫ ==================
async def set_thread_status(session: AsyncSession, thread_id: int, status: str, admin: types.User):
    user_id = await get_user_by_thread(session, thread_id)
    if not user_id:
        return

    # (Оставим попытку переименовать, но НЕ падаем, если TOPIC_ID_INVALID)
    try:
        await tg_retry(bot.edit_forum_topic,
                       chat_id=GROUP_ID,
                       message_thread_id=thread_id,
                       name=f"{STATUS_NAMES[status]} | Тема {user_id}")
    except TelegramBadRequest as e:
        if "TOPIC_ID_INVALID" in str(e):
            logger.info("edit_forum_topic: TOPIC_ID_INVALID — пропускаю переименование (тема общая/удалена).")
        else:
            logger.warning("Не удалось изменить название темы: %s", e)

    await update_status(session, thread_id, status)
    await update_topic_card(session, thread_id)

# ================== ПЛАНИРОВЩИКИ ==================
# ВАЖНО: не передавать открытую session в таски — берём новую внутри
async def schedule_pending_status(thread_id: int, admin: types.User):
    if thread_id in WAIT_TIMERS:
        WAIT_TIMERS[thread_id].cancel()

    async def _task():
        try:
            await asyncio.sleep(WAIT_TIMEOUT)
            async with SessionLocal() as session:
                await set_thread_status(session, thread_id, "pending", admin)
            await schedule_auto_close(thread_id)
        except asyncio.CancelledError:
            pass

    WAIT_TIMERS[thread_id] = asyncio.create_task(_task())

async def schedule_auto_close(thread_id: int):
    if thread_id in AUTO_CLOSE_TIMERS:
        AUTO_CLOSE_TIMERS[thread_id].cancel()

    async def _task():
        try:
            await asyncio.sleep(AUTO_CLOSE_TIMEOUT)
            async with SessionLocal() as session:
                await set_thread_status(session, thread_id, "closed",
                                        types.User(id=0, is_bot=True, first_name="Бот"))
        except asyncio.CancelledError:
            pass

    AUTO_CLOSE_TIMERS[thread_id] = asyncio.create_task(_task())

# ================== ХЭНДЛЕРЫ ==================
@dp.message(F.chat.type == ChatType.PRIVATE, ~F.text.startswith("/"))
async def handle_user_message(message: types.Message):
    async with SessionLocal() as session:
        # Получаем/создаём тему
        thread_id = await get_or_create_thread(session, bot, message.from_user)
        await set_thread_status(session, thread_id, "active", message.from_user)

        # Отмечаем как новое сообщение
        t_link = await session.get(ThreadLink, message.from_user.id)
        t_link.unread = 1
        await session.commit()

        # Универсальная отправка с авто-восстановлением темы
        async def factory(tid):
            kwargs = dict(chat_id=GROUP_ID)
            if tid: kwargs["message_thread_id"] = tid

            if message.text:
                return await bot.send_message(**kwargs,
                                              text=f"🧑 <b>{message.from_user.full_name}:</b>\n{message.text}",
                                              parse_mode="HTML")
            elif message.photo:
                return await bot.send_photo(**kwargs,
                                            photo=message.photo[-1].file_id,
                                            caption=message.caption or "")
            elif message.document:
                return await bot.send_document(**kwargs,
                                               document=message.document.file_id,
                                               caption=message.caption or "")
            elif message.video:
                return await bot.send_video(**kwargs,
                                            video=message.video.file_id,
                                            caption=message.caption or "")
            elif message.voice:
                return await bot.send_voice(**kwargs,
                                            voice=message.voice.file_id,
                                            caption=message.caption or "")
            elif message.audio:
                return await bot.send_audio(**kwargs,
                                            audio=message.audio.file_id,
                                            caption=message.caption or "")
            elif message.sticker:
                return await bot.send_sticker(**kwargs,
                                              sticker=message.sticker.file_id)
            elif message.animation:
                return await bot.send_animation(**kwargs,
                                                animation=message.animation.file_id,
                                                caption=message.caption or "")
            elif message.dice:
                return await bot.send_dice(**kwargs,
                                           emoji=message.dice.emoji)
            elif message.video_note:
                return await bot.send_video_note(**kwargs,
                                                 video_note=message.video_note.file_id)
            else:
                await message.reply("❌ Этот тип сообщения пока не поддерживается.")
                return None

        await send_in_topic_safe(session, message.from_user, factory)

        # Обновляем pinned-карточку
        await update_topic_card(session, thread_id)
#
# @dp.message(Command("groupid"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
# async def group_id_handler(message: types.Message):
#     await message.reply(
#         f"ID этой группы: <code>{message.chat.id}</code>\n"
#         f"ID темы: <code>{message.message_thread_id}</code>",
#         parse_mode="HTML"
#     )

@dp.message(F.chat.type == ChatType.SUPERGROUP)
async def handle_admin_reply(message: types.Message):
    async with SessionLocal() as session:
        thread_id = message.message_thread_id
        if not thread_id:
            return

        user_id = await get_user_by_thread(session, thread_id)
        if not user_id or message.from_user.is_bot:
            return

        await tg_retry(message.copy_to, chat_id=user_id)

        t_link = await session.get(ThreadLink, user_id)
        t_link.unread = 0
        await session.commit()

        await update_topic_card(session, thread_id)
        await schedule_pending_status(thread_id, message.from_user)

@dp.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start(message: types.Message):
    await message.reply(
        "👋 Привет! Я Бот поддержки сервиса V Работе.\n\n"
        "💡 Пишите мне по вопросам покупки меня!))"
    )

# ================== ЗАПУСК ==================
async def main():
    logger.info("Запуск бота и инициализация БД...")
    await init_db()

    # ВАЖНО: снести webhook перед polling, чтобы не было конфликта с другим инстансом
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning("delete_webhook: %s", e)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
