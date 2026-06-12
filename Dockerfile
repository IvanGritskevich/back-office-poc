FROM python:3.11-slim-bookworm

WORKDIR /app

# Устанавливаем системные зависимости для корректной работы сети и сборки пакетов
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта
COPY . .

EXPOSE 8000
