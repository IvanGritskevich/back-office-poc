from pydantic import BaseModel, Field
from typing import Optional

class AddressDetail(BaseModel):
    # Убираем default="", оставляем просто описание
    street: Optional[str] = Field(description="Только улица, дом, корпус, квартира. БЕЗ города и БЕЗ страны.")
    city: Optional[str] = Field(description="Только название города/населенного пункта.")
    country: Optional[str] = Field(description="Только название страны.")

    def to_string(self) -> str:
        return self.street if self.street and self.street.strip() else "Не указан"


class InvoiceData(BaseModel):
    # Убираем все default=None, default=0.0, default="USD" и default="Нет"
    name: Optional[str] = Field(description="Полное имя клиента.")
    address: Optional[AddressDetail] = Field(description="Распарсенный объект адреса.")
    city: Optional[str] = Field(description="Город проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда город из адреса).")
    country: Optional[str] = Field(description="Страна проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда страну из адреса).")
    username: Optional[str] = Field(description="Юзернейм пользователя в Телеграм или мессенджере.")
    email: Optional[str] = Field(description="Контактный email.")
    amount: Optional[float] = Field(description="Сумма счета числом. Если не найдена, ИИ вернет пустоту, а не 0.0.")
    currency: Optional[str] = Field(description="Международный трехзначный код валюты (USD, EUR, ILS и т.д.).")
    postal: Optional[str] = Field(description="Почтовый индекс (ZIP/Postal code).")
    has_nz_tax_15: Optional[str] = Field(description="Если страна 'New Zealand' -> 'Да', иначе -> 'Нет'")