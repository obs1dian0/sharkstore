from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Определяем константу прямо здесь
GAMES_PER_PAGE = 4


def get_steam_card_keyboard(app_id):
    buttons = [
        # Новые кнопки выбора типа покупки
        [InlineKeyboardButton(text="🔑 Купить ключом", callback_data=f"stbuy_key_{app_id}")],
        [InlineKeyboardButton(text="🎁 Купить подарком", callback_data=f"stbuy_gift_{app_id}")],
        [InlineKeyboardButton(text="👤 Купить аккаунтом", callback_data=f"stbuy_acc_{app_id}")],

        # Служебные кнопки (старые)
        [InlineKeyboardButton(text="🖼 Посмотреть скриншоты", callback_data=f"screens_{app_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="games_steam")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_accounts_keyboard(items_list, platform, page, total_count):
    rows = []

    # Кнопки товаров
    for name, item_id in items_list:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"buy_id_{item_id}")])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"accpage_{platform}_{page - 1}"))

    if (page + 1) * 6 < total_count:  # Допустим, по 6 товаров на странице
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"accpage_{platform}_{page + 1}"))

    if nav_buttons:
        rows.append(nav_buttons)

    rows.append([InlineKeyboardButton(text="🔙 Назад к платформам", callback_data="accounts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_games_keyboard(games_list, category, page, total_count):
    rows = []

    # 🔍 Кнопка поиска по текущей категории (всегда сверху)
    rows.append([
        InlineKeyboardButton(
            text=f"🔍 Найти в {category}",
            callback_data=f"search_start_{category}"
        )
    ])

    # games_list это список кортежей [(name, steam_id), ...] из БД
    for name, steam_id in games_list:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"steam_game_{steam_id}")])

    # Ряд кнопок навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"page_{category}_{page - 1}"))

    # Проверка: есть ли еще элементы дальше
    if (page + 1) * GAMES_PER_PAGE < total_count:
        nav_buttons.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"page_{category}_{page + 1}"))

    if nav_buttons:
        rows.append(nav_buttons)

    # Кнопка возврата к списку всех жанров
    rows.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="games_steam")])

    return InlineKeyboardMarkup(inline_keyboard=rows)