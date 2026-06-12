import os
import json
import asyncpg
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from pathlib import Path
import startGpt

# Загружаем доступы к БД
load_dotenv(dotenv_path=Path('key.env'))

app = FastAPI(title="Invoice Verification Service")
templates = Jinja2Templates(directory="templates")

async def get_db_conn():
    """Создает быстрое подключение к Postgres"""
    return await asyncpg.connect(
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "exel_group"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432")
    )

class MapObject:
    def __init__(self, d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
               setattr(self, a, [MapObject(x) if isinstance(x, dict) else x for x in b])
            else:
               setattr(self, a, MapObject(b) if isinstance(b, dict) else b)

# 1. ЕСЛИ ПОЛЬЗОВАТЕЛЬ СРАЗУ НАЖАЛ "ВСЕ ВЕРНО" В ПИСЬМЕ
@app.get("/confirm/{pending_id}", response_class=HTMLResponse)
async def confirm_invoice(pending_id: int, request: Request):
    conn = await get_db_conn()
    try:
        row = await conn.fetchrow("SELECT raw_data, status FROM pending_invoices WHERE id = $1", pending_id)
        if not row or row['status'] != 'pending':
            return "<h3>❌ Сессия недоступна или уже закрыта</h3>"

        invoice_dict = json.loads(row['raw_data'])
        
        # Превращаем словарь в объект, чтобы работал вызов .name, .amount внутри твоей save_to_db
        invoice_obj = MapObject(invoice_dict)
        
        # 🚀 ВЫГРУЖАЕМ В ТВОИ БОЕВЫЕ ТАБЛИЦЫ (clients и bills)
        SYSTEM_MAIL_MANAGER_ID = 99999
        await startGpt.save_to_db(invoice_obj, manager_id=SYSTEM_MAIL_MANAGER_ID)
        
        # Закрываем статус во временной таблице
        await conn.execute("UPDATE pending_invoices SET status = 'confirmed' WHERE id = $1", pending_id)
        
        return templates.TemplateResponse(
            request=request, name="success.html", 
            context={"name": invoice_dict.get('name'), "amount": invoice_dict.get('amount')}
        )
    finally:
        await conn.close()

@app.get("/edit/{pending_id}", response_class=HTMLResponse)
async def edit_invoice_form(pending_id: int, request: Request):
    conn = await get_db_conn()
    try:
        row = await conn.fetchrow("SELECT raw_data, status FROM pending_invoices WHERE id = $1", pending_id)
        if not row or row['status'] != 'pending':
            return "<h3>❌ Сессия недоступна или уже закрыта</h3>"
        
        invoice_data = json.loads(row['raw_data'])
        
        # --- ИСПРАВЛЕНИЕ: РАСПАКОВКА СЛОВАРЯ АДРЕСА ---
        # Если ИИ засунул в "address" словарь вместо строки
        if isinstance(invoice_data.get('address'), dict):
            addr_dict = invoice_data['address']
            # Вытаскиваем улицу/дом в поле адреса
            invoice_data['address'] = addr_dict.get('street') or addr_dict.get('address') or ""
            # Если в основном пакете не было города/страны, берем их из словаря адреса
            if not invoice_data.get('city'): invoice_data['city'] = addr_dict.get('city') or ""
            if not invoice_data.get('country'): invoice_data['country'] = addr_dict.get('country') or ""
            if not invoice_data.get('postal'): invoice_data['postal'] = addr_dict.get('postal') or addr_dict.get('zip') or ""

        return templates.TemplateResponse(
            request=request, 
            name="edit.html", 
            context={"pending_id": pending_id, "data": invoice_data}
        )
    finally:
        await conn.close()


# 2. ЕСЛИ ПОЛЬЗОВАТЕЛЬ ОТРЕДАКТИРОВАЛ ДАННЫЕ В ФОРМЕ И НАЖАЛ "СОХРАНИТЬ"
@app.post("/edit/{pending_id}")
async def save_edited_invoice(
    pending_id: int,
    request: Request,
    name: str = Form(...),
    client_email: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    postal: str = Form(""),
    amount: float = Form(...),
    currency: str = Form(...)
):
    conn = await get_db_conn()
    try:
        # Собираем ПОЛНЫЙ пакет данных, идентичный твоей структуре БД
        updated_dict = {
            "name": name,
            "email": client_email,
            "address": address,
            "city": city,
            "country": country,
            "postal": postal,     # Почтовый индекс идет отдельным полем по твоим правилам!
            "amount": amount,
            "currency": currency
        }
        
        # Превращаем в объект для совместимости с твоей функцией записи
        invoice_obj = MapObject(updated_dict)
        
        # 🚀 ВЫГРУЖАЕМ В ТВОИ БОЕВЫЕ ТАБЛИЦЫ (clients и bills)
        SYSTEM_MAIL_MANAGER_ID = 99999
        await startGpt.save_to_db(invoice_obj, manager_id=SYSTEM_MAIL_MANAGER_ID)
        
        # Обновляем временную таблицу (сохраняем историю того, что исправил человек)
        await conn.execute(
            "UPDATE pending_invoices SET raw_data = $1, status = 'confirmed' WHERE id = $2",
            json.dumps(updated_dict), pending_id
        )
        print(f"✅ Данные инвойса {pending_id} успешно скорректированы человеком и сохранены в clients/bills.")
        
        return templates.TemplateResponse(
            request=request, name="success.html", 
            context={"name": name, "amount": amount}
        )
    finally:
        await conn.close()