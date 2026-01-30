# ТЗ: Python 3.11+
FROM python:3.11-slim

WORKDIR /app

# Git для коммита и push в Code Agent
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код, конфиг, промпты и тесты
COPY src/ ./src/
COPY config/ ./config/
COPY prompts/ ./prompts/
COPY tests/ ./tests/
COPY pyproject.toml ./

# Точка входа
CMD ["python", "src/main.py"]
