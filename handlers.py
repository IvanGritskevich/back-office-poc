import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.asyncio_storage import StateMemoryStorage

import startGpt
import auth

# Инициализируем хранилище состояний
storage = StateMemoryStorage()

# Определяем состояния для FSM
class InvoiceStates(StatesGroup):
    confirm_data = State()    # Ожидание подтверждения Да/Нет
    choose_field = State()    # Ожидание выбора поля для редактирования
    edit_field = State()      # Ожидание ввода нового значения для поля

# Глобальный буфер для медиагрупп и временное хранилище результатов ИИ для сессий пользователей
MEDIA_BUFFER = {}
USER_RESULTS = {}  # {user_id: InvoiceData}
BUFFER_LOCK = asyncio.Lock()

# Селектор кнопок "Все верно / Изменить"
def get_confirmation_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Да, все верно", callback_data="invoice_confirm_yes"),
        InlineKeyboardButton("❌ Нет, изменить", callback_data="invoice_confirm_no")
    )
    return markup

# Селектор кнопок для выбора поля изменения
def get_fields_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Имя", callback_data="field_name"),
        InlineKeyboardButton("Адрес", callback_data="field_address"),
        InlineKeyboardButton("Город", callback_data="field_city"),
        InlineKeyboardButton("Страна", callback_data="field_country"),
        InlineKeyboardButton("Индекс", callback_data="field_postal"),
        InlineKeyboardButton("Пользователь", callback_data="field_username"),
        InlineKeyboardButton("Почта", callback_data="field_email"),
        InlineKeyboardButton("Счет (Сумма)", callback_data="field_amount"),
        InlineKeyboardButton("Валюта", callback_data="field_currency")
    )
    markup.row(InlineKeyboardButton("⬅️ Назад к проверке", callback_data="field_back"))
    return markup

def format_invoice_text(result) -> str:
    return (
        f"📋 **Проверьте корректность данных перед отправкой в БД:**\n\n"
        f"Имя: {result.name or 'Не указано'}\n"
        f"Адрес: {result.address.to_string() if result.address else 'Не указан'}\n"
        f"Город: {result.city or 'Не указан'}\n"
        f"Страна: {result.country or 'Не указана'}\n"
        f"Пользователь: {result.username or 'Не указан'}\n"
        f"Почта: {result.email or 'Не указана'}\n"
        f"Счет: {result.amount} \n"
        f"Валюта: {result.currency} \n"
        f"Почтовый индекс: {result.postal or 'Не указан'} \n"
        f"Налог (Новая Зеландия 15%): {result.has_nz_tax_15}"
    )

async def process_accumulated_media(group_id: str, chat_id: int, bot: AsyncTeleBot):
    await asyncio.sleep(1.2)
    async with BUFFER_LOCK:
        data = MEDIA_BUFFER.pop(group_id, None)
    if not data: return

    msg = await bot.send_message(chat_id, "⏳ Все файлы получены. Начинаю комплексный анализ данных...")
    try:
        combined_text = data["text"]
        files = data["files"]
        created_by = data.get("user_id", 0)
        
        result = await startGpt.extract_invoice_multimedia(text_prompt=combined_text, files_list=files)
        
        # Сохраняем результат в оперативную память сессии пользователя
        USER_RESULTS[created_by] = result
        
        # Переводим пользователя в состояние ожидания подтверждения данных
        await bot.set_state(created_by, InvoiceStates.confirm_data, chat_id)
        
        await bot.delete_message(chat_id, msg.message_id)
        await bot.send_message(
            chat_id=chat_id,
            text=format_invoice_text(result),
            reply_markup=get_confirmation_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка обработки ИИ: {e}")

async def add_to_buffer(message, bot: AsyncTeleBot, file_bytes: bytes = None, mime_type: str = None):
    group_id = message.media_group_id or f"single_{message.chat.id}"
    async with BUFFER_LOCK:
        if group_id not in MEDIA_BUFFER:
            MEDIA_BUFFER[group_id] = {"text": "", "files": [], "user_id": message.from_user.id, "task_started": False}
        if "user_id" not in MEDIA_BUFFER[group_id]:
            MEDIA_BUFFER[group_id]["user_id"] = message.from_user.id
            
        incoming_text = message.text or message.caption
        if incoming_text:
            if MEDIA_BUFFER[group_id]["text"]:
                MEDIA_BUFFER[group_id]["text"] += f"\n{incoming_text}"
            else:
                MEDIA_BUFFER[group_id]["text"] = incoming_text
        if file_bytes and mime_type:
            MEDIA_BUFFER[group_id]["files"].append((file_bytes, mime_type))
            
        if not MEDIA_BUFFER[group_id]["task_started"]:
            MEDIA_BUFFER[group_id]["task_started"] = True
            asyncio.create_task(process_accumulated_media(group_id, message.chat.id, bot))


# --- РЕГИСТРАЦИЯ ВСЕХ ХЕНДЛЕРОВ ---

def register_all_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=['start'])
    async def send_welcome(message):
        if not await auth.gateway_middleware(message, bot): return
        await bot.send_message(chat_id=message.chat.id, text="👋 Рад видеть вас снова! Отправляйте ваши инвойсы или медиагруппы.")

    # Коллбэк для обработки подтверждения "Да / Нет"
    @bot.callback_query_handler(func=lambda call: call.data.startswith("invoice_confirm_"))
    async def handle_confirmation(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        
        if user_id not in USER_RESULTS:
            await bot.send_message(chat_id, "⚠️ Данные сессии устарели. Загрузите файлы заново.")
            return

        if call.data == "invoice_confirm_yes":
            # Выгружаем в БД
            result = USER_RESULTS.pop(user_id)
            await bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="⏳ Сохраняю данные.")
            try:
                await startGpt.save_to_db(result, created_by=user_id)
                await bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🚀 Данные успешно сохранены!")
                await bot.delete_state(user_id, chat_id)
            except Exception as e:
                await bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"❌ Ошибка записи в БД: {e}")
        
        elif call.data == "invoice_confirm_no":
            # Переводим в режим выбора поля для изменения
            await bot.set_state(user_id, InvoiceStates.choose_field, chat_id)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="🔄 Выберите поле, которое необходимо отредактировать:",
                reply_markup=get_fields_keyboard()
            )

    # Коллбэк для выбора конкретного поля редактирования
    @bot.callback_query_handler(func=lambda call: True, state=InvoiceStates.choose_field)
    async def handle_field_selection(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        if call.data == "field_back":
            # Возвращаемся к главному экрану проверки
            await bot.set_state(user_id, InvoiceStates.confirm_data, chat_id)
            result = USER_RESULTS[user_id]
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=format_invoice_text(result),
                reply_markup=get_confirmation_keyboard(),
                parse_mode="Markdown"
            )
            return

        # Запоминаем выбранное поле в контекст FSM сессии
        field_name = call.data.replace("field_", "")
        async with bot.retrieve_data(user_id, chat_id) as data:
            data['target_field'] = field_name

        await bot.set_state(user_id, InvoiceStates.edit_field, chat_id)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"✍️ Введите новое значение для поля **{field_name.upper()}**:",
            parse_mode="Markdown"
        )

    # Хендлер текстового ввода нового значения для поля (работает только в стейте edit_field)
    @bot.message_handler(state=InvoiceStates.edit_field, content_types=['text'])
    async def handle_field_replacement(message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        new_value = message.text.strip()

        async with bot.retrieve_data(user_id, chat_id) as data:
            target_field = data.get('target_field')

        result = USER_RESULTS.get(user_id)
        if result and target_field:
            # Динамически обновляем поле внутри Pydantic-модели InvoiceData
            if target_field == "address":
                if not result.address:
                    from gpt import AddressDetail
                    result.address = AddressDetail()
                result.address.street = new_value
            elif target_field == "amount":
                try:
                    result.amount = float(new_value)
                except ValueError:
                    await bot.send_message(chat_id, "⚠️ Ошибка: Сумма должна быть числом. Значение не изменено.")
            elif target_field == "has_nz_tax_15":
                result.has_nz_tax_15 = new_value
            else:
                if hasattr(result, target_field):
                    setattr(result, target_field, new_value)
                    
            # Дополнительная валидация налога при ручном переименовании страны
            if target_field == "country":
                result.has_nz_tax_15 = "Да" if new_value.lower() == "new zealand" else "Нет"

        # Возвращаем пользователя на этап подтверждения с обновленным текстом
        await bot.set_state(user_id, InvoiceStates.confirm_data, chat_id)
        await bot.send_message(
            chat_id=chat_id,
            text=format_invoice_text(result),
            reply_markup=get_confirmation_keyboard(),
            parse_mode="Markdown"
        )

    # Базовые медиа-хендлеры (работают только если пользователь НЕ находится в процессе редактирования)
    @bot.message_handler(content_types=['text'])
    async def handle_text(message):
        if not await auth.gateway_middleware(message, bot): return
        await add_to_buffer(message, bot)

    @bot.message_handler(content_types=['photo'])
    async def handle_photo(message):
        if not await auth.gateway_middleware(message, bot): return
        file_info = await bot.get_file(message.photo[-1].file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        await add_to_buffer(message, bot, file_bytes, "image/jpeg")

    @bot.message_handler(content_types=['document'])
    async def handle_document(message):
        if not await auth.gateway_middleware(message, bot): return
        mime_type = message.document.mime_type
        allowed_mimes = [
            "application/pdf", "image/png", "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ]
        if mime_type not in allowed_mimes:
            await bot.send_message(chat_id=message.chat.id, text="⚠️ Формат файла не поддерживается.")
            return
            
        file_info = await bot.get_file(message.document.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        await add_to_buffer(message, bot, file_bytes, mime_type)