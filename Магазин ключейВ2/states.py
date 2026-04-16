from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_developer = State()


class SupportStates(StatesGroup):
    waiting_for_question = State()


class PromoStates(StatesGroup):
    waiting_for_promo = State()


class AdminStates(StatesGroup):
    # --- Для добавления новой игры (Steam) ---
    waiting_for_game_name = State()
    waiting_for_game_selection = State()
    waiting_for_category = State()
    waiting_for_prices = State()
    waiting_for_keys = State()

    # --- Для редактирования товара ---
    edit_search = State()
    edit_select = State()
    edit_action = State()
    edit_new_price = State()
    edit_add_keys = State()
    edit_new_photo = State()
    edit_new_description = State()
    edit_confirm_delete = State()

    # --- Для ручного добавления (Подписки / Сервисы) ---
    manual_category = State()
    manual_platform = State()
    manual_name = State()
    manual_description = State()
    manual_price = State()
    manual_photo = State()
    manual_keys = State()
    manual_type = State()
    manual_service_info = State()