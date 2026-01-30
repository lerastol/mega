# Coding Agents — Мегашкола

Агентная система для SDLC в GitHub: Code Agent и AI Reviewer Agent (по ТЗ «Coding Agents»).

## Этап 1: Инфраструктура и окружение

### Структура

```
mega/
├── src/
│   ├── main.py          # Точка входа
│   ├── github_client.py # Работа с GitHub API
│   └── llm_client.py    # OpenAI / YandexGPT
├── config/
│   └── settings.yaml
├── .github/workflows/
│   └── agent_trigger.yml # Триггер на issues/PR
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

### Быстрый старт

1. **Клонировать и перейти в каталог**
   ```bash
   cd mega
   ```

2. **Создать `.env` из примера**
   ```bash
   copy .env.example .env
   ```
   Заполнить `GITHUB_TOKEN`, для LLM по умолчанию — `YANDEX_API_KEY` и `YANDEX_FOLDER_ID` (Yandex GPT); при необходимости `GITHUB_REPOSITORY`.

3. **Локально (без Docker)**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   # Code Agent (полный цикл: Issue → код → проверки → PR):
   python src/main.py --issue 1
   # Режим скелета (только тесты чтения/LLM/записи):
   python src/main.py --issue 1 --skeleton
   ```

4. **Через Docker**
   ```bash
   docker compose up --build
   ```

### Проверка скелета

- **Тест Issues:** создать Issue в репозитории → запустить workflow или `python src/main.py --issue <номер>` — скрипт должен прочитать текст Issue.
- **Тест LLM:** при заданных `YANDEX_API_KEY` и `YANDEX_FOLDER_ID` (Yandex GPT по умолчанию) или `OPENAI_API_KEY` скрипт отправляет тестовый запрос и выводит ответ в консоль.
- **Тест записи:**
  - комментарий в Issue: `python src/main.py --issue <номер> --test-write`;
  - пустая ветка: `python src/main.py --branch test-agent-branch --test-write`.

### GitHub Actions

- В репозитории: **Settings → Secrets and variables → Actions** добавить:
  - **Yandex GPT (по умолчанию):** `YANDEX_API_KEY` и `YANDEX_FOLDER_ID`;
  - **OpenAI:** `OPENAI_API_KEY` или `LLM_API_KEY`, если используете `LLM_PROVIDER=openai`.
- При создании/редактировании Issue или PR workflow «Agent Trigger» собирает образ и запускает контейнер с контекстом события (номер Issue и т.д.).

### Результат этапа 1

Работающая цепочка: **Событие в GitHub → Запуск Action → Скрипт получает данные → LLM отвечает → Скрипт может писать в GitHub** (комментарий/ветка).

---

## Этап 2: Code Agent (CLI)

CLI-инструмент превращает Issue в Pull Request с проверенным кодом.

### Запуск

- **Code Agent (полный цикл):** `python src/main.py --issue 123`  
  Парсинг Issue → контекст репо → LLM генерирует код (JSON) → применение к файлам → ruff, black, mypy, pytest (с retry при ошибках) → ветка `fix/issue-123` → коммит → push → создание PR с «Closes #123».
- **Скелет (тесты):** `python src/main.py --issue 1 --skeleton`

### Компоненты

- **issue_parser.py** — текст Issue, структура репо, ключевые файлы, комментарии Reviewer (при повторе).
- **prompts.py** — System Prompt (Senior Python Developer), формат вывода JSON `{files: [{path, content}]}`.
- **code_applier.py** — разбор ответа LLM и запись файлов.
- **quality_runner.py** — black (форматирование), ruff check, mypy, pytest; при падении лог отправляется в LLM для исправления (до лимита итераций).
- **git_runner.py** — создание ветки, коммит, push (в т.ч. с GITHUB_TOKEN для Actions).

### GitHub Actions

Workflow монтирует workspace в контейнер (`-v $GITHUB_WORKSPACE:/app`), чтобы агент мог писать файлы и выполнять git push. При открытии/редактировании **Issue** запускается **Code Agent**; при открытии/обновлении **Pull Request** запускается **AI Reviewer Agent** (этап 3).

---

## Этап 3: AI Reviewer Agent

Автоматический ревьюер PR: проверяет соответствие кода задаче из Issue, стиль, безопасность и публикует вердикт (APPROVE / REQUEST_CHANGES) с отчётом и inline-комментариями.

### Запуск

- **Reviewer (по PR):** `python src/main.py --pr 5`  
  Сбор контекста PR (diff, Issue, CI) → LLM анализирует → публикация ревью с разделами ✅ / ⚠️ / ❌ и (опционально) inline-комментариями.
- В **GitHub Actions** при событии **pull_request** (opened, synchronize) workflow передаёт `PR_NUMBER`, и контейнер запускает Reviewer Agent.

### Компоненты

- **pr_context.py** — сбор контекста: diff (GitHub API), связанный Issue (Closes #N), список изменённых файлов, результаты CI (workflow runs).
- **prompts/reviewer_v1.txt** и **REVIEWER_SYSTEM_PROMPT** в prompts.py — правила проверки: функциональность (Diff vs Issue), безопасность, читаемость (PEP8/black/ruff).
- **reviewer_agent.py** — вызов LLM, разбор JSON (verdict, summary, inline_comments), публикация ревью через `create_pr_review` (APPROVE или REQUEST_CHANGES).
- **github_client.py** — добавлены: `get_pr_details`, `get_pr_diff`, `get_pr_changed_files`, `parse_issue_number_from_pr`, `create_pr_review`, `get_workflow_runs_for_head`, `get_review_count_by_user`.

### Лимит итераций и логирование

- Не более **3 ревью** на один PR от одного бота (`REVIEWER_MAX_ITERATIONS`), чтобы избежать бесконечного цикла с Code Agent.
- Вердикт и фрагмент summary выводятся в логи GitHub Actions для отладки.

### Результат этапа 3

Полный цикл: **Issue → Code Agent создаёт PR → CI и Reviewer Agent запускаются по PR → Reviewer оставляет отчёт и APPROVE/REQUEST_CHANGES → при REQUEST_CHANGES Code Agent может править и пушить снова** (до лимита итераций).

---

## Этап 4: Управление циклом (Orchestration)

Оркестрация «диалога» между Code Agent и Reviewer Agent: замыкание цикла правок, лимиты итераций, метки, логи.

### Замыкание цикла (Feedback Integration)

- **issue_parser.py**: `get_reviewer_feedback_from_pr(gh, pr_number)` — только комментарии AI Reviewer (по формату отчёта ## ✅ / ## ❌ или по state CHANGES_REQUESTED/COMMENTED).  
- **get_issue_context_for_pr(gh, pr_number)** — контекст для режима правок: Issue из PR, код из head-ветки PR, замечания Reviewer.  
- **prompts.py**: **FIX_PROMPT** — «Проанализируй замечания ревьюера и внеси правки в существующий код». Инкрементальные изменения (hotfixes), не переписывание всего проекта.

### State Management (лимиты и защита от циклов)

- **state_manager.py** — чтение/запись счётчика итераций в теле PR: тег `<!-- iteration: N -->`.  
- **MAX_ITERATIONS** (переменная окружения `CODE_AGENT_MAX_ITERATIONS`, по умолчанию 5): перед запуском Code Agent Fix проверяется текущая итерация; при достижении лимита — комментарий «Достигнут лимит итераций. Требуется вмешательство человека» и метка **error**.  
- **Детектор стагнации**: если LLM не вернул изменения или diff пустой после применения — цикл прерывается, комментарий в PR.

### Code Agent Fix (режим правок по PR)

- **code_agent.run_code_agent_fix(pr_number)** — checkout head-ветки PR → контекст с замечаниями Reviewer → FIX_PROMPT → применение правок → проверки → коммит и push в ту же ветку → обновление `iteration` в теле PR.  
- Запуск: через **FIX_MODE=1** и **PR_NUMBER** (в workflow — при событии `pull_request_review` и `state == changes_requested`).

### Метки (Labels)

- **ai-thinking** — вешается при создании PR (Code Agent) и при старте правок (Code Agent Fix); снимается Reviewer при APPROVE.  
- **needs-fix** — вешается Reviewer при REQUEST_CHANGES.  
- **reviewed** — вешается Reviewer при APPROVE.  
- **error** — при достижении лимита итераций или стагнации.

### Оркестрация в GitHub Actions

- **on**: `issues` (opened, edited), `pull_request` (opened, synchronize), **pull_request_review** (submitted).  
- **Условие запуска job**: `issues` или `pull_request` или (`pull_request_review` и `review.state == CHANGES_REQUESTED`).  
- При **pull_request_review** и **changes_requested** передаются **FIX_MODE=1** и **PR_NUMBER** → в контейнере запускается **run_code_agent_fix(pr_number)**.  
- **Checkout**: для события review используется `ref: github.event.pull_request.head.sha`, чтобы править в ветке PR.  
- **Логи**: вывод агента пишется в `agent.log` (tee), затем **upload-artifact** сохраняет логи в Artifacts (имя: `agent-logs-<run_id>-<event_name>`, retention 7 дней).

### Результат этапа 4

Полностью автономный конвейер: **создаёте Issue → через несколько минут получаете готовый, проверенный и при необходимости исправленный по замечаниям Reviewer Pull Request**, с контролем лимита итераций и без бесконечных циклов.

---

## Валидация и воспроизведение

### Чеклист валидации

Полный чеклист — в **[docs/VALIDATION.md](docs/VALIDATION.md)**. Кратко:

- **Code Agent:** Issue → ветка `fix/issue-N` → коммит → PR с «Closes #N», метка **ai-thinking**.
- **Reviewer Agent:** PR → ревью (APPROVE или REQUEST_CHANGES) с summary и inline-комментариями; при APPROVE — метка **reviewed**, снятие **ai-thinking**; при REQUEST_CHANGES — **needs-fix**.
- **Цикл правок:** при REQUEST_CHANGES запускается Code Agent Fix → правки → push → повторное ревью; счётчик итераций в теле PR (`<!-- iteration: N -->`); лимит и стагнация → комментарий в PR и метка **error**.
- **Качество:** black, ruff, mypy, pytest в Code Agent; при падении — повторная попытка с логом в LLM.
- **Воспроизводимость:** запуск одной командой (`docker compose up --build` или по шагам из README); версии Python 3.11+, зависимости из `requirements.txt`.

### Примеры Issues и ожидаемое поведение

Шаблоны текстов Issues и сценарии — в каталоге **`docs/examples/`**:

- **`docs/examples/issues/simple_task.md`** — простая задача (опечатка, добавление зависимости); ожидание: один цикл, APPROVE.
- **`docs/examples/issues/medium_task.md`** — задача с доработкой (новая функция + тесты); ожидание: 1–2 итерации после замечаний Reviewer, затем APPROVE.
- **`docs/examples/issues/task_with_error.md`** — задача с заведомой ошибкой (например, вывод API-ключа в лог); ожидание: Reviewer REQUEST_CHANGES → Code Agent Fix → APPROVE.

После прогона на вашем репозитории добавьте в **REPORT.md** (раздел 5) конкретные ссылки на Issues и PR, например:

- Issue #X — «Краткое описание» → PR #Y (итерации 1–2), итог: APPROVE.
- Issue #Z — «Задача с ошибкой» → PR #W, Reviewer: REQUEST_CHANGES → Fix → APPROVE.
#   m e g a  
 