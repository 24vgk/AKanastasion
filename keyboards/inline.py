from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def selection_keyboard(
    width: int, *args: str, lst_button: str | None = None, **kwargs: str
) -> InlineKeyboardMarkup:
    kb_builder = InlineKeyboardBuilder()

    buttons: list[InlineKeyboardButton] = []

    if args:
        for button in args:
            buttons.append(
                InlineKeyboardButton(
                    text=(
                       button
                    ),
                    callback_data=button,
                )
            )

    if kwargs:
        for button, text in kwargs.items():
            buttons.append(InlineKeyboardButton(text=text, callback_data=button))

    kb_builder.row(*buttons, width=width)

    if lst_button:
        kb_builder.row(
            InlineKeyboardButton(text=lst_button, callback_data=lst_button)
        )
    return kb_builder.as_markup()


def confirm_cancel_keyboard(confirm_text="Подтвердить", cancel_text="Отмена") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=confirm_text, callback_data="confirm"),
            InlineKeyboardButton(text=cancel_text, callback_data="cancel"),
        ]
    ])
