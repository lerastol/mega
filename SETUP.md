# Пошаговая настройка

## 1. Файл `.env`

Файл **`.env`** уже создан в корне проекта. Откройте его и замените плейсхолдеры на реальные значения.

### GITHUB_TOKEN (Personal Access Token)

1. Зайдите на GitHub → **Settings** (ваш профиль) → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. **Generate new token (classic)**. Название, например: `mega-agent`.
3. Выберите права: **repo**, **issues**, **pull_requests**.
4. Сгенерируйте и скопируйте токен (начинается с `ghp_`).
5. В `.env` вставьте: `GITHUB_TOKEN=ghp_ваш_токен`.

### Yandex GPT (по умолчанию)

1. Зарегистрируйтесь в [Yandex Cloud](https://console.yandex.cloud).
2. Создайте каталог (folder) и получите его **идентификатор** (Folder ID).
3. Включите [YandexGPT API](https://cloud.yandex.ru/docs/yandexgpt/quickstart) и создайте **API-ключ** для сервисного аккаунта.
4. В `.env` укажите:
   - `YANDEX_API_KEY=ваш_api_ключ`
   - `YANDEX_FOLDER_ID=идентификатор_каталога`
5. Провайдер по умолчанию: `LLM_PROVIDER=yandex` (можно не указывать).

### OpenAI (опционально)

Если хотите использовать GPT-4o-mini: задайте в `.env` `LLM_PROVIDER=openai` и `OPENAI_API_KEY=sk-ваш_ключ`. Ключ создаётся на [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

### GITHUB_REPOSITORY

Формат: **владелец/репозиторий**. Пример: если репозиторий `https://github.com/leras/mega`, то:

```env
GITHUB_REPOSITORY=leras/mega
```

---

## 2. Локальная проверка

В каталоге проекта выполните:

```powershell
cd d:\itmo\mega

# Рекомендуется: виртуальное окружение
python -m venv .venv
.venv\Scripts\activate

# Зависимости
pip install -r requirements.txt

# Чтение Issue и тест LLM (подставьте номер существующего Issue)
python src/main.py --issue 1

# Тест записи: комментарий в Issue
python src/main.py --issue 1 --test-write
```

Если Issue с номером 1 нет — создайте любой Issue в репозитории и подставьте его номер.

---

## 3. Секреты в GitHub (для Actions)

Чтобы workflow в GitHub Actions мог вызывать LLM и API GitHub:

1. Откройте ваш репозиторий на GitHub.
2. **Settings** → **Secrets and variables** → **Actions**.
3. Для **Yandex GPT** (по умолчанию) добавьте секреты:
   - `YANDEX_API_KEY` — API-ключ из Yandex Cloud.
   - `YANDEX_FOLDER_ID` — идентификатор каталога.
4. Для **OpenAI** (если переключите провайдер): `OPENAI_API_KEY` или `LLM_API_KEY`.
5. Секрет **GITHUB_TOKEN** создаётся автоматически для каждого workflow — его указывать не нужно.

После пуша в репозиторий при открытии/редактировании Issue или Pull Request будет запускаться workflow и контейнер с агентом.

---

## 4. Docker

Когда `.env` заполнен, агента можно запустить одним контейнером:

```powershell
cd d:\itmo\mega
docker compose up --build
```

Переменные окружения подхватываются из `.env`. Для фонового режима: `docker compose up -d --build`.
