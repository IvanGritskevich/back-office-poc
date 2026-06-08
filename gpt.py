from pydantic import BaseModel
from typing import Optional

from pydantic import BaseModel, Field
from typing import Optional

class AddressDetail(BaseModel):
    street: Optional[str] = Field(default="", description="Только улица, дом, корпус, квартира. БЕЗ города и БЕЗ страны.")
    city: Optional[str] = Field(default="", description="Только название города/населенного пункта.")
    country: Optional[str] = Field(default="", description="Только название страны.")

    def to_string(self) -> str:
        return self.street if self.street and self.street.strip() else "Не указан"


class InvoiceData(BaseModel):
    name: Optional[str] = Field(default=None, description="Полное имя клиента.")
    address: Optional[AddressDetail] = Field(default=None, description="Распарсенный объект адреса.")
    city: Optional[str] = Field(default=None, description="Город проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда город из адреса).")
    country: Optional[str] = Field(default=None, description="Страна проживания клиента (ОБЯЗАТЕЛЬНО продублируй сюда страну из адреса).")
    username: Optional[str] = Field(default=None, description="Юзернейм пользователя в Телеграм или мессенджере.")
    email: Optional[str] = Field(default=None, description="Контактный email.")
    amount: float = Field(default=0.0, description="Сумма счета числом.")
    currency: str = Field(default="USD", description="Международный трехзначный код валюты (USD, EUR, ILS и т.д.).")
    postal: Optional[str] = Field(default=None, description="Почтовый индекс (ZIP/Postal code).")
    has_nz_tax_15: str = Field(default="Нет", description="Если страна 'New Zealand' -> 'Да', иначе -> 'Нет'")