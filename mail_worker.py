import os
import re
import imaplib
import email
from email.header import decode_header
import asyncio
from dotenv import load_dotenv
from pathlib import Path
import startGpt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
#
#async def send_verification_email(to_email: str, result, pending_id: int):
#    """Отправляет сотруднику письмо с результатами разбора ИИ и ссылками на действия"""
#    
#    # Ссылки будут вести на наш будущий веб-сервер (пока локальный)
#    confirm_url = f"http://localhost:8000/confirm/{pending_id}"
#    edit_url = f"http://localhost:8000/edit/{pending_id}"
#
#    msg = MIMEMultipart("alternative")
#    msg["Subject"] = f"🤖 Проверка инвойса: {result.name or 'Неизвестный клиент'}"
#    msg["From"] = MAIL_USER
#    msg["To"] = to_email
#
#    # Формируем красивое HTML-письмо с кнопками
#    html = f"""
#    <html>
#      <body style="font-family: Arial, sans-serif; color: #333;">
#        <h2 style="color: #4A90E2;">📋 Результат автоматического разбора ИИ</h2>
#        <p>Пожалуйста, проверьте корректность данных перед отправкой в базу данных:</p>
#        <table style="border-collapse: collapse; width: 100%; max-width: 500px;">
#          <tr style="background-color: #f2f2f2;"><td style="padding: 8px; font-weight: bold;">Имя клиента:</td><td style="padding: 8px;">{result.name}</td></tr>
#          <tr><td style="padding: 8px; font-weight: bold;">Сумма:</td><td style="padding: 8px;">{result.amount} {result.currency}</td></tr>
#          <tr style="background-color: #f2f2f2;"><td style="padding: 8px; font-weight: bold;">Город/Страна:</td><td style="padding: 8px;">{result.city}, {result.country}</td></tr>
#          <tr><td style="padding: 8px; font-weight: bold;">Индекс:</td><td style="padding: 8px;">{result.postal}</td></tr>
#        </table>
#        
#        <br><br>
#        <div style="display: flex; gap: 15px;">
#            <a href="{confirm_url}" style="background-color: #2ECC71; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">✅ Всё верно, внести в БД</a>
#            <a href="{edit_url}" style="background-color: #E74C3C; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">❌ Есть ошибки, исправить</a>
#        </div>
#        <br>
#        <p style="font-size: 12px; color: #7f8c8d;">ID сессии проверки: {pending_id}</p>
#      </body>
#    </html>
#    """
#    
#    msg.attach(MIMEText(html, "html", "utf-8"))
#
#    # Асинхронно отправляем через фоновый поток, чтобы не вешать воркер
#    def _send():
#        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
#            server.starttls() # Включаем шифрование
#            server.login(MAIL_USER, MAIL_PASSWORD)
#            server.sendmail(MAIL_USER, to_email, msg.as_string())
#
#    await asyncio.to_thread(_send)
#    print(f"📩 Письмо-верификация успешно отправлено на {to_email}")
async def send_verification_email(to_email: str, result, pending_id: int):
    """Имитирует отправку письма и выводит интерактивную ссылку в консоль VS Code"""
    
    # Ссылки на твой будущий локальный веб-интерфейс проверки
    confirm_url = f"http://localhost:8000/confirm/{pending_id}"
    edit_url = f"http://localhost:8000/edit/{pending_id}"

    print("\n" + "="*60)
    print(f"📨 [ИМИТАЦИЯ ОТПРАВКИ EMAIL] -> Направлено на: {to_email}")
    print(f"📋 Тема: Проверка инвойса: {result.name or 'Неизвестный клиент'}")
    print(f"💰 Сумма к верификации: {result.amount} {result.currency}")
    print("-"*60)
    print("🔗 ДЛЯ ТЕСТИРОВАНИЯ КЛИКНИТЕ ПО ССЫЛКЕ НИЖЕ:")
    print(f"✅ Подтвердить и выгрузить в БД: {confirm_url}")
    print(f"❌ Изменить данные (ошибки ИИ):   {edit_url}")
    print("="*60 + "\n")

    # Небольшая задержка, имитирующая отправку по сети
    await asyncio.sleep(0.5)
# Загружаем конфигурацию
dotenv_path = Path('key.env')
load_dotenv(dotenv_path=dotenv_path)

MAIL_SERVER = os.getenv("MAIL_SERVER", "imap.gmail.com")
MAIL_USER = os.getenv("MAIL_USER")       # Твоя почта
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") # Секретный 16-значный пароль приложения

def decode_mime_words(s):
    """Декодирует тему письма или имя файла, если они на русском/другом языке"""
    if not s:
        return ""
    parts = decode_header(s)
    result = []
    for text, encoding in parts:
        if isinstance(text, bytes):
            result.append(text.decode(encoding or "utf-8", errors="ignore"))
        else:
            result.append(str(text))
    return "".join(result)

async def check_email_invoices():
    """Фоновая функция проверки новых писем и вложений"""
    print("📬 Проверка почтового ящика на наличие инвойсов...")
    
    try:
        mail = imaplib.IMAP4_SSL(MAIL_SERVER)
        mail.login(MAIL_USER, MAIL_PASSWORD)
        mail.select("INBOX")

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            mail.close()
            mail.logout()
            return

        mail_ids = messages[0].split()
        
        for mail_id in mail_ids:
            status, msg_data = mail.fetch(mail_id, "(RFC822)")
            if status != "OK":
                continue
                
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            sender = decode_mime_words(msg.get("From"))
            subject = decode_mime_words(msg.get("Subject"))
            
            # --- ИСПРАВЛЕНИЕ: СТРОГАЯ КОРПОРАТИВНАЯ ЗАЩИТА ---
            # Из строки "Anastasia <nastya@korudh.com>" достаем чистый email внутри скобок < >
            
            email_match = re.search(r'[\w\.-]+@[\w\.-]+', sender)
            
            if not email_match:
                print(f"⚠️ Не удалось распознать email отправителя: {sender}. Пропускаем.")
                mail.store(mail_id, "+FLAGS", "\\Seen")
                continue
                
            sender_email = email_match.group(0).lower()
            
            # Проверяем, заканчивается ли почта на домен компании @korudh.com
            if not sender_email.endswith("@korudh.com"):
                print(f"⛔️ БЛОКИРОВКА: Письмо от {sender_email} отклонено. Домен не принадлежит компании @korudh.com!")
                mail.store(mail_id, "+FLAGS", "\\Seen") # Помечаем прочитанным, чтобы спам не копился
                continue

            combined_text = f"Тема письма: {subject}\n"
            files_list = []
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    # 1. Собираем обычный текст письма
                    if content_type == "text/plain" and "attachment" not in content_disposition and "inline" not in content_disposition:
                        payload = part.get_payload(decode=True)
                        if payload:
                            combined_text += f"\nТекст письма:\n{payload.decode('utf-8', errors='ignore')}"
                    
                    # 2. ИСПРАВЛЕНО: Собираем файлы, если они прикреплены КАК файлы ИЛИ вставлены КАРТИНКОЙ в текст
                    elif "attachment" in content_disposition or "inline" in content_disposition:
                        filename = decode_mime_words(part.get_filename())
                        file_bytes = part.get_payload(decode=True)
                        
                        # У картинок внутри текста (inline) иногда может не быть имени файла, 
                        # даем им временное имя, чтобы ИИ понимал, с чем работает
                        if not filename and content_type.startswith("image/"):
                            filename = f"inline_image_{len(files_list) + 1}.jpg"
                        
                        if filename and file_bytes:
                            print(f"📎 Найдено вложение ({'в тексте' if 'inline' in content_disposition else 'файлом'}): {filename} ({content_type})")
                            files_list.append((file_bytes, content_type))
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    combined_text += f"\nТекст письма:\n{payload.decode('utf-8', errors='ignore')}"

            # --- ИСПРАВЛЕНИЕ 2: ПРОВЕРКА НА НАЛИЧИЕ ПРИЗНАКОВ ИНВОЙСА ---
            keywords = ["инвойс", "счет", "invoice", "bill", "payment", "оплата", "check"]
            has_keywords = any(word in combined_text.lower() for word in keywords)
            
            # Если нет вложений И нет ключевых слов в тексте — это не инвойс
            if not files_list and not has_keywords:
                print(f"🗑 Письмо '{subject}' не содержит вложений или признаков инвойса. Пропускаем.")
                mail.store(mail_id, "+FLAGS", "\\Seen")
                continue

            # Если проверка на домен @korudh.com и наличие ключевых слов пройдена — парсим:
            try:
                print(f"📧 Обрабатываем целевое письмо: {subject}")
                result = await startGpt.extract_invoice_multimedia(text_prompt=combined_text, files_list=files_list)

                # 1. Вместо немедленного save_to_db, делаем пред-сохранение во временную таблицу
                # База данных сама сгенерирует уникальный serial ID
                pending_id = await startGpt.save_to_pending(sender_email=sender_email, result=result)
                print(f"📥 Данные временно сохранены в pending_invoices под ID: {pending_id}")
                
                # 2. Отправляем сотруднику письмо с его персональными кнопками-ссылками
                await send_verification_email(to_email=sender_email, result=result, pending_id=pending_id)
                
                # 3. Помечаем письмо прочитанным в почтовом ящике, так как мы его полностью обработали
                mail.store(mail_id, "+FLAGS", "\\Seen")
                print(f"✅ Письмо успешно обработано и ожидает подтверждения от {sender_email}\n")
                
            except Exception as gpt_err:
                print(f"❌ Ошибка разбора данных ИИ для письма: {gpt_err}")
                # Даже если что-то упало (например, ИИ выдал ошибку разметки), 
                # помечаем прочитанным, чтобы не спамить в API повторно
                mail.store(mail_id, "+FLAGS", "\\Seen")

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"🚨 Ошибка при работе с почтовым сервером: {e}")


async def main():
    print("🚀 Почтовый воркер для инвойсов успешно запущен...")
    while True:
        await check_email_invoices()
        # Опрашиваем почтовый ящик каждые 60 секунд
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())