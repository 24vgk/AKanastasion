from aiogram import Router, F, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram3_calendar import SimpleCalendar
from aiogram3_calendar.calendar_types import SimpleCalendarCallback
from sqlalchemy import select

from Lexicon import button, lexicon
from config import load_config
from database.db import SessionLocal
from database.models import Order, User
from handlers.all_handlers.states import CreateOrder
from handlers.start import keyboard_start_reg_order
from keyboards.inline import (
    selection_keyboard,
)
from zoneinfo import ZoneInfo
from datetime import datetime, date, time

config = load_config()
router = Router()

# Основные клавиатуры
# keyboard_create_work = build_category_keyboard(button.category_structure)
keyboard_create_work_photo = selection_keyboard(2, **button.need_photo)
keyboard_create_work_file = selection_keyboard(2, **button.need_file)
keyboard_create_endwork = selection_keyboard(2, **button.end_work_selection)
keyboard_start_reg = selection_keyboard(2, **button.start_reg_selection)


TZ = ZoneInfo("Europe/Moscow")  # московская таймзона

def parse_start_date(value) -> datetime | None:
    if value in (None, "", " "):
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ)

    if isinstance(value, date):
        return datetime.combine(value, time(9, 0), tzinfo=TZ)

    if isinstance(value, str):
        v = value.strip()
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(v, fmt)
                if fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                    dt = dt.replace(hour=9, minute=0)
                return dt.replace(tzinfo=TZ)
            except ValueError:
                continue

    raise ValueError(f"Unsupported start_date format: {value!r}")

def parse_price_cents(value) -> int | None:
    if value in (None, "", " "):
        return None
    # доп. защита от "5 000", "5,000"
    if isinstance(value, str):
        v = value.replace(" ", "").replace(",", "")
        return int(v)
    return int(value)


# === 1. Начало создания заказа ===
@router.callback_query(F.data == "create_work")
async def start_create_order(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_caption(caption="Введите название мероприятия:")
    await state.set_state(CreateOrder.title)


# === 4. Ввод названия ===
@router.message(CreateOrder.title)
async def input_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(
        "📅 Выберите дату, мероприятия:",
        reply_markup=await SimpleCalendar().start_calendar(),
    )


# === 5. Выбор даты ===
@router.callback_query(SimpleCalendarCallback.filter())
async def process_simple_calendar(
    callback_query: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext
):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        await state.update_data(start_date=date.strftime("%d.%m.%Y"))
        await callback_query.message.answer(
            f"✅ Вы выбрали дату: <b>{date.strftime('%d.%m.%Y')}</b>\n\n📝 Теперь опишите мероприятие:",
            parse_mode="HTML",
        )
        await state.set_state(CreateOrder.description)


# === 6. Ввод описания ===
@router.message(CreateOrder.description)
async def input_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("📸 Нужно прикрепить фото?", reply_markup=keyboard_create_work_photo)
    await state.set_state(CreateOrder.need_photo)


# === 7. Обработка выбора по фото ===
@router.callback_query(CreateOrder.need_photo, F.data.startswith("need_photo"))
async def choose_photo_option(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.endswith("yes"):
        await callback.message.edit_text("Отправьте фото:")
        await state.set_state(CreateOrder.photo)
    else:
        await state.update_data(photo=None)
        await callback.message.edit_text("📎 Нужно прикрепить файлы?", reply_markup=keyboard_create_work_file)
        await state.set_state(CreateOrder.need_file)


# === 8. Приём фото ===
@router.message(CreateOrder.photo, F.photo)
async def get_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("📎 Нужно прикрепить файлы?", reply_markup=keyboard_create_work_file)
    await state.set_state(CreateOrder.need_file)


# === 9. Выбор прикрепления файла ===
@router.callback_query(CreateOrder.need_file, F.data.endswith("yes"))
async def choose_file_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправьте файл:")
    await state.set_state(CreateOrder.file)

@router.callback_query(CreateOrder.need_file, F.data.endswith("no"))
async def choose_file_no(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(file=None)
    await callback.message.edit_text("💰 Укажите стоимость участия:")
    await state.set_state(CreateOrder.price)


# === 10. Приём файла ===
@router.message(CreateOrder.file, F.document)
async def get_file(message: types.Message, state: FSMContext):
    await state.update_data(file=message.document.file_id)
    await message.answer("💰 Укажите стоимость участия:")
    await state.set_state(CreateOrder.price)


# === 11. Ввод цены и предпросмотр ===
@router.message(CreateOrder.price)
async def input_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    data = await state.get_data()

    text = (
        f"<b>📦 Предпросмотр мероприятия:</b>\n\n"
        f"📌 Название: {data.get('title')}\n"
        f"📅 Дата: {data.get('start_date')}\n"
        f"📝 Описание: {data.get('description')}\n"
        f"💰 Цена: {data.get('price')} ₴"
    )

    await message.answer(text, reply_markup=keyboard_create_endwork)
    await state.set_state(CreateOrder.confirm)


# === 12. Публикация заказа с сохранением channel_message_id ===
@router.callback_query(CreateOrder.confirm, F.data == "publish_order")
async def publish_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    async with SessionLocal() as session:
        # Получаем пользователя
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await callback.message.answer("Ошибка: пользователь не найден.")
            await state.clear()
            return

        # Создаем заказ
        start_date = parse_start_date(data.get("start_date"))
        price_cents = parse_price_cents(data.get("price_cents") or data.get("price"))

        order = Order(
            user_id=user.id,
            worker_id=None,
            title=data["title"],  # у вас nullable=False → требуемо
            start_date=start_date,  # datetime с tzinfo (или None)
            description=data["description"],  # nullable=False
            photo=data.get("photo"),
            file=data.get("file"),
            price_cents=price_cents or 0,  # int
            status="Ожидает откликов",  # <-- явное значение вместо NULL
            cancel_pending=False,  # <-- явное значение вместо NULL
            channel_message_id=None,
            cancel_reason=None,
        )
        session.add(order)
        await session.commit()  # commit чтобы получить order.id

        cat_name = button.category_structure[order.category]["name"]
        sub_name = button.category_structure[order.category]["subcategories"][order.subcategory]

        # Сообщение для канала
        text = (
            f"🆕 <b>Новое мероприятие #{order.id}</b>\n\n"
            f"📌 <b>Название:</b> {order.title}\n"
            f"📅 <b>Дата начала:</b> {order.start_date}\n"
            f"📝 <b>Описание:</b>\n{order.description}\n"
            f"💰 <b>Цена:</b> {order.price_cents} ₴\n"
            f"💬 Уже записалось: 0"  # счетчик откликов
        )

        bot = callback.bot
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📄 Подробнее",
                url=f"https://t.me/{(await bot.me()).username}?start=order_{order.id}"
            )]
        ])

        # Отправка в канал и сохранение channel_message_id
        try:
            if order.photo:
                msg = await bot.send_photo(
                    chat_id=config.tg_bot.channel_id,
                    photo=order.photo,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            else:
                msg = await bot.send_message(
                    chat_id=config.tg_bot.channel_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

            # Сохраняем ID сообщения в заказе для обновления
            order.channel_message_id = msg.message_id
            session.add(order)
            await session.commit()

        except Exception as e:
            await callback.message.answer(f"Ошибка при отправке в канал: {e}")
            await state.clear()
            return

        await callback.message.edit_text("✅ Мероприятие опубликовано и отправлено в канал!")

        # Возвращаем пользователя на стартовую клавиатуру
        start_text = lexicon.start
        await callback.message.answer_photo(
            photo=types.FSInputFile("img/640_360.png"),
            caption=start_text,
            reply_markup=keyboard_start_reg_order,
        )

        await state.clear()

# === 13. Перезапуск или отмена ===
@router.callback_query(CreateOrder.confirm, F.data == "restart_order")
async def restart_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await start_create_order(callback, state)


@router.callback_query(CreateOrder.confirm, F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🚪 Вы вышли из создания мероприятия.")
    await state.clear()
