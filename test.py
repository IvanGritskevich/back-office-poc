import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from pathlib import Path
import startGpt

async def has_access(message) -> bool:
    """
    Проверяет доступ пользователя. 
    Возвращает True, если доступ разрешен, и False, если заблокирован.
    """
    try:
        # Асинхронно запрашиваем у startGpt, есть ли этот человек в БД
        allowed = await startGpt.check_user_access(message.from_user.id)
        if not allowed:
            await bot.reply_to(message, "⛔️ Ошибка доступа. Вашего ID нет в базе данных.")
            return False  # Доступ запрещен
        return True  # Доступ разрешен
        
    except Exception as e:
        print(f"Ошибка при проверке доступа: {e}")
        await bot.reply_to(message, "❌ Произошла ошибка при проверке прав.")
        return False  # В случае ошибки базы данных тоже блокируем доступ от греха подальше

dotenv_path = Path('key.env')
load_dotenv(dotenv_path=dotenv_path)

bot = AsyncTeleBot(os.getenv("TELEGRAM_BOT_TOKEN"))

# Глобальный буфер для хранения медиафайлов от пользователей
# Структура: { "ID_группы": { "text": "...", "files": [(bytes, mime), ...] } }
MEDIA_BUFFER = {}
BUFFER_LOCK = asyncio.Lock()

# Вспомогательная функция для генерации красивого отчета пользователю
def format_invoice_text(result) -> str:
    return (
        f"✅ Данные успешно занесены в БД!\n\n"
        f"Имя: {result.name or 'Не указано'}\n"
        f"Адрес: {result.address.to_string() if result.address else 'Не указан'}\n"
        f"Город: {result.city or 'Не указан'}\n"
        f"Страна: {result.country or 'Не указана'}\n"
        f"Пользователь: {result.username or 'Не указан'}\n"
        f"Почта: {result.email or 'Не указана'}\n"
        f"Счет: {result.amount} \n"
        f"Валюта: {result.currency} \n"
        f"Почтовый индекс: {result.postal} \n"
        f"Налог если в страна Новая Зеландия 15%: {result.has_nz_tax_15}"
    )

async def process_accumulated_media(group_id: str, chat_id: int, reply_to_msg_id: int):
    """Функция, которая вызывается ПОСЛЕ того, как все файлы из группы собраны"""
    # Делаем микропаузу (0.8–1.2 сек), чтобы Telegram успел передать все сообщения пакета
    await asyncio.sleep(1.0)
    
    async with BUFFER_LOCK:
        data = MEDIA_BUFFER.pop(group_id, None)
        
    if not data:
        return

    msg = await bot.send_message(chat_id, "⏳ Все файлы получены. Начинаю комплексный анализ данных...")
    
    try:
        combined_text = data["text"]
        files = data["files"]
        
        # Передаем собранные данные в обновленную функцию startGpt
        result = await startGpt.extract_invoice_multimedia(text_prompt=combined_text, files_list=files)
        
        # Сохраняем одну общую запись в БД
        await startGpt.save_to_db(result)
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg.message_id,
            text=format_invoice_text(result)
        )
    except Exception as e:
        await bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"❌ Ошибка обработки: {e}")


async def add_to_buffer(message, file_bytes: bytes = None, mime_type: str = None):
    """Вспомогательная функция для упаковки данных в буфер"""
    # Если это альбом, ключ — media_group_id. Если одиночные файлы подряд — группируем по chat_id
    group_id = message.media_group_id or f"single_{message.chat.id}"
    
    async with BUFFER_LOCK:
        if group_id not in MEDIA_BUFFER:
            MEDIA_BUFFER[group_id] = {"text": "", "files": [], "task_started": False}
            
        # Собираем текст (подписи к фото или обычный текст)
        incoming_text = message.text or message.caption
        if incoming_text:
            if MEDIA_BUFFER[group_id]["text"]:
                MEDIA_BUFFER[group_id]["text"] += f"\n{incoming_text}"
            else:
                MEDIA_BUFFER[group_id]["text"] = incoming_text
                
        # Собираем файлы (байты + тип)
        if file_bytes and mime_type:
            MEDIA_BUFFER[group_id]["files"].append((file_bytes, mime_type))
            
        # Запускаем таймер ожидания только один раз для всей группы
        if not MEDIA_BUFFER[group_id]["task_started"]:
            MEDIA_BUFFER[group_id]["task_started"] = True
            asyncio.create_task(process_accumulated_media(group_id, message.chat.id, message.message_id))


@bot.message_handler(commands=['start'])
async def send_welcome(message):
    if not await has_access(message):
        return
    await bot.reply_to(message, "Привет! Ты можешь отправить мне текст, несколько фото или документов ОДНИМ сообщением, и я соберу их вместе.")


# 1. Хендлер для текста
@bot.message_handler(content_types=['text'])
async def handle_text(message):
    if not await has_access(message):
        return
    await add_to_buffer(message)


# 2. Хендлер для фото
@bot.message_handler(content_types=['photo'])
async def handle_photo(message):
    if not await has_access(message):
        return
    file_info = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    await add_to_buffer(message, file_bytes, "image/jpeg")


# 3. Хендлер для документов (PDF, Excel, Word)
@bot.message_handler(content_types=['document'])
async def handle_document(message):
    if not await has_access(message):
        return
    mime_type = message.document.mime_type
    allowed_mimes = [
        "application/pdf", "image/png", "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    if mime_type not in allowed_mimes:
        await bot.reply_to(message, "⚠️ Формат файла не поддерживается.")
        return
        
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    await add_to_buffer(message, file_bytes, mime_type)

if __name__ == '__main__':
    print("Бот со сквозной нормализацией запущен...")
    asyncio.run(bot.infinity_polling())