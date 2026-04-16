import config
import logging
import asyncio
import re
from aiogram import Bot, Dispatcher, F, types, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from keyboards import get_games_keyboard, GAMES_PER_PAGE, get_accounts_keyboard
from states import SearchStates, SupportStates, PromoStates
from base import SQL
from handlers_steam import router as steam_router
from ai_support import handle_ai_support
from handlers_admin import admin_router
from aiogram.filters import Command

db = SQL('db.db')

bot = Bot(token=config.TOKEN)
dp = Dispatcher()
main_router = Router()  # Главный роутер для этого файла

logging.basicConfig(level=logging.INFO)

# --- КЛАВИАТУРЫ ---
buttons_main = [
    [InlineKeyboardButton(text="🛍️ Каталог", callback_data="category")],
    [InlineKeyboardButton(text="🛒 Моя корзина", callback_data="basket")],
    [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
    [InlineKeyboardButton(text="📞🤖 Поддержка (Нейросеть)", callback_data="help_neyro")],
]
kb_main = InlineKeyboardMarkup(inline_keyboard=buttons_main)

buttons_category = [
    [InlineKeyboardButton(text="Подписки Нейросети", callback_data="subscribes")],
    [InlineKeyboardButton(text="Игровые сервисы", callback_data="accounts")],
    [InlineKeyboardButton(text="Игры Steam", callback_data="games_steam")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
]
kb_category = InlineKeyboardMarkup(inline_keyboard=buttons_category)

buttons_subscribes = [
    [InlineKeyboardButton(text="ChatGPT", callback_data="chat_gpt_menu")],
    [InlineKeyboardButton(text="Gemini", callback_data="gemini_menu")],
    [InlineKeyboardButton(text="Grok AI", callback_data="grok_menu")],
    [InlineKeyboardButton(text="Claude", callback_data="claude_menu")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="category")],
]
kb_subscribes = InlineKeyboardMarkup(inline_keyboard=buttons_subscribes)

kb_accounts_platforms = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Playstation 🎮", callback_data="acc_ps")],
    [InlineKeyboardButton(text="Steam 💨", callback_data="acc_steam")],
    [InlineKeyboardButton(text="Xbox 🟢", callback_data="acc_xbox")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="category")],
])

buttons_after_ai = [
    [InlineKeyboardButton(text="👤 Написать администратору", url="tg://user?id=1626312647")],
    [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
]
kb_after_ai = InlineKeyboardMarkup(inline_keyboard=buttons_after_ai)


# --- ФУНКЦИЯ ДЛЯ ПЛАВНОЙ ЗАМЕНЫ СООБЩЕНИЙ ---
async def safe_edit_text(call: types.CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup):
    """Помогает менять экраны без создания новых сообщений снизу"""
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")


@main_router.message(Command("cancel"))
@main_router.message(F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("🚫 Действие отменено. Возвращаюсь в меню.", reply_markup=kb_main)


# --- ОБРАБОТКА КОМАНД ---

def get_dynamic_kb(items, back_callback):
    """Динамически собирает клавиатуру из товаров БД"""
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for item_id, name, price in items:
        # Каждая кнопка содержит название, цену и ведет на стандартную покупку
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{name} — {price}₽", callback_data=f"buy_id_{item_id}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return kb


def get_main_kb(is_admin=False):
    buttons = [
        [InlineKeyboardButton(text="🛍️ Каталог", callback_data="category")],
        [InlineKeyboardButton(text="🛒 Моя корзина", callback_data="basket")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📞🤖 Поддержка (Нейросеть)", callback_data="help_neyro")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@main_router.message(Command("start"), F.text)
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if not db.user_exist(user_id):
        db.add_user(user_id)
    is_admin = db.get_field("users", user_id, "admin")
    start_text = (
        "🌟 <b>Привет!</b> 🌟\n"
        "Ты находишься в магазине <b>SharkStore</b> 🦈.\n"
        "Мы гарантируем мгновенную доставку цифровых товаров 24/7.\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>ПОЧЕМУ ВЫБИРАЮТ НАС:</b>\n"
        "• ⚡ Мгновенная автоматическая выдача товаров\n"
        "• 🔒 100% конфиденциальность и безопасность\n"
        "• 💳 Удобные способы оплаты\n"
        "• 🆘 Круглосуточная поддержка 24/7\n"
        "• ✅ Гарантия качества на все товары\n"
    )
    # Всем выводится магазин. Но у админа будет дополнительная кнопка внизу!
    await message.answer(start_text, reply_markup=get_main_kb(is_admin), parse_mode="HTML")


# --- ОБРАБОТКА ЛОГИКИ ПРОМОКОДА ---
@main_router.message(PromoStates.waiting_for_promo)
async def promo_logic(message: types.Message, state: FSMContext):
    promo_code = message.text
    discount = db.check_promo(promo_code)

    if discount:
        await state.update_data(active_discount=discount)
        text = f"✅ Промокод применен! Скидка: <b>{discount} руб.</b>\nПерейдите в корзину для оплаты."
    else:
        text = "❌ Такого промокода не существует или он закончился."

    await state.set_state(None)
    await message.answer(text, reply_markup=kb_main, parse_mode="HTML")


# --- ОБРАБОТКА ПОИСКА ИГР (FSM) ---

@main_router.message(SearchStates.waiting_for_query)
async def process_search(message: types.Message, state: FSMContext):
    data = await state.get_data()
    category = data.get("search_cat")
    query = message.text

    # Ищем игру, но фильтруем только "базовые" записи (key_), чтобы избежать тройных дублей
    db.cursor.execute("""
        SELECT steam_id, name FROM items 
        WHERE steam_category = ? AND name LIKE ? AND steam_id LIKE 'key_%'
    """, (category, f"%{query}%"))
    results = db.cursor.fetchall()

    if not results:
        await message.answer(
            f"❌ По запросу «{query}» ничего не найдено в категории {category}. Попробуйте еще раз или нажмите /start.")
        return

    kb_results = []
    for steam_id, name in results:
        # Очищаем название от "Steam [Ключ]: " и достаем чистый ID
        clean_name = name.replace("Steam [Ключ]: ", "").strip()
        app_id = steam_id.replace("key_", "")

        # Направляем кнопку на нашу новую красивую карточку игры
        kb_results.append([InlineKeyboardButton(text=clean_name, callback_data=f"steam_game_{app_id}")])

    kb_results.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"show_cat_{category}")])

    await message.answer(f"✅ Найдено по запросу «<b>{query}</b>»:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_results), parse_mode="HTML")
    await state.clear()


# --- ОБРАБОТКА НЕЙРОСЕТИ (FSM) ---

@main_router.message(SupportStates.waiting_for_question)
async def ai_support_logic(message: types.Message, state: FSMContext, bot: Bot):
    await handle_ai_support(message, state, bot)
    await message.answer("Если нужна более точная информация, вы можете написать администратору:",
                         reply_markup=kb_after_ai)


# --- ОБРАБОТКА КНОПОК (CALLBACK) ---

@main_router.callback_query()
async def start_call(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id

    if call.data == "back_to_main":
        is_admin = db.get_field("users", user_id, "admin")
        start_text = (
            "🌟 <b>Привет!</b> 🌟\n"
            "Ты находишься в магазине <b>SharkStore</b> 🦈.\n"
            "Мы гарантируем мгновенную доставку цифровых товаров 24/7.\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "✨ <b>ПОЧЕМУ ВЫБИРАЮТ НАС:</b>\n"
            "• ⚡ Мгновенная автоматическая выдача товаров\n"
            "• 🔒 100% конфиденциальность и безопасность\n"
            "• 💳 Удобные способы оплаты\n"
            "• 🆘 Круглосуточная поддержка 24/7\n"
            "• ✅ Гарантия качества на все товары\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Навигация:</b>\n"
            "• 🛍️ Каталог — посмотреть все товары\n"
            "• 🛒 Моя корзина — просмотреть корзину\n"
            "• 👤 Мой профиль — покупки и баланс\n"
            "• 📞🤖 Поддержка — связаться с нейросетью\n"
        )
        await safe_edit_text(call, start_text, get_main_kb(is_admin))

    if call.data == "category":
        await safe_edit_text(call, "🛒 <b>Категории товаров:</b>", kb_category)

    if call.data == "profile":
        balance = db.get_field("users", user_id, "balance") or 0
        db.cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 1", (user_id,))
        purchases_count = db.cursor.fetchone()[0]

        text = (
            f"👤 <b>Личный кабинет</b>\n\n"
            f"🔑 <b>Ваш ID:</b> <code>{user_id}</code>\n"
            f"💰 <b>Баланс:</b> {balance} руб.\n"
            f"📦 <b>Куплено товаров:</b> {purchases_count} шт.\n"
        )

        kb_profile = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Мои покупки", callback_data="orders")],
            [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="balance")],
            [InlineKeyboardButton(text="🎟 Активировать промокод", callback_data="enter_promo")],
            [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
        ])
        await safe_edit_text(call, text, kb_profile)

    if call.data == "balance":
        await call.answer("🛠 Раздел пополнения баланса находится в разработке!", show_alert=True)
        return

    if call.data == "subscribes":
        await safe_edit_text(call, "🤖 <b>Подписки на Нейросети:</b>", kb_subscribes)

    if call.data == "help_neyro":
        await state.set_state(SupportStates.waiting_for_question)
        kb_cancel = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_main")]])
        await safe_edit_text(call, "🤖 Я — нейросеть-помощник SharkStore.\nНапишите ваш вопрос текстовым сообщением!",
                             kb_cancel)
        await call.answer()
        return

    if call.data == "accounts":
        buttons = [
            [InlineKeyboardButton(text="🎮 Playstation", callback_data="acc_ps")],
            [InlineKeyboardButton(text="🟢 Xbox", callback_data="acc_xbox")],
            [InlineKeyboardButton(text="💨 Steam", callback_data="acc_steam")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="category")]
        ]
        await safe_edit_text(call, "<b>Выберите платформу:</b>", InlineKeyboardMarkup(inline_keyboard=buttons))

    # --- ДИНАМИЧЕСКОЕ МЕНЮ: ПОДПИСКИ НЕЙРОСЕТЕЙ ---
    if call.data in ["chat_gpt_menu", "gemini_menu", "grok_menu", "claude_menu"]:
        platform_map = {
            "chat_gpt_menu": ("ChatGPT", "chatgpt"),
            "gemini_menu": ("Gemini", "gemini"),
            "grok_menu": ("Grok AI", "grok"),
            "claude_menu": ("Claude", "claude")
        }
        display_name, db_plat = platform_map[call.data]

        # Достаем тарифы из базы
        items = db.get_custom_items("subscribes", db_plat)

        if not items:
            await call.answer(f"Тарифы для {display_name} пока не добавлены или закончились!", show_alert=True)
            return

        kb = get_dynamic_kb(items, "subscribes")
        await safe_edit_text(call, f"🤖 Вы выбрали <b>{display_name}</b>. Доступные тарифы:", kb)

    # --- ДИНАМИЧЕСКОЕ МЕНЮ: ИГРОВЫЕ СЕРВИСЫ ---
    if call.data in ["acc_ps", "acc_steam", "acc_xbox"]:
        platform_map = {
            "acc_ps": ("PlayStation", "PS"),
            "acc_xbox": ("Xbox", "XBOX"),
            "acc_steam": ("Steam", "STEAM")
        }
        display_name, db_plat = platform_map[call.data]

        # Достаем товары из базы
        items = db.get_custom_items("accounts", db_plat)

        if not items:
            await call.answer(f"Сервисы для {display_name} пока не добавлены или закончились!", show_alert=True)
            return

        kb = get_dynamic_kb(items, "accounts")
        await safe_edit_text(call, f"🎮 <b>Доступные сервисы {display_name}:</b>", kb)

    if call.data.startswith("search_start_"):
        category = call.data.replace("search_start_", "")
        await state.update_data(search_cat=category)
        await state.set_state(SearchStates.waiting_for_query)
        kb_cancel = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data=f"show_cat_{category}")]])
        await safe_edit_text(call, f"🔎 Введите название игры для поиска в категории <b>{category}</b>:", kb_cancel)
        await call.answer()
        return

    if call.data.startswith("show_cat_") or call.data.startswith("page_"):
        if call.data.startswith("show_cat_"):
            category = call.data.replace("show_cat_", "")
            page = 0
        else:
            parts = call.data.split("_")
            category = parts[1]
            page = int(parts[2])

        offset = page * GAMES_PER_PAGE
        games = db.get_games_by_category(category, GAMES_PER_PAGE, offset)
        total = db.count_games_in_category(category)

        text = f"📂 <b>Список игр: {category} (Стр. {page + 1})</b>"
        kb = get_games_keyboard(games, category, page, total)
        await safe_edit_text(call, text, kb)

    if call.data == "games_steam":
        buttons = [
            [InlineKeyboardButton(text="🆕 Новинки", callback_data="cat_new")],
            [InlineKeyboardButton(text="🌟 AAA игры", callback_data="cat_aaa")],
            [InlineKeyboardButton(text="👥 КООП игры", callback_data="cat_coop")],
            [InlineKeyboardButton(text="👨‍💻 Поиск по разработчику", callback_data="search_dev_start")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="category")]
        ]
        text = "🎯 <b>Магазин Steam</b>\nВыберите раздел:"
        await safe_edit_text(call, text, InlineKeyboardMarkup(inline_keyboard=buttons))

    if call.data.startswith("cat_"):
        category_code = call.data.split("_")[1]

        # Берем из базы только "базовые" игры (по префиксу key_), чтобы не было дублей в каталоге
        db.cursor.execute("SELECT steam_id, name FROM items WHERE steam_category = ? AND steam_id LIKE 'key_%'",
                          (category_code,))
        games = db.cursor.fetchall()

        if not games:
            await call.answer("В этой категории пока нет товаров!", show_alert=True)
            return

        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for steam_id, name in games:
            # Очищаем название от технических приписок (убираем "Steam [Ключ]: ")
            clean_name = name.replace("Steam [Ключ]: ", "").strip()
            app_id = steam_id.replace("key_", "")

            kb.inline_keyboard.append([InlineKeyboardButton(text=clean_name, callback_data=f"steam_game_{app_id}")])

        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="games_steam")])

        cat_names = {"new": "НОВИНКИ", "aaa": "AAA ИГРЫ", "coop": "КООП ИГРЫ"}
        display_name = cat_names.get(category_code, category_code.upper())
        await safe_edit_text(call, f"📂 <b>Игры в разделе {display_name}:</b>", kb)

    if call.data.startswith("stbuy_"):
        parts = call.data.split("_")
        buy_type, app_id = parts[1], parts[2]
        from steam_parser import get_steam_game_info
        game = get_steam_game_info(app_id)

        if game:
            import re
            clean_text = re.sub(r'(\d+)\s+(?=\d)', r'\1', str(game['price']))
            match = re.search(r'Актуальная цена:.*?(\d+(?:[.,]\d+)?)\s*руб', clean_text)

            if match:
                steam_price = int(float(match.group(1).replace(',', '.')))
            else:
                fallback = re.search(r'(\d+(?:[.,]\d+)?)\s*руб', clean_text)
                steam_price = int(float(fallback.group(1).replace(',', '.'))) if fallback else 0

            # ПРОВЕРЯЕМ БАЗУ: Если админ уже добавил эту игру, берем его цену!
            db_steam_id = f"{buy_type}_{app_id}"
            db.cursor.execute("SELECT price FROM items WHERE steam_id = ?", (db_steam_id,))
            saved_item = db.cursor.fetchone()

            if saved_item:
                current_price = saved_item[0]  # Берем 1000 рублей из базы
            else:
                # Если в базе нет, считаем по старой логике наценок
                if buy_type == "acc":
                    current_price = steam_price - 150
                elif buy_type == "gift":
                    current_price = steam_price + 250
                else:  # key
                    current_price = steam_price + 450
                current_price = max(current_price, 50)

            type_names = {"acc": "👤 Аккаунт", "gift": "🎁 Гифт", "key": "🔑 Ключ"}
            type_text = type_names.get(buy_type, "Товар")

            confirm_text = (
                f"📝 <b>Подтверждение заказа</b>\n\n"
                f"🎮 <b>Игра:</b> {game['name']}\n"
                f"📦 <b>Способ:</b> {type_text}\n"
                f"💳 <b>Цена в Steam:</b> {steam_price} руб.\n"
                f"🔥 <b>Наша цена:</b> {current_price} руб.\n\n"
                f"Нажмите подтвердить, чтобы добавить товар в корзину."
            )

            kb_confirm = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить и в корзину", callback_data=f"confst_{buy_type}_{app_id}")],
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"steam_game_{app_id}")]
            ])

            if call.message.photo:
                await call.message.edit_caption(caption=confirm_text, reply_markup=kb_confirm, parse_mode="HTML")
            else:
                await call.message.edit_text(confirm_text, reply_markup=kb_confirm, parse_mode="HTML")
        else:
            await call.answer("❌ Ошибка получения данных", show_alert=True)

    if call.data.startswith("confst_"):
        parts = call.data.split("_")
        buy_type, app_id = parts[1], parts[2]
        from steam_parser import get_steam_game_info
        game = get_steam_game_info(app_id)

        if game:
            item_id = db.get_or_create_steam_item(app_id, game['name'], game['price'], buy_type,
                                                  developer=game.get('developers', 'Unknown'))
            db.add_order(user_id, item_id)
            await call.answer("✅ Добавлено в корзину!", show_alert=True)

            kb_success = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Перейти в корзину", callback_data="basket")],
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
            ])
            # Заменяем сообщение на подтверждение добавления
            await safe_edit_text(call, "🛒 <b>Товар успешно добавлен в корзину!</b>", kb_success)

    if call.data.startswith("steam_game_"):
        raw_id = call.data.replace("steam_game_", "")
        app_id = raw_id.replace("key_", "").replace("gift_", "").replace("acc_", "")

        from steam_parser import get_steam_game_info
        game = get_steam_game_info(app_id)

        if game:
            # Ищем все 3 цены И ОПИСАНИЕ в базе данных по ID игры
            db.cursor.execute("SELECT steam_id, price, description FROM items WHERE steam_id IN (?, ?, ?)",
                              (f"key_{app_id}", f"gift_{app_id}", f"acc_{app_id}"))

            rows = db.cursor.fetchall()

            # Собираем найденные цены в словарь {'key': 1500, 'gift': 1800, 'acc': 1000}
            prices_data = {row[0].split('_')[0]: row[1] for row in rows}

            # Ищем кастомное описание, если админ его задал для версии 'key_...'
            custom_desc = next((row[2] for row in rows if row[0] == f"key_{app_id}" and row[2]), None)

            # Если админ задал описание, берем его. Если нет — берем стандартное из Steam
            final_description = custom_desc if custom_desc else game['description']

            admin_price_text = ""
            kb_card = InlineKeyboardMarkup(inline_keyboard=[])

            if prices_data:
                admin_price_text = (
                    f"🔥 <b>Наши цены:</b>\n"
                    f"🔑 Ключ: {prices_data.get('key', '❌')} руб.\n"
                    f"🎁 Гифт: {prices_data.get('gift', '❌')} руб.\n"
                    f"👤 Аккаунт: {prices_data.get('acc', '❌')} руб.\n\n"
                )

                # Динамически создаем кнопки покупки
                if 'key' in prices_data:
                    kb_card.inline_keyboard.append(
                        [InlineKeyboardButton(text=f"🔑 Купить ключом", callback_data=f"stbuy_key_{app_id}")])
                if 'gift' in prices_data:
                    kb_card.inline_keyboard.append(
                        [InlineKeyboardButton(text=f"🎁 Купить гифтом", callback_data=f"stbuy_gift_{app_id}")])
                if 'acc' in prices_data:
                    kb_card.inline_keyboard.append(
                        [InlineKeyboardButton(text=f"👤 Купить аккаунтом", callback_data=f"stbuy_acc_{app_id}")])

            # Добавляем стандартные кнопки в конец
            kb_card.inline_keyboard.append(
                [InlineKeyboardButton(text="🖼 Скриншоты", callback_data=f"screens_{app_id}")])
            kb_card.inline_keyboard.append(
                [InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="games_steam")])

            text = (
                f"🎮 <b>{game['name']}</b>\n\n"
                f"📝 <b>Описание:</b> {final_description}\n\n"
                f"👨‍💻 <b>Разработчик:</b> {game['developers']}\n"
                f"🎭 <b>Жанры:</b> {game['genres']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Справочные цены в Steam:</b>\n"
                f"{game['price']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{admin_price_text}"
                f"ℹ️ <i>Выберите удобный способ приобретения ниже:</i>"
            )

            await call.message.delete()
            await call.message.answer_photo(photo=game['image'], caption=text, reply_markup=kb_card, parse_mode="HTML")
        else:
            await call.answer("❌ Не удалось получить данные из Steam", show_alert=True)

    if call.data.startswith("screens_"):
        raw_id = call.data.replace("screens_", "")

        # Срезаем префиксы для скриншотов
        app_id = raw_id.replace("key_", "").replace("gift_", "").replace("acc_", "")

        from steam_parser import get_steam_game_info
        game = get_steam_game_info(app_id)
        if game and game['screenshots']:
            media = [InputMediaPhoto(media=url) for url in game['screenshots']]
            await call.message.answer_media_group(media=media)
            await call.answer()
        else:
            await call.answer("❌ Скриншоты не найдены", show_alert=True)

    if call.data.startswith("buy_id_"):
        target_id = call.data.replace("buy_id_", "")

        # Оптимизация: вытаскиваем всю информацию разом одним запросом, включая item_type
        db.cursor.execute("SELECT name, price, stock, photo, description, item_type FROM items WHERE id = ?",
                          (target_id,))
        item_data = db.cursor.fetchone()

        if item_data:
            item_name, item_price, count, photo_id, item_desc, item_type = item_data

            kb_add = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 В корзину", callback_data=f"add_to_cart_{target_id}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="category")]
            ]) if count > 0 else InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="category")]])

            # Умная проверка: если это услуга, пишем просто "Доступно"
            if item_type == 'service':
                avail_text = "✅ Доступно для заказа"
            else:
                avail_text = f"✅ В наличии: {count} шт." if count > 0 else "❌ Нет в наличии"

            # Формируем текст с описанием, если оно есть
            desc_text = f"\n\n📝 <b>Описание:</b>\n{item_desc}\n" if item_desc else ""
            text = f"📦 <b>Товар:</b> {item_name}{desc_text}\n💰 <b>Цена:</b> {item_price} руб.\n📊 {avail_text}"

            # Если у товара есть фото, присылаем красивую карточку
            if photo_id:
                await call.message.delete()
                await call.message.answer_photo(photo=photo_id, caption=text, reply_markup=kb_add, parse_mode="HTML")
            else:
                await safe_edit_text(call, text, kb_add)
        else:
            await call.answer("❌ Товар не найден", show_alert=True)

    if call.data.startswith("add_to_cart_"):
        item_id = call.data.replace("add_to_cart_", "")
        db.add_order(user_id, item_id)
        await call.answer("✅ Товар добавлен в корзину!", show_alert=True)
        kb_success = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Корзина", callback_data="basket")],
            [InlineKeyboardButton(text="🛍️ Выбрать что-то еще", callback_data="category")]
        ])
        await safe_edit_text(call, "🛒 <b>Товар в корзине!</b> Что делаем дальше?", kb_success)

    if call.data == "basket":
        query = "SELECT item_id FROM orders WHERE user_id = ? AND status = 0"
        db.cursor.execute(query, (user_id,))
        rows = db.cursor.fetchall()
        if rows:
            text = "🛒 <b>Ваша корзина:</b>\n\n"
            total = 0
            for row in rows:
                item_id = row[0]
                name_item = db.get_field("items", item_id, "name")
                price_item = db.get_field("items", item_id, "price")
                text += f"🔹 {name_item} — {price_item} руб.\n"
                total += price_item

            data = await state.get_data()
            discount = data.get("active_discount", 0)
            final_price = max(0, total - discount)

            if discount > 0:
                text += f"\n🎟 Промокод: -{discount} руб."
            text += f"\n💰 Итого к оплате: <b>{final_price} руб.</b>"

            kb_basket = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay_order")],
                [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
                [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
            ])
            await safe_edit_text(call, text, kb_basket)
        else:
            await call.answer("🛒 Ваша корзина пуста!", show_alert=True)

    if call.data == "enter_promo":
        await state.set_state(PromoStates.waiting_for_promo)
        kb_cancel = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="profile")]])
        await safe_edit_text(call, "⌨️ <b>Введите промокод</b> в чат текстовым сообщением:", kb_cancel)
        await call.answer()

    if call.data == "clear_cart":
        db.cursor.execute("DELETE FROM orders WHERE user_id = ? AND status = 0", (user_id,))
        db.connection.commit()
        await call.answer("🗑 Корзина очищена!", show_alert=True)
        await safe_edit_text(call, "Ваша корзина пуста. Выберите раздел:", kb_main)

    if call.data == "pay_order":
        db.cursor.execute("SELECT item_id FROM orders WHERE user_id = ? AND status = 0", (user_id,))
        items_in_cart = db.cursor.fetchall()
        if not items_in_cart:
            await call.answer("Корзина пуста!", show_alert=True)
            return

        bought_items_text = "🎉 <b>Оплата прошла успешно!</b>\n\n"
        success_count = 0
        for row in items_in_cart:
            item_id = row[0]
            result_message = db.process_purchase(user_id, item_id)
            if result_message:
                bought_items_text += f"{result_message}\n━━━━━━━━━━━━━━━━━━━━━\n"
                success_count += 1
                if "админ" in result_message.lower():
                    await bot.send_message(config.ADMIN_ID, f"🔔 НОВЫЙ ЗАКАЗ!\nUser: {user_id}\nТовар ID: {item_id}")
        if success_count > 0:
            await state.update_data(active_discount=0)
            kb_after_pay = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")]])
            await safe_edit_text(call, bought_items_text, kb_after_pay)
        else:
            await call.answer("Произошла ошибка при выдаче товара.", show_alert=True)

    if call.data == "orders":
        query = "SELECT item_id, key FROM orders WHERE user_id = ? AND status = 1"
        db.cursor.execute(query, (user_id,))
        rows = db.cursor.fetchall()
        if rows:
            text = "📦 <b>Ваши купленные товары:</b>\n\n"
            for row in rows:
                item_id = row[0]
                name_item = db.get_field("items", item_id, "name")
                item_key = row[1]
                text += f"✅ {name_item}\n🔑 Ключ/Инфо: <code>{item_key}</code>\n"
                text += "━━━━━━━━━━━━━━━━━━━━━\n"
            kb_back_orders = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]])
            await safe_edit_text(call, text, kb_back_orders)
        else:
            await call.answer("📦 У вас пока нет купленных товаров.", show_alert=True)

    try:
        await call.answer()
    except Exception:
        pass

async def main():
    db.create_tables()
    # ПОРЯДОК ВАЖЕН:
    dp.include_router(steam_router)  # Роутер Steam
    dp.include_router(admin_router)  # НОВЫЙ Роутер админки
    dp.include_router(main_router)  # Главное меню (в самом конце)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())