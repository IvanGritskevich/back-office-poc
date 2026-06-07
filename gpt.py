from pydantic import BaseModel
from typing import Optional

from pydantic import BaseModel, Field
from typing import Optional

class AddressDetail(BaseModel):
    # Добавляем description, чтобы ИИ понимал границы полей
    street: Optional[str] = Field(default="", description="Только улица, дом, корпус, квартира. БЕЗ города и БЕЗ страны.")
    city: Optional[str] = Field(default="", description="Только название города/населенного пункта.")
    country: Optional[str] = Field(default="", description="Только название страны.")

    def to_string(self) -> str:
        # ИСПРАВЛЕНО: Теперь берем ТОЛЬКО street, чтобы адрес не был слишком длинным и не дублировал город/страну
        return self.street if self.street and self.street.strip() else "Не указан"


class InvoiceData(BaseModel):
    name: Optional[str] = Field(default=None, description="Полное имя клиента.")
    address: Optional[AddressDetail] = Field(default=None, description="Распарсенный объект адреса.")
    
    # Вот эти поля оставались пустыми, теперь мы жестко привязываем их логику
    city: Optional[str] = Field(default=None, description="Город проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда город из адреса).")
    country: Optional[str] = Field(default=None, description="Страна проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда страну из адреса).")
    
    username: Optional[str] = Field(default=None, description="Юзернейм пользователя в Телеграм или мессенджере.")
    email: Optional[str] = Field(default=None, description="Контактный email.")
    amount: float = Field(default=None, description="Сумма счета числом.")
    currency: str = Field(default=None, description="Международный трехзначный код валюты (USD, EUR, ILS и т.д.).")
    postal: Optional[str] = Field(default=None, description="Почтовый индекс (ZIP/Postal code).")
    has_nz_tax_15: str = Field(default=None, description="Если страна 'New Zealand' -> 'Да', иначе -> 'Нет'")