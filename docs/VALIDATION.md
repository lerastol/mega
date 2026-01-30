# Валидация и воспроизведение

Чеклист для проверки работы агентной системы SDLC на реальном репозитории.

## Предварительные условия

- [ ] Репозиторий клонирован, `.env` заполнен (`GITHUB_TOKEN`, `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` или `OPENAI_API_KEY`, при необходимости `GITHUB_REPOSITORY`).
- [ ] В репозитории настроены GitHub Actions Secrets (см. README и SETUP.md).
- [ ] Локально: `pip install -r requirements.txt` или Docker: `docker compose build`.

## Чеклист валидации

### 1. Code Agent (Issue → PR)

- [ ] Создано Issue с чётким описанием задачи (см. `docs/examples/issues/`).
- [ ] Запущен Code Agent: `python src/main.py --issue <N>` или через workflow при открытии Issue.
- [ ] Создана ветка `fix/issue-<N>` и коммит с изменениями.
- [ ] Создан Pull Request с текстом «Closes #<N>».
- [ ] На PR повешена метка **ai-thinking** (до ревью).
- [ ] В логах (консоль или Artifacts) нет критических ошибок.

### 2. AI Reviewer Agent (PR → ревью)

- [ ] После создания/обновления PR запустился workflow и Reviewer Agent.
- [ ] Опубликовано ревью: либо **APPROVE**, либо **REQUEST_CHANGES** с summary и (при необходимости) inline-комментариями.
- [ ] При APPROVE: метки **reviewed**, снята **ai-thinking**.
- [ ] При REQUEST_CHANGES: метка **needs-fix**.

### 3. Цикл правок (Fix mode)

- [ ] После REQUEST_CHANGES при событии `pull_request_review` (submitted, changes_requested) запустился Code Agent в режиме Fix.
- [ ] В теле PR присутствует тег `<!-- iteration: N -->`, счётчик увеличивается после каждого Fix.
- [ ] После push в ту же ветку снова запустился Reviewer; цикл повторяется до APPROVE или лимита.
- [ ] Нет бесконечного цикла: срабатывает лимит итераций (`CODE_AGENT_MAX_ITERATIONS`) или детектор стагнации.
- [ ] При лимите/стагнации: комментарий в PR и метка **error**.

### 4. Качество кода и тесты

- [ ] Code Agent перед push запускает black, ruff check, mypy, pytest (см. `quality_runner.py`).
- [ ] При падении проверок лог отправляется в LLM для повторной попытки (в пределах лимита).
- [ ] Локально: `pytest tests/` проходит (импорты и placeholder-тесты).

### 5. Воспроизводимость

- [ ] Запуск одной командой: `docker compose up --build` или по шагам из README (venv, pip, `python src/main.py --issue N`).
- [ ] Версии: Python 3.11+, зависимости из `requirements.txt`; при необходимости зафиксировать в `pyproject.toml` или CI.

## Примеры сценариев

| Сценарий | Ожидание |
|----------|----------|
| **Простая задача** (опечатка в README, добавление зависимости в requirements.txt) | Один цикл, PR с минимальными изменениями, APPROVE. |
| **Задача с доработкой** (новая функция + тесты) | При необходимости 1–2 итерации после замечаний Reviewer, затем APPROVE. |
| **Задача с заведомой ошибкой** (например, вывод API-ключа в лог) | Reviewer: REQUEST_CHANGES → Code Agent вносит правки → повторное ревью → APPROVE. |

Шаблоны текстов Issues для этих сценариев — в `docs/examples/issues/`.

## Где смотреть результаты

- **PR и метки:** вкладка Pull Requests репозитория; на каждом PR — метки ai-thinking, needs-fix, reviewed, error.
- **Ревью и комментарии:** вкладка «Files changed» / «Conversation» у PR.
- **Логи агента:** GitHub Actions → выбранный workflow run → Artifacts (имя вида `agent-logs-<run_id>-<event_name>`).
- **Счётчик итераций:** в теле PR искать `<!-- iteration: N -->`.

## После прогона

Добавить в REPORT.md (раздел 5) и/или в README конкретные ссылки:

- Issue #X — «Краткое описание» → PR #Y (итерации 1–2), итог: APPROVE.
- Issue #Z — «Задача с ошибкой» → PR #W, Reviewer: REQUEST_CHANGES → Fix → APPROVE.

Это завершает валидацию и документирует воспроизводимость на вашем репо.
