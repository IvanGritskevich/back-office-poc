import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from pathlib import Path
import handlers
from telebot import asyncio_filters

dotenv_path = Path('key.env')
load_dotenv(dotenv_path=dotenv_path)

# Инициализируем асинхронного бота с поддержкой оперативной памяти состояний (FSM)
bot = AsyncTeleBot(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    state_storage=handlers.storage
)

# Подключаем к боту все вынесенные хендлеры из модуля handlers
handlers.register_all_handlers(bot)

# Регистрируем встроенный фильтр состояний (обязательно для telebot FSM)
bot.add_custom_filter(asyncio_filters.StateFilter(bot))

if __name__ == '__main__':
    print("Бот со сквозной нормализацией, FSM-верификацией и внешними хендлерами запущен...")
    asyncio.run(bot.infinity_polling())