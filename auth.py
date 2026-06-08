import os
import json
import asyncpg
from dotenv import load_dotenv
from pathlib import Path

dotenv_path = Path('key.env')
load_dotenv(dotenv_path=dotenv_path)

# Безопасно загружаем коды из env
try:
    INVITE_CODES = json.loads(os.getenv("INVITE_CODES", "{}"))
except Exception:
    print("❌ Ошибка: Неверный формат INVITE_CODES в файле key.env!")
    INVITE_CODES = {}


async def check_user_access(user_id: int) -> bool:
    """Проверяет, занесен ли уже пользователь в белый список БД"""
    conn = await asyncpg.connect(
        user=os.getenv("DB_USER"), 
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), 
        host=os.getenv("DB_HOST")
    )
    try:
        # Убедимся, что таблица пользователей существует (структура из прошлого шага)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        row = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
        return row is not None
    finally:
        await conn.close()


async def register_new_user(user_id: int, username: str) -> bool:
    """Добавляет нового авторизованного пользователя в БД"""
    conn = await asyncpg.connect(
        user=os.getenv("DB_USER"), 
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), 
        host=os.getenv("DB_HOST")
    )
    try:
        await conn.execute("""
            INSERT INTO users (user_id, username) 
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING;
        """, user_id, username)
        return True
    except Exception as e:
        print(f"Ошибка при регистрации пользователя {user_id}: {e}")
        return False
    finally:
        await conn.close()


def verify_invite_code(code: str) -> bool:
    """Проверяет, существует ли переданный код в key.env"""
    return code in INVITE_CODES


async def gateway_middleware(message, bot) -> bool:
    """
    Главный фильтр-шлюз для всех хендлеров.
    Возвращает True только если пользователю РАЗРЕШЕНО обрабатывать документы текущим сообщением.
    """
    user_id = message.from_user.id
    text = (message.text or "").strip()
    
    # 1. Если пользователь уже есть в БД — пропускаем его файлы/текст дальше
    if await check_user_access(user_id):
        return True
        
    # 2. Если его нет в БД, проверяем, прислал ли он инвайт-код
    if verify_invite_code(text):
        success = await register_new_user(user_id, message.from_user.username)
        if success:
            await bot.send_message(
                chat_id=message.chat.id,
                text="🎉 Авторизация успешна! Ваш Telegram ID внесен в белый список.\n"
                     "Теперь вы можете отправлять мне инвойсы, таблицы и фото."
            )
        # КРИТИЧЕСКИЙ МОМЕНТ: Возвращаем False! 
        # Пользователь теперь в базе, но само текстовое сообщение с кодом НЕ должно идти в ИИ.
        return False
            
    # 3. Если кода нет или он неверный
    await bot.send_message(
        chat_id=message.chat.id,
        text="⛔️ Доступ заблокирован.\n\n"
             "Вашего аккаунта нет в базе. Если у вас есть инвайт-код, "
             "отправьте его мне текстовым сообщением."
    )
    return False
