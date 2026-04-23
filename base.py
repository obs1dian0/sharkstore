import sqlite3
import os

def get_instruction():
    file_path = "support_instruction.txt"

    # Жесткий промпт с ограничениями
    strict_prompt = (
        "Ты — официальный ИИ-помощник магазина цифровых товаров SharkStore. "
        "Твоя задача: помогать клиентам с покупкой игр, ключей, аккаунтов Steam/PS/Xbox, "
        "объяснять правила магазина, рассказывать про цены и ассортимент.\n\n"
        "СТРОГОЕ ПРАВИЛО: Ты отвечаешь ТОЛЬКО на вопросы, связанные с магазином, играми и покупками. "
        "Если пользователь задает вопрос на отвлеченную тему (погода, программирование, рецепты, политика, "
        "общие знания) или просит выполнить стороннюю задачу (написать текст, решить пример), "
        "ты ДОЛЖЕН вежливо отказаться, сказать, что ты всего лишь консультант магазина SharkStore, "
        "и предложить помощь по каталогу товаров. Ни при каких обстоятельствах не нарушай это правило."
    )

    # Если файл не существует или мы хотим его принудительно обновить, перезаписываем
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(strict_prompt)

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

class SQL:
    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.cursor = self.connection.cursor()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                category TEXT,          
                steam_category TEXT,   
                developer TEXT,        
                steam_id TEXT,         
                stock INTEGER DEFAULT 999
            )
        """)
        self.connection.commit()
        self.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS promos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT UNIQUE,
                        discount INTEGER
                    )
                """)
        self.connection.commit()

        # --- АВТОМАТИЧЕСКОЕ ОБНОВЛЕНИЕ БАЗЫ ---
        import sqlite3
        try:
            self.cursor.execute("ALTER TABLE items ADD COLUMN item_type TEXT DEFAULT 'product'")
            self.cursor.execute("ALTER TABLE items ADD COLUMN service_info TEXT")
            self.connection.commit()
            print("База данных обновлена: добавлена поддержка услуг")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE items ADD COLUMN photo TEXT")
            self.connection.commit()
            print("База данных обновлена: добавлена колонка photo")
        except sqlite3.OperationalError:
            pass

        try:
            self.cursor.execute("ALTER TABLE items ADD COLUMN description TEXT")
            self.connection.commit()
            print("База данных обновлена: добавлена колонка description")
        except sqlite3.OperationalError:
            pass

    def add_user(self, id):
        query = "INSERT INTO users (id) VALUES(?)"
        with self.connection:
            return self.cursor.execute(query, (id,))

    def user_exist(self, id):
        query = "SELECT * FROM users WHERE id = ?"
        with self.connection:
            result = self.cursor.execute(query, (id,)).fetchall()
            return bool(len(result))

    def get_field(self, table, id, field):
        query = f"SELECT {field} FROM {table} WHERE id = ?"
        with self.connection:
            result = self.cursor.execute(query, (id,)).fetchone()
            if result:
                return result[0]

    def add_order(self, user_id, item_id):
        query = "INSERT INTO orders (user_id, item_id) VALUES(?, ?)"
        with self.connection:
            self.cursor.execute(query, (user_id, item_id))

    def get_stock(self, item_id):
        query = "SELECT COUNT(id) FROM item_keys WHERE item_id = ?"
        with self.connection:
            result = self.cursor.execute(query, (item_id,)).fetchone()
            return result[0]

    def get_games_by_category(self, category, limit, offset):
        query = "SELECT name, steam_id FROM items WHERE category = ? LIMIT ? OFFSET ?"
        self.cursor.execute(query, (category, limit, offset))
        return self.cursor.fetchall()

    def count_games_in_category(self, category):
        query = "SELECT COUNT(*) FROM items WHERE category = ?"
        self.cursor.execute(query, (category,))
        return self.cursor.fetchone()[0]

    def search_games_in_category(self, category, query):
        sql = "SELECT name, steam_id FROM items WHERE category = ? AND steam_id IS NOT NULL AND name LIKE ?"
        self.cursor.execute(sql, (category, f"%{query}%"))
        return self.cursor.fetchall()

    def get_accounts_by_platform(self, platform, limit, offset):
        sql = "SELECT name, id FROM items WHERE category = 'accounts' AND name LIKE ? LIMIT ? OFFSET ?"
        self.cursor.execute(sql, (f"{platform}%", limit, offset))
        return self.cursor.fetchall()

    def count_accounts_by_platform(self, platform):
        sql = "SELECT COUNT(*) FROM items WHERE category = 'accounts' AND name LIKE ?"
        self.cursor.execute(sql, (f"{platform}%",))
        return self.cursor.fetchone()[0]

    def get_double_filter_items(self, p1, p2):
        sql = "SELECT name, id FROM items WHERE category = 'accounts' AND name LIKE ? AND name LIKE ?"
        self.cursor.execute(sql, (f"%{p1}%", f"%{p2}%"))
        return self.cursor.fetchall()

    def get_or_create_steam_item(self, steam_id, name, price, buy_type, developer='Unknown'):
        """Создает товар Steam на лету, если его еще нет в базе"""
        db_steam_id = f"{buy_type}_{steam_id}"
        self.cursor.execute("SELECT id FROM items WHERE steam_id = ?", (db_steam_id,))
        item = self.cursor.fetchone()

        if not item:
            # Определяем тип "на лету"
            if buy_type == 'gift':
                item_type = 'service'
                service_info = '🎁 Для получения гифта, отправьте ссылку на ваш профиль Steam администратору.'
            elif buy_type == 'acc':
                item_type = 'service'
                service_info = '👤 Ожидайте, администратор отправит вам данные от аккаунта.'
            else:  # key
                item_type = 'product'
                service_info = None

            self.cursor.execute("""
                INSERT INTO items (name, price, category, stock, steam_id, developer, item_type, service_info) 
                VALUES (?, ?, 'games_steam', 9999, ?, ?, ?, ?)
            """, (f"Steam [{buy_type}]: {name}", price, db_steam_id, developer, item_type, service_info))
            self.connection.commit()
            return self.cursor.lastrowid
        else:
            self.cursor.execute("UPDATE items SET developer = ? WHERE id = ?", (developer, item[0]))
            self.connection.commit()
            return item[0]

    def process_purchase(self, user_id, item_id):
        # 1. Получаем инфу о товаре
        self.cursor.execute("SELECT name, item_type, service_info FROM items WHERE id = ?", (item_id,))
        item_data = self.cursor.fetchone()
        if not item_data: return "❌ Ошибка: товар не найден."

        item_name, item_type, service_info = item_data

        # --- ЛОГИКА ВЫДАЧИ УСЛУГИ ---
        if item_type == 'service':
            # Привязываем инструкцию вместо ключа, чтобы юзер видел её в "Моих покупках"
            self.cursor.execute(
                "UPDATE orders SET status = 1, key = ? WHERE user_id = ? AND item_id = ? AND status = 0",
                (service_info, user_id, item_id))
            self.connection.commit()
            # Слово "администратор" вызовет отправку уведомления тебе
            return f"✅ Вы успешно заказали услугу: <b>{item_name}</b>\n\n📌 <b>Инструкция:</b>\n{service_info}\n\nОжидайте, скоро с вами свяжется администратор."

        # --- ЛОГИКА ВЫДАЧИ ТОВАРА (КЛЮЧА) ---
        else:
            self.cursor.execute("SELECT id, key_value FROM item_keys WHERE item_id = ? AND status = 0 LIMIT 1",
                                (item_id,))
            key_data = self.cursor.fetchone()

            if not key_data:
                return f"❌ Ошибка: Ключи для {item_name} закончились."

            key_id, key_value = key_data

            self.cursor.execute("UPDATE item_keys SET status = 1 WHERE id = ?", (key_id,))
            self.cursor.execute("UPDATE items SET stock = stock - 1 WHERE id = ?", (item_id,))
            self.cursor.execute(
                "UPDATE orders SET status = 1, key = ? WHERE user_id = ? AND item_id = ? AND status = 0",
                (key_value, user_id, item_id))
            self.connection.commit()

            return f"✅ Вы успешно купили: <b>{item_name}</b>\n🔑 Ваш товар:\n<code>{key_value}</code>"

    def get_steam_games_by_genre(self, genre_code):
        query = "SELECT steam_id, name, price FROM items WHERE steam_category = ? AND stock > 0"
        self.cursor.execute(query, (genre_code,))
        return self.cursor.fetchall()

    def search_by_developer(self, dev_query):
        query = "SELECT steam_id, name, price FROM items WHERE developer LIKE ? OR name LIKE ? AND stock > 0"
        self.cursor.execute(query, (f"%{dev_query}%", f"%{dev_query}%"))
        return self.cursor.fetchall()

    def add_game_with_keys(self, name, price, steam_category, developer, steam_id, keys_list):
        """Создает игру и сразу привязывает к ней массив ключей"""
        # 1. Добавляем игру в каталог (buy_type ставим 'key', чтобы логика карточек работала)
        db_steam_id = f"key_{steam_id}"

        self.cursor.execute("""
            INSERT INTO items (name, price, category, steam_category, developer, steam_id, stock) 
            VALUES (?, ?, 'games_steam', ?, ?, ?, ?)
        """, (f"Steam [Ключ]: {name}", price, steam_category, developer, db_steam_id, len(keys_list)))

        item_id = self.cursor.lastrowid

        # 2. Загружаем ключи в базу
        for key in keys_list:
            self.cursor.execute("INSERT INTO item_keys (item_id, key_value, status) VALUES (?, ?, 0)",
                                (item_id, key.strip()))

        self.connection.commit()
        return len(keys_list)  # Возвращаем количество добавленных ключей

    def add_game_complex(self, name, prices, steam_category, developer, steam_id, keys_list):
        """Создает сразу 3 версии игры с учетом типа (Товар или Услуга)"""
        added_keys = 0
        type_names = {"key": "Ключ", "gift": "Гифт", "acc": "Аккаунт"}

        for buy_type, price in prices.items():
            db_steam_id = f"{buy_type}_{steam_id}"
            full_name = f"Steam [{type_names[buy_type]}]: {name}"

            # Разделяем логику: Ключ - это товар. Гифт и Аккаунт - это услуги.
            if buy_type == 'key':
                stock = len(keys_list)
                item_type = 'product'
                service_info = None
            elif buy_type == 'gift':
                stock = 9999
                item_type = 'service'
                service_info = '🎁 Для получения гифта (подарка), пожалуйста, отправьте ссылку на ваш профиль Steam (Friend Code) администратору.'
            else:  # acc
                stock = 9999
                item_type = 'service'
                service_info = '👤 Ожидайте, администратор скоро свяжется с вами и отправит данные (логин и пароль) от нового аккаунта Steam.'

            self.cursor.execute("""
                INSERT INTO items (name, price, category, steam_category, developer, steam_id, stock, item_type, service_info) 
                VALUES (?, ?, 'games_steam', ?, ?, ?, ?, ?, ?)
            """, (full_name, price, steam_category, developer, db_steam_id, stock, item_type, service_info))

            item_id = self.cursor.lastrowid

            if buy_type == 'key':
                for key in keys_list:
                    self.cursor.execute("INSERT INTO item_keys (item_id, key_value, status) VALUES (?, ?, 0)",
                                        (item_id, key.strip()))
                added_keys = len(keys_list)

        self.connection.commit()
        return added_keys

    def search_local_items(self, query):
        """Ищет товары в локальной БД для редактирования"""
        self.cursor.execute("SELECT id, name, price, stock FROM items WHERE name LIKE ? LIMIT 8", (f"%{query}%",))
        return self.cursor.fetchall()

    def update_item_price(self, item_id, new_price):
        """Обновляет цену существующего товара"""
        self.cursor.execute("UPDATE items SET price = ? WHERE id = ?", (new_price, item_id))
        self.connection.commit()

    def add_keys_to_existing_item(self, item_id, keys_list):
        """Докидывает ключи в существующий товар"""
        for key in keys_list:
            self.cursor.execute("INSERT INTO item_keys (item_id, key_value, status) VALUES (?, ?, 0)",
                                (item_id, key.strip()))
        self.cursor.execute("UPDATE items SET stock = stock + ? WHERE id = ?", (len(keys_list), item_id))
        self.connection.commit()

    def get_custom_items(self, category, platform):
        """Получает товары для динамических меню (подписки, сервисы)"""
        # Ищем по категории и платформе, и только те, что есть в наличии (stock > 0)
        self.cursor.execute("""
            SELECT id, name, price FROM items 
            WHERE category = ? AND steam_category = ? AND stock > 0
        """, (category, platform))
        return self.cursor.fetchall()

    def delete_item(self, item_id):
        """Удаляет товар и все его невыданные ключи"""
        self.cursor.execute("DELETE FROM item_keys WHERE item_id = ?", (item_id,))
        self.cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.connection.commit()

    def update_item_photo(self, item_id, photo_id):
        """Обновляет фотографию существующего товара"""
        self.cursor.execute("UPDATE items SET photo = ? WHERE id = ?", (photo_id, item_id))
        self.connection.commit()

    def add_custom_item(self, name, price, category, steam_category, keys_list=None, photo_id=None,
                    description=None, item_type='product', service_info=None):
        """Универсальное добавление: Товары (с ключами) и Услуги (без ключей)"""
        # Если это услуга, ставим бесконечный запас (9999). Если товар - считаем ключи.
        stock = 9999 if item_type == 'service' else len(keys_list)

        self.cursor.execute("""
            INSERT INTO items (name, price, category, steam_category, stock, photo, description, item_type, service_info) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, price, category, steam_category, stock, photo_id, description, item_type, service_info))

        item_id = self.cursor.lastrowid

        # Загружаем ключи только если они есть
        if keys_list:
            for key in keys_list:
                self.cursor.execute("INSERT INTO item_keys (item_id, key_value, status) VALUES (?, ?, 0)",
                                        (item_id, key.strip()))
        self.connection.commit()
        return len(keys_list)

    def update_item_description(self, item_id, description):
        """Обновляет описание существующего товара"""
        self.cursor.execute("UPDATE items SET description = ? WHERE id = ?", (description, item_id))
        self.connection.commit()

    def get_all_local_items(self):
        """Получает список всех товаров для меню редактирования (от новых к старым)"""
        self.cursor.execute("SELECT id, name, price, stock FROM items ORDER BY id DESC")
        return self.cursor.fetchall()

    def add_promo(self, code, discount):
        """Добавляет новый промокод в базу данных"""
        self.cursor.execute("INSERT INTO promos (code, discount) VALUES (?, ?)", (code, discount))
        self.connection.commit()

    def check_promo(self, code):
        """Проверяет промокод и возвращает скидку (или None)"""
        # Переводим код в верхний регистр на всякий случай перед поиском
        clean_code = code.strip().upper()
        self.cursor.execute("SELECT discount FROM promos WHERE code = ?", (clean_code,))
        result = self.cursor.fetchone()

        if result:
            return result[0]  # Возвращаем сумму скидки (например, 100)
        return None

    def close(self):
        self.connection.close()