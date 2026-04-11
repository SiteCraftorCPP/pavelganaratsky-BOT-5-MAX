from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_message_text = State()
    waiting_for_message_date = State()
    waiting_for_message_time = State()
    
    # For editing/deleting
    waiting_for_message_id_edit = State()
    waiting_for_message_id_delete = State()
    
    # For editing specific fields
    editing_message_id = State()
    editing_text = State()
    editing_date = State()
    editing_time = State()

    # Greeting / timezone texts
    editing_welcome_text_ru = State()
    editing_welcome_photo_ru = State()
    editing_welcome_text_en = State()
    editing_welcome_photo_en = State()

    editing_after_tz_text_ru = State()
    editing_after_tz_photo_ru = State()
    editing_after_tz_text_en = State()
    editing_after_tz_photo_en = State()

    # For schedule language targeting
    waiting_for_message_lang = State()
