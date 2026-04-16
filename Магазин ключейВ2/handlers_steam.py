from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from states import SearchStates
from base import SQL
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import html

router = Router()
db = SQL('db.db')

@router.callback_query(F.data == "search_dev_start")
async def start_dev_search(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_developer)
    await call.message.answer("⌨️ Напишите название разработчика (например: <b>FromSoftware</b>):", parse_mode="HTML")
    await call.answer()


@router.message(SearchStates.waiting_for_developer)
async def process_dev_search(message: types.Message, state: FSMContext):
    query = message.text

    # Тот же трюк: ищем только по разработчику и берем только базовые игры
    from base import SQL  # на всякий случай импортируем, если у тебя там свой инстанс БД
    db = SQL('db.db')

    db.cursor.execute("""
        SELECT steam_id, name FROM items 
        WHERE developer LIKE ? AND steam_id LIKE 'key_%'
    """, (f"%{query}%",))
    results = db.cursor.fetchall()

    if not results:
        await message.answer(f"❌ Игр от разработчика «{query}» не найдено.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for steam_id, name in results:
        clean_name = name.replace("Steam [Ключ]: ", "").strip()
        app_id = steam_id.replace("key_", "")

        kb.inline_keyboard.append([InlineKeyboardButton(text=clean_name, callback_data=f"steam_game_{app_id}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")])

    await message.answer(f"✅ <b>Найдено игр от {query}:</b>", reply_markup=kb, parse_mode="HTML")
    await state.clear()