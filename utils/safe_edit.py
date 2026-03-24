# utils/safe_edit.py
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

async def safe_edit(cb: types.CallbackQuery, text: str, kb: types.InlineKeyboardMarkup | None = None):
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
