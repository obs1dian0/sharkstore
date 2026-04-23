from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states import AdminStates
from base import SQL

admin_router = Router()
db = SQL('db.db')


async def safe_edit_text(call: types.CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup):
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")


# --- ГЛАВНОЕ МЕНЮ АДМИНА ---
@admin_router.callback_query(F.data == "admin_panel")
async def open_admin_panel(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = call.from_user.id
    if not db.get_field("users", user_id, "admin"):
        return await call.answer("Нет доступа", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Добавить игру (Steam)", callback_data="add")],
        [InlineKeyboardButton(text="📦 Добавить другой товар", callback_data="add_manual")],
        [InlineKeyboardButton(text="✏️ Редактировать товар", callback_data="edit_item_start")],
        [InlineKeyboardButton(text="🎫 Создать промокод", callback_data="add_promo_start")],  # <-- НОВАЯ КНОПКА
        [InlineKeyboardButton(text="🔙 Вернуться в магазин", callback_data="back_to_main")]
    ])
    await safe_edit_text(call, "🛠 <b>Панель администратора</b>\nВыберите действие:", kb)


# ==========================================
# БЛОК 1: ДОБАВЛЕНИЕ НОВОЙ ИГРЫ
# ==========================================
@admin_router.callback_query(F.data == "add")
async def admin_add_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_game_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]])
    await safe_edit_text(call, "🛠 <b>Добавление игры</b>\nНапишите название игры для поиска в Steam:", kb)


@admin_router.message(AdminStates.waiting_for_game_name)
async def admin_search_game(message: types.Message, state: FSMContext):
    query = message.text
    from steam_parser import search_steam_games_by_name
    msg = await message.answer("🔍 Ищу в Steam...")
    results = search_steam_games_by_name(query)

    if not results:
        return await msg.edit_text("❌ В Steam ничего не найдено. Попробуйте написать иначе:")

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for game in results:
        short_name = game['name'][:20]
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text=game['name'], callback_data=f"adm_sel_{game['id']}_{short_name}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")])
    await msg.edit_text("✅ <b>Найдено в Steam.</b> Выберите нужную игру:", reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_game_selection)


@admin_router.callback_query(AdminStates.waiting_for_game_selection, F.data.startswith("adm_sel_"))
async def admin_select_game(call: types.CallbackQuery, state: FSMContext):
    app_id = call.data.split("_")[2]
    from steam_parser import get_steam_game_info
    game_info = get_steam_game_info(app_id)

    if not game_info:
        return await call.answer("❌ Ошибка Steam", show_alert=True)

    await state.update_data(add_app_id=app_id, add_name=game_info['name'], add_developer=game_info['developers'])

    kb_cat = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Новинка", callback_data="adm_cat_new")],
        [InlineKeyboardButton(text="🌟 AAA проект", callback_data="adm_cat_aaa")],
        [InlineKeyboardButton(text="👥 Кооп", callback_data="adm_cat_coop")]
    ])
    await safe_edit_text(call, f"🎮 Выбрана игра: <b>{game_info['name']}</b>\nКуда ее добавим?", kb_cat)
    await state.set_state(AdminStates.waiting_for_category)


@admin_router.callback_query(AdminStates.waiting_for_category, F.data.startswith("adm_cat_"))
async def admin_select_category(call: types.CallbackQuery, state: FSMContext):
    cat = call.data.replace("adm_cat_", "")
    await state.update_data(add_category=cat)
    await state.set_state(AdminStates.waiting_for_prices)

    text = (
        "💰 <b>Настройка цен</b>\n\n"
        "Введите <b>ТРИ</b> цены через пробел в таком порядке:\n"
        "<code>ЦенаКлюча ЦенаГифта ЦенаАккаунта</code>\n\n"
        "<i>Например: 1500 1800 1000</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]])
    await safe_edit_text(call, text, kb)


@admin_router.message(AdminStates.waiting_for_prices)
async def admin_set_prices(message: types.Message, state: FSMContext):
    prices = message.text.split()
    if len(prices) != 3 or not all(p.isdigit() for p in prices):
        return await message.answer("❌ Ошибка! Введите ровно 3 числа через пробел (например: 1500 1800 1000).")

    await state.update_data(prices_dict={'key': int(prices[0]), 'gift': int(prices[1]), 'acc': int(prices[2])})
    await state.set_state(AdminStates.waiting_for_keys)
    await message.answer("🔑 <b>Отправьте ключи</b> для этой игры (каждый с новой строки).", parse_mode="HTML")


@admin_router.message(AdminStates.waiting_for_keys)
async def admin_set_keys(message: types.Message, state: FSMContext):
    keys_list = [k.strip() for k in message.text.split('\n') if k.strip()]
    data = await state.get_data()

    added_count = db.add_game_complex(
        name=data['add_name'], prices=data['prices_dict'], steam_category=data['add_category'],
        developer=data['add_developer'], steam_id=data['add_app_id'], keys_list=keys_list
    )

    text = (
        f"✅ <b>Игра успешно добавлена!</b>\n\n"
        f"🎮 {data['add_name']}\n"
        f"🔑 Ключ: {data['prices_dict']['key']} руб. ({added_count} шт.)\n"
        f"🎁 Гифт: {data['prices_dict']['gift']} руб.\n"
        f"👤 Аккаунт: {data['prices_dict']['acc']} руб."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 В панель", callback_data="admin_panel")]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


# ==========================================
# БЛОК 2: РЕДАКТИРОВАНИЕ ТОВАРА В БД
# ==========================================
@admin_router.callback_query(F.data == "edit_item_start")
async def edit_start(call: types.CallbackQuery, state: FSMContext):
    results = db.get_all_local_items()

    if not results:
        return await call.answer("❌ В базе пока нет ни одного товара!", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # Telegram имеет лимит на количество кнопок, поэтому выводим 80 последних добавленных товаров
    for item_id, name, price, stock in results[:80]:
        # Немного обрезаем слишком длинные названия, чтобы кнопки выглядели аккуратно
        short_name = name[:35] + "..." if len(name) > 35 else name
        kb.inline_keyboard.append(
            [InlineKeyboardButton(text=f"{short_name} ({price}₽)", callback_data=f"adm_ed_{item_id}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")])

    await safe_edit_text(call, "✏️ <b>Редактирование</b>\nВыберите товар из списка ниже:", kb)
    await state.set_state(AdminStates.edit_select)


@admin_router.callback_query(AdminStates.edit_select, F.data.startswith("adm_ed_"))
async def edit_select(call: types.CallbackQuery, state: FSMContext):
    item_id = call.data.replace("adm_ed_", "")
    await state.update_data(edit_item_id=item_id)

    # --- НОВЫЕ КНОПКИ РЕДАКТИРОВАНИЯ ---
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Цена", callback_data="ed_act_price"),
         InlineKeyboardButton(text="🔑 Ключи", callback_data="ed_act_keys")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data="ed_act_photo"),
         InlineKeyboardButton(text="📝 Описание", callback_data="ed_act_desc")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="ed_act_delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_item_start")]
    ])
    await safe_edit_text(call, "⚙️ Что именно вы хотите сделать с этим товаром?", kb)
    await state.set_state(AdminStates.edit_action)


@admin_router.callback_query(AdminStates.edit_action, F.data.startswith("ed_act_"))
async def edit_action(call: types.CallbackQuery, state: FSMContext):
    action = call.data.replace("ed_act_", "")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]])

    if action == "price":
        await state.set_state(AdminStates.edit_new_price)
        await safe_edit_text(call, "💰 Введите новую цену в рублях (только цифры):", kb)
    elif action == "keys":
        await state.set_state(AdminStates.edit_add_keys)
        await safe_edit_text(call, "🔑 Отправьте новые ключи (каждый с новой строки):", kb)
    elif action == "photo":
        await state.set_state(AdminStates.edit_new_photo)
        await safe_edit_text(call, "🖼 Отправьте новую <b>фотографию</b> для этого товара:", kb)
    elif action == "delete":
        await state.set_state(AdminStates.edit_confirm_delete)
        kb_del = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚨 Да, удалить навсегда!", callback_data="confirm_delete")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]
        ])
        await safe_edit_text(call,
                             "⚠️ <b>ВНИМАНИЕ!</b>\nТовар и все загруженные для него ключи будут безвозвратно удалены. Продолжить?",
                             kb_del)
    elif action == "desc":
        await state.set_state(AdminStates.edit_new_description)
        await safe_edit_text(call, "📝 Отправьте новое <b>описание</b> для этого товара:", kb)

@admin_router.message(AdminStates.edit_new_description)
async def edit_save_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db.update_item_description(data['edit_item_id'], message.text)
    await message.answer("✅ Описание успешно обновлено!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="admin_panel")]]))
    await state.clear()

@admin_router.message(AdminStates.edit_new_price)
async def edit_save_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Только цифры!")
    data = await state.get_data()
    db.update_item_price(data['edit_item_id'], int(message.text))
    await message.answer("✅ Цена успешно обновлена!", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="admin_panel")]]))
    await state.clear()


@admin_router.message(AdminStates.edit_add_keys)
async def edit_save_keys(message: types.Message, state: FSMContext):
    keys_list = [k.strip() for k in message.text.split('\n') if k.strip()]
    data = await state.get_data()
    db.add_keys_to_existing_item(data['edit_item_id'], keys_list)
    await message.answer(f"✅ Добавлено {len(keys_list)} новых ключей в базу!", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="admin_panel")]]))
    await state.clear()


@admin_router.message(AdminStates.edit_new_photo, F.photo)
async def edit_save_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id  # Берем фото в лучшем качестве
    data = await state.get_data()
    db.update_item_photo(data['edit_item_id'], photo_id)
    await message.answer("✅ Фотография успешно обновлена!", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="admin_panel")]]))
    await state.clear()


@admin_router.callback_query(AdminStates.edit_confirm_delete, F.data == "confirm_delete")
async def edit_delete_confirm(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db.delete_item(data['edit_item_id'])
    await safe_edit_text(call, "🗑 <b>Товар успешно удален!</b>", InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="admin_panel")]]))
    await state.clear()


# ==========================================
# БЛОК 3: РУЧНОЕ ДОБАВЛЕНИЕ (ПОДПИСКИ / СЕРВИСЫ)
# ==========================================
@admin_router.callback_query(F.data == "add_manual")
async def manual_add_start(call: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Подписки Нейросети", callback_data="man_cat_subscribes")],
        [InlineKeyboardButton(text="🎮 Игровые сервисы", callback_data="man_cat_accounts")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]
    ])
    await safe_edit_text(call, "📦 <b>Добавление товара</b>\nВыберите категорию:", kb)
    await state.set_state(AdminStates.manual_category)


@admin_router.callback_query(AdminStates.manual_category, F.data.startswith("man_cat_"))
async def manual_category_select(call: types.CallbackQuery, state: FSMContext):
    cat = call.data.replace("man_cat_", "")
    await state.update_data(man_cat=cat)

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if cat == "subscribes":
        kb.inline_keyboard = [
            [InlineKeyboardButton(text="ChatGPT", callback_data="man_plat_chatgpt"),
             InlineKeyboardButton(text="Gemini", callback_data="man_plat_gemini")],
            [InlineKeyboardButton(text="Grok", callback_data="man_plat_grok"),
             InlineKeyboardButton(text="Claude", callback_data="man_plat_claude")]
        ]
    else:
        kb.inline_keyboard = [
            [InlineKeyboardButton(text="PlayStation", callback_data="man_plat_PS"),
             InlineKeyboardButton(text="Xbox", callback_data="man_plat_XBOX")],
            [InlineKeyboardButton(text="Steam", callback_data="man_plat_STEAM")]
        ]
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")])

    await safe_edit_text(call, "📌 Выберите платформу или сервис:", kb)
    await state.set_state(AdminStates.manual_platform)


@admin_router.callback_query(AdminStates.manual_platform, F.data.startswith("man_plat_"))
async def manual_platform_select(call: types.CallbackQuery, state: FSMContext):
    platform = call.data.replace("man_plat_", "")
    await state.update_data(man_plat=platform)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Товар (выдаются ключи)", callback_data="man_type_product")],
        [InlineKeyboardButton(text="👨‍💻 Услуга (смена региона, донат)", callback_data="man_type_service")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]
    ])
    await safe_edit_text(call, "🔍 <b>Выберите формат:</b>", kb)
    await state.set_state(AdminStates.manual_type)


@admin_router.callback_query(AdminStates.manual_type, F.data.startswith("man_type_"))
async def manual_type_select(call: types.CallbackQuery, state: FSMContext):
    item_type = call.data.replace("man_type_", "")
    await state.update_data(man_type=item_type)

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]])
    await safe_edit_text(call, "📝 Введите <b>название</b>\n(например: <i>Смена региона на Турцию</i>):", kb)
    await state.set_state(AdminStates.manual_name)


@admin_router.message(AdminStates.manual_name)
async def manual_name(message: types.Message, state: FSMContext):
    await state.update_data(man_name=message.text)
    kb_skip = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏩ Пропустить", callback_data="skip_desc")]])
    await message.answer("📝 Введите <b>описание</b> (или нажмите пропустить):", reply_markup=kb_skip, parse_mode="HTML")
    await state.set_state(AdminStates.manual_description)


@admin_router.message(AdminStates.manual_description)
async def manual_desc_msg(message: types.Message, state: FSMContext):
    await state.update_data(man_desc=message.text)
    await message.answer("💰 Введите <b>цену продажи</b> в рублях (только цифры):")
    await state.set_state(AdminStates.manual_price)


@admin_router.callback_query(AdminStates.manual_description, F.data == "skip_desc")
async def manual_desc_skip(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(man_desc=None)
    await call.message.edit_text("⏭ Описание пропущено.\n\n💰 Введите <b>цену продажи</b> в рублях:")
    await state.set_state(AdminStates.manual_price)


@admin_router.message(AdminStates.manual_price)
async def manual_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Только цифры!")
    await state.update_data(man_price=int(message.text))

    kb_skip = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏩ Пропустить фото", callback_data="skip_photo")]])
    await message.answer("🖼 Отправьте <b>фотографию</b> (или нажмите пропустить):", reply_markup=kb_skip,
                         parse_mode="HTML")
    await state.set_state(AdminStates.manual_photo)


# --- УМНОЕ ВЕТВЛЕНИЕ ПОСЛЕ ФОТО ---
async def process_after_photo(message: types.Message, state: FSMContext, is_edit=False):
    data = await state.get_data()
    if data.get('man_type') == 'service':
        text = "👨‍💻 Отправьте <b>инструкцию для покупателя</b> (она выдастся после покупки).\n<i>Например: Отправьте ваш логин и пароль администратору @username</i>"
        await state.set_state(AdminStates.manual_service_info)
    else:
        text = "🔑 Отправьте <b>ключи / данные от аккаунтов</b> (каждый с новой строки):"
        await state.set_state(AdminStates.manual_keys)

    if is_edit:
        await message.edit_text(f"⏭ Фото пропущено.\n\n{text}", parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


@admin_router.message(AdminStates.manual_photo, F.photo)
async def manual_photo_msg(message: types.Message, state: FSMContext):
    await state.update_data(man_photo=message.photo[-1].file_id)
    await process_after_photo(message, state)


@admin_router.callback_query(AdminStates.manual_photo, F.data == "skip_photo")
async def manual_photo_skip(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(man_photo=None)
    await process_after_photo(call.message, state, is_edit=True)


# --- СОХРАНЕНИЕ ТОВАРА (С КЛЮЧАМИ) ---
@admin_router.message(AdminStates.manual_keys)
async def manual_keys(message: types.Message, state: FSMContext):
    keys_list = [k.strip() for k in message.text.split('\n') if k.strip()]
    data = await state.get_data()

    db.add_custom_item(
        name=data['man_name'], price=data['man_price'], category=data['man_cat'], steam_category=data['man_plat'],
        keys_list=keys_list, photo_id=data.get('man_photo'), description=data.get('man_desc'), item_type='product'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 В панель", callback_data="admin_panel")]])
    await message.answer(f"✅ Товар добавлен! Загружено: {len(keys_list)} шт.", reply_markup=kb)
    await state.clear()


# --- СОХРАНЕНИЕ УСЛУГИ (БЕЗ КЛЮЧЕЙ) ---
@admin_router.message(AdminStates.manual_service_info)
async def manual_service_info(message: types.Message, state: FSMContext):
    data = await state.get_data()

    db.add_custom_item(
        name=data['man_name'], price=data['man_price'], category=data['man_cat'], steam_category=data['man_plat'],
        keys_list=None, photo_id=data.get('man_photo'), description=data.get('man_desc'),
        item_type='service', service_info=message.text
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 В панель", callback_data="admin_panel")]])
    await message.answer(f"✅ Услуга успешно создана!", reply_markup=kb)
    await state.clear()


# ==========================================
# БЛОК 4: СОЗДАНИЕ ПРОМОКОДОВ
# ==========================================
@admin_router.callback_query(F.data == "add_promo_start")
async def add_promo_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_new_promo_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_panel")]])
    await safe_edit_text(call,
                         "🎫 <b>Создание промокода</b>\nВведите секретное слово (например: <code>SHARKFREE</code>):", kb)


@admin_router.message(AdminStates.waiting_for_new_promo_name)
async def promo_name_step(message: types.Message, state: FSMContext):
    await state.update_data(new_promo_name=message.text.upper())  # Сохраняем в верхнем регистре
    await message.answer("💰 Введите <b>сумму скидки</b> в рублях (только число):")
    await state.set_state(AdminStates.waiting_for_new_promo_discount)


@admin_router.message(AdminStates.waiting_for_new_promo_discount)
async def promo_discount_step(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите число (сумму скидки) без лишних символов!")

    data = await state.get_data()
    promo_name = data['new_promo_name']
    discount = int(message.text)

    db.add_promo(promo_name, discount)

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 В панель", callback_data="admin_panel")]])
    await message.answer(f"✅ <b>Промокод создан!</b>\n\n🎟 Код: <code>{promo_name}</code>\n💸 Скидка: {discount} руб.",
                         reply_markup=kb, parse_mode="HTML")
    await state.clear()