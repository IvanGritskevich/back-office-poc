import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional
import asyncpg
from gpt import InvoiceData
import io
import docx
import openpyxl
from groq import AsyncGroq  # Импортируем асинхронный клиент Groq

async def check_user_access(user_id: int) -> bool:
    """Проверяет наличие user_id в таблице разрешенных пользователей"""
    conn = await asyncpg.connect(
        user=os.getenv("DB_USER"), 
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), 
        host=os.getenv("DB_HOST")
    )
    try:
        # Создаем таблицу белого списка, если её ещё нет
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Ищем пользователя в базе данных
        row = await conn.fetchrow("SELECT 1 FROM allowed_users WHERE user_id = $1", user_id)
        return row is not None
    finally:
        await conn.close()

# Загружаем переменные окружения
dotenv_path = Path('key.env')
load_dotenv(dotenv_path=dotenv_path)

# Инициализируем клиентов ИИ
client = genai.Client(api_key=os.getenv("API_KEY"))
groq_client = AsyncGroq(api_key=os.getenv("API_KEY_GROG"))


def parse_docx(file_bytes: bytes) -> str:
    """Извлекает весь текст из файла Word (.docx)"""
    doc = docx.Document(io.BytesIO(file_bytes))
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text for cell in row.cells]
            full_text.append(" | ".join(row_text))
    return "\n".join(full_text)


def parse_xlsx(file_bytes: bytes) -> str:
    """Извлекает все данные из таблиц Excel (.xlsx)"""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    full_text = []
    for sheet in wb.worksheets:
        full_text.append(f"--- Лист: {sheet.title} ---")
        for row in sheet.iter_rows(values_only=True):
            if any(row):
                row_text = [str(cell) if cell is not None else "" for cell in row]
                full_text.append(" | ".join(row_text))
    return "\n".join(full_text)


async def save_to_db(result: InvoiceData):
    conn = await asyncpg.connect(
        user=os.getenv("DB_USER"), 
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), 
        host=os.getenv("DB_HOST")
    )
    try:
        # Создаем таблицу, если ее нет
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                name TEXT,
                address TEXT,
                city TEXT,
                country TEXT,
                username TEXT,
                email TEXT,
                amount NUMERIC,
                currency TEXT,
                postal TEXT,
                has_nz_tax_15 TEXT
            );
        """)
        address_str = result.address.to_string() if result.address else None

        await conn.execute("""
            INSERT INTO clients (name, address, city, country, username, email, amount, currency, postal, has_nz_tax_15) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, 
        result.name, address_str, result.city, result.country, 
        result.username, result.email, result.amount, result.currency, result.postal, result.has_nz_tax_15)
    finally:
        await conn.close()


async def extract_invoice_multimedia(text_prompt: str, files_list: list) -> InvoiceData:
    """
    Принимает накопленный текст и список кортежей файлов [(file_bytes, mime_type), ...]
    И отправляет всё ОДНИМ запросом в ИИ.
    """
    contents = []
    
    # 1. Проходимся по всем накопленным файлам и парсим их в зависимости от типа
    for file_bytes, mime_type in files_list:
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            extracted_text = parse_docx(file_bytes)
            contents.append(f"\n[Данные из Word документа]:\n{extracted_text}")
        elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            extracted_text = parse_xlsx(file_bytes)
            contents.append(f"\n[Данные из Excel таблицы]:\n{extracted_text}")
        elif mime_type:
            # Для PDF и Картинок создаем Part объект (Gemini «увидит» их одновременно)
            file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
            contents.append(file_part)
            
    # 2. Добавляем объединенный текст переписки или подписей
    if text_prompt:
        contents.append(f"\nСопроводительный текст / Подписи: {text_prompt}")

    # Строгая инструкция по валидации данных (одинакова для всех моделей)
    system_instruction = (
        "Ты — эксперт по верификации международных адресов и парсингу данных.\n\n"
        "ПРАВИЛА И КРИТЕРИИ ВАЛИДАЦИИ:\n"
        "1. СТРУКТУРА АДРЕСА: Внутри объекта address разделяй данные строго по полям:\n"
        "   - address.street: Только улица, дом, корпус, квартира (например: 'Hacharimon Street 20, Apartment 6'). НЕ пиши сюда индекс, город и страну.\n"
        "   - address.city: Только город (например: 'Safed').\n"
        "   - address.country: Только страна (например: 'Israel').\n"
        "2. КОРНЕВЫЕ ПОЛЯ: Обязательно продублируй город в корневое поле 'city', а страну — в корневое поле 'country'. Они НЕ должны быть путыми.\n"
        "3. ПОЧТОВЫЙ ИНДЕКС: Найди почтовый индекс (ZIP/Postal code) и запиши его строго в отдельное поле 'postal'. Не удаляй его.\n"
        "4. ФИНАНСЫ: Сумму пиши в 'amount' (float), код валюты — в 'currency' (например, 'USD', 'EUR', 'ILS'). Если данных нет, ставь 0.0 и 'USD'.\n"
        "5. Если страна 'New Zealand' -> 'has_nz_tax_15' = 'Да', иначе 'Нет'.\n\n"
        
        "ПРИМЕР ИДЕАЛЬНОГО РАЗБОРА:\n"
        "Входной текст: 'Anastasia Katsevman, Hahermon St 20, Apt 6, Safed, Israel, 1310401, Nastya Belikova-Kats, Freezingboo@gmail.com'\n"
        "Твой JSON-выход должен быть точно таким:\n"
        "{\n"
        "  'name': 'Anastasia Katsevman',\n"
        "  'address': {\n"
        "    'street': 'Hacharimon Street 20, Apartment 6',\n"
        "    'city': 'Safed',\n"
        "    'country': 'Israel'\n"
        "  },\n"
        "  'city': 'Safed',\n"
        "  'country': 'Israel',\n"
        "  'username': 'Nastya Belikova-Kats',\n"
        "  'email': 'Freezingboo@gmail.com',\n"
        "  'amount': 0.0,\n"
        "  'currency': 'USD',\n"
        "  'postal': '1310401',\n"
        "  'has_nz_tax_15': 'Нет'\n"
        "}"
    )

    # Каскадный вызов ИИ (План А -> Б -> В)
    try:
        print(f"🤖 [План А] Анализируем медиапакет ({len(files_list)} файлов) в Gemini 2.5 Flash...")
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash', 
            contents=contents, 
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InvoiceData, 
                system_instruction=system_instruction
            ),
        )
        return InvoiceData.model_validate_json(response.text)
        
    except Exception as e_gemini_25:
        print(f"⚠️ План А сбой: {e_gemini_25}. Пробуем План Б (Gemini 2.0)...")
        try:
            response = await client.aio.models.generate_content(
                model='gemini-2.0-flash', 
                contents=contents, 
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=InvoiceData, 
                    system_instruction=system_instruction
                ),
            )
            return InvoiceData.model_validate_json(response.text)
        except Exception as e_gemini_20:
            print(f"🚨 План Б сбой: {e_gemini_20}. Переключаемся на План В (Groq)...")
            
            # Текстовая сборка для Groq (так как он не видит картинки/PDF напрямую)
            text_context = f"{system_instruction}\n\nСобери данные из текстов в единый JSON:\n"
            for item in contents:
                if isinstance(item, str):
                    text_context += f"\n{item}"
                    
            groq_response = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": text_context}],
                response_format={"type": "json_object"}
            )
            return InvoiceData.model_validate_json(groq_response.choices[0].message.content)