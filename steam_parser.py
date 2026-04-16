import requests
import time
import html
import re

# Кэш для курса
CURRENCY_CACHE = {
    "rate": 0.20,
    "last_update": 0
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
})

def search_steam_games_by_name(query):
    """Ищет игры в Steam по названию и возвращает список совпадений"""
    url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=russian&cc=ru"
    try:
        res = session.get(url, timeout=5).json()
        if res.get('total', 0) > 0:
            # Возвращаем топ-5 совпадений
            return [{"id": str(item['id']), "name": item['name']} for item in res['items'][:5]]
    except Exception as e:
        print(f"Ошибка поиска Steam: {e}")
    return []

def get_actual_rate():
    if time.time() - CURRENCY_CACHE["last_update"] < 3600:
        return CURRENCY_CACHE["rate"]
    try:
        response = session.get("https://open.er-api.com/v6/latest/KZT", timeout=5)
        data = response.json()
        if data.get("result") == "success":
            CURRENCY_CACHE["rate"] = data["rates"]["RUB"]
            CURRENCY_CACHE["last_update"] = time.time()
    except Exception:
        pass
    return CURRENCY_CACHE["rate"]


def get_steam_game_info(app_id):
    regions = ['ru', 'kz', 'us']

    rate_kzt = get_actual_rate()
    rate_usd = 92  # Можно также привязать к API

    for cc in regions:
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=russian&cc={cc}"
        try:
            res = session.get(url, cookies={'birthtime': '946684801', 'lastagecheckage': '1-0-2000'}, timeout=10)
            data = res.json()

            if data and data.get(str(app_id)) and data[str(app_id)]['success']:
                game_data = data[str(app_id)]['data']
                price_info = game_data.get("price_overview")

                if price_info:
                    discount = price_info.get("discount_percent", 0)
                    final_raw = price_info.get("final") / 100
                    initial_raw = price_info.get("initial") / 100

                    if cc == 'ru':
                        price_rub = final_raw
                        price_old_rub = initial_raw
                        price_kzt = round(price_rub / rate_kzt)
                        price_usd = round(price_rub / rate_usd, 2)
                    elif cc == 'kz':
                        price_kzt = final_raw
                        price_old_kzt = initial_raw
                        price_rub = round(price_kzt * rate_kzt)
                        price_old_rub = round(price_old_kzt * rate_kzt)
                        price_usd = round(price_rub / rate_usd, 2)
                    else:
                        price_usd = final_raw
                        price_rub = round(price_usd * rate_usd)
                        price_old_rub = round((initial_raw) * rate_usd)
                        price_kzt = round(price_rub / rate_kzt)

                    if discount > 0:
                        price_text = (
                            f"💰 <b>Цена без скидки:</b> {price_old_rub} руб.\n"
                            f"🇷🇺 <b>Актуальная цена:</b> {price_rub} руб.\n"
                            f"🇰🇿 <b>В тенге:</b> {price_kzt} ₸\n"
                            f"🇺🇸 <b>В долларах:</b> ${price_usd}\n"
                            f"🎁 <b>Скидка в Steam: -{discount}%</b>"
                        )
                    else:
                        price_text = (
                            f"🇷🇺 <b>Актуальная цена:</b> {price_rub} руб.\n"
                            f"🇰🇿 <b>В тенге:</b> {price_kzt} ₸\n"
                            f"🇺🇸 <b>В долларах:</b> ${price_usd}"
                        )
                else:
                    price_text = "💎 <b>Бесплатно или нет в продаже</b>"

                # --- ОЧИСТКА ТЕКСТА ОТ МУСОРА STEAM ---
                # 1. Берем описание
                raw_desc = game_data.get("short_description", "Без описания")
                # 2. Переводим &quot; в обычные кавычки "
                desc_unescaped = html.unescape(raw_desc)
                # 3. Регулярным выражением вырезаем все теги (всё, что внутри < >) и заменяем на пробел
                clean_desc = re.sub(r'<[^>]+>', ' ', desc_unescaped)

                # То же самое делаем для имени игры на всякий случай
                clean_name = html.unescape(game_data.get("name", ""))

                return {
                    "name": html.escape(clean_name),
                    "description": html.escape(clean_desc.strip()),  # Экранируем уже чистый текст
                    "price": price_text,
                    "image": game_data.get("header_image"),
                    "screenshots": [s['path_full'] for s in game_data.get("screenshots", [])[:3]],
                    "developers": html.escape(", ".join(game_data.get("developers", []) or ["Unknown"])),
                    "genres": html.escape(
                        ", ".join([g['description'] for g in game_data.get("genres", [])] or ["Games"]))
                }
        except Exception as e:
            print(f"Ошибка региона {cc}: {e}")
            continue

    return None