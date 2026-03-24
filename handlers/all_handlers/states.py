from aiogram.fsm.state import State, StatesGroup

class Register(StatesGroup):
    choosing_role = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_email = State()

class PortfolioState(StatesGroup):
    entering_repo = State()
    choosing_category = State()
    choosing_subcategory = State()
    choosing_language = State()
    entering_description = State()
    uploading_file = State()
    writing_comment = State()

class EditProfile(StatesGroup):
    choosing_field = State()
    editing_field = State()

class CreateOrder(StatesGroup):
    category = State()
    subcategory = State()
    title = State()
    start_date = State()
    description = State()
    need_photo = State()
    photo = State()
    need_file = State()
    file = State()
    price = State()
    confirm = State()

class OfferOrder(StatesGroup):
    waiting_for_offer = State()

class CancelOrder(StatesGroup):
    waiting_cancel_reason = State()