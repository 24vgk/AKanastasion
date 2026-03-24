from aiogram.types import Message, InputMediaPhoto
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest

async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
) -> None:
    """
    Редактирует текст, если это текстовое сообщение,
    или подпись, если это медиа-сообщение.
    """
    try:
        if message.content_type in {
            ContentType.PHOTO,
            ContentType.VIDEO,
            ContentType.DOCUMENT,
            ContentType.ANIMATION,
            ContentType.AUDIO,
        }:
            await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        # Подстраховка: если вдруг тип не совпал, пробуем альтернативу
        if "no caption" in str(e).lower():
            await message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif "message is not modified" in str(e).lower():
            # игнорируем "не изменилось"
            return
        else:
            raise