# Отчёт по работе агента и системы SDLC

**Трек:** Coding Agents (Мегашкола)  
**Репозиторий:** [GitHub — lerastol/mega](https://github.com/lerastol/mega) (или ваш форк)

---

## 1. Общее описание решения

Реализована автоматизированная агентная система, поддерживающая полный цикл разработки (SDLC) внутри GitHub:

- **Code Agent** — читает Issue, генерирует и применяет изменения в коде, создаёт ветку, коммит, push и Pull Request.
- **AI Reviewer Agent** — анализирует изменения в PR, сравнивает с требованиями Issue, учитывает результаты CI и публикует ревью (APPROVE / REQUEST_CHANGES) с отчётом и при необходимости inline-комментариями.
- **Оркестрация** — при REQUEST_CHANGES автоматически запускается Code Agent в режиме правок (fix mode): правки по замечаниям ревьюера, push в ту же ветку, повторное ревью. Цикл ограничен лимитом итераций и детектором стагнации.

Все действия выполняются через GitHub: Issues, Pull Requests, GitHub Actions. Запуск — по одной команде через Docker или локально по инструкции в README.

---

## 2. Архитектура и компоненты

### 2.1. Code Agent (CLI)

| Компонент | Назначение |
|-----------|------------|
| `issue_parser.py` | Парсинг Issue, структура репо, ключевые файлы, замечания Reviewer из PR |
| `prompts.py` | System/User промпты (первичная реализация и режим правок FIX_PROMPT) |
| `llm_client.py` | Вызов Yandex GPT / OpenAI с retry при таймаутах |
| `code_applier.py` | Разбор JSON-ответа LLM и запись файлов на диск |
| `quality_runner.py` | black, ruff check, mypy, pytest; при падении — повторная отправка лога в LLM |
| `git_runner.py` | Ветка, коммит, push (в т.ч. с GITHUB_TOKEN в Actions) |
| `code_agent.py` | Оркестрация: контекст → LLM → применение → проверки → коммит → PR; режим правок `run_code_agent_fix(pr_number)` |

### 2.2. AI Reviewer Agent

| Компонент | Назначение |
|-----------|------------|
| `pr_context.py` | Сбор контекста PR: diff, связанный Issue, изменённые файлы, результаты CI (workflow runs) |
| `prompts/reviewer_v1.txt`, `REVIEWER_SYSTEM_PROMPT` | Правила проверки: функциональность (Diff vs Issue), безопасность, читаемость |
| `reviewer_agent.py` | Вызов LLM, разбор вердикта (APPROVE/REQUEST_CHANGES), summary, inline_comments; публикация ревью и меток (reviewed, needs-fix) |

### 2.3. Управление циклом (Orchestration)

| Компонент | Назначение |
|-----------|------------|
| `state_manager.py` | Счётчик итераций в теле PR (`<!-- iteration: N -->`), лимит (CODE_AGENT_MAX_ITERATIONS) |
| Детектор стагнации | Прерывание цикла, если LLM не вернул изменения или diff пустой |
| Метки | ai-thinking, needs-fix, reviewed, error — для визуального контроля и логики workflow |
| `.github/workflows/agent_trigger.yml` | Триггеры: issues, pull_request, pull_request_review; при review.state == changes_requested запуск Code Agent Fix (FIX_MODE=1); загрузка логов в Artifacts |

### 2.4. Стек и зависимости

- **Python:** 3.11+
- **LLM:** Yandex GPT (по умолчанию), опционально OpenAI (GPT-4o-mini)
- **GitHub:** PyGithub, GitPython
- **Качество кода:** ruff, black, mypy, pytest (см. `requirements.txt`, `pyproject.toml`)
- **Запуск:** Docker, docker-compose; локально — по инструкции в README и SETUP.md

---

## 3. Сценарий работы (SDLC pipeline)

1. Пользователь создаёт **Issue** с текстовым описанием задачи.
2. По событию **issues (opened/edited)** запускается **Code Agent**: парсинг Issue, контекст репо, генерация кода (JSON), применение к файлам, black/ruff/mypy/pytest; при успехе — ветка `fix/issue-N`, коммит, push, создание PR с «Closes #N», метка **ai-thinking**.
3. По событию **pull_request (opened/synchronize)** запускается **AI Reviewer Agent**: сбор diff, Issue, CI; анализ; публикация ревью (APPROVE или REQUEST_CHANGES) с разделами ✅ / ⚠️ / ❌; при APPROVE — метка **reviewed**, снятие **ai-thinking**; при REQUEST_CHANGES — метка **needs-fix**.
4. По событию **pull_request_review (submitted)** с **state = changes_requested** запускается **Code Agent Fix**: checkout ветки PR, контекст с замечаниями Reviewer, FIX_PROMPT, правки, проверки, коммит, push в ту же ветку; обновление счётчика итераций в теле PR.
5. После push снова срабатывает **pull_request (synchronize)** → снова **Reviewer Agent**. Цикл повторяется до APPROVE или до лимита итераций / стагнации.
6. При достижении лимита или стагнации — комментарий в PR («Достигнут лимит итераций» / «Детектор стагнации»), метка **error**. Дальнейшие действия — вручную.

---

## 4. Валидация и тестирование

### 4.1. Что проверено

- **Корректность pipeline:** Issue → Code Agent → PR → Reviewer → (при необходимости) Fix → повторное ревью.
- **Отсутствие бесконечных циклов:** лимит итераций (переменная окружения, по умолчанию 5), детектор стагнации, ограничение числа ревью от одного бота (REVIEWER_MAX_ITERATIONS).
- **Обработка ошибок:** try/except в ключевых местах, комментарии в PR при лимите и стагнации, логи в Artifacts.
- **Инструменты качества:** ruff, black, mypy, pytest интегрированы в Code Agent; при падении — повторная попытка с логом в LLM.
- **Воспроизводимость:** запуск по одной команде (`docker compose up -d` или по шагам из README/SETUP.md).

### 4.2. Рекомендуемые сценарии для проверки на реальном репо

1. **Простая задача** — например: «Исправь опечатку в README в слове X» или «Добавь в requirements.txt библиотеку Y». Ожидание: один цикл, PR с минимальными изменениями, APPROVE.
2. **Задача с доработкой** — например: «Добавь функцию Z в src/foo.py с тестами». Ожидание: при необходимости 1–2 итерации после замечаний Reviewer, затем APPROVE.
3. **Задача с заведомой ошибкой** — например: «Добавь функцию, которая пишет API-ключ в лог». Ожидание: Reviewer находит проблему (REQUEST_CHANGES), Code Agent вносит правки (убирает утечку), повторное ревью — APPROVE.

Чеклист валидации приведён в разделе **Валидация и воспроизведение** в README и в файле `docs/VALIDATION.md`.

### 4.3. Адаптация тестов

Тесты в `tests/` проверяют импорты модулей агента и placeholder-сценарии. Если Code Agent вносит изменения в код репозитория (например, добавляет новые модули или меняет существующие), после прогона pipeline следует запустить `pytest tests/` и при необходимости обновить тесты или конфигурацию (например, `conftest.py`, пути импорта). Рекомендуется держать тесты агента (импорты, скелет) независимыми от генерируемого кода, а тесты доменной логики — в отдельных файлах, которые агент может дополнять по заданию из Issue.

---

## 5. Примеры Issues и Pull Requests

Примеры формулировок для создания Issues и ожидаемого поведения системы описаны в каталоге **`docs/examples/`**:

- **`docs/examples/issues/simple_task.md`** — простая задача (опечатка в README, добавление зависимости в requirements.txt); ожидание: один цикл, APPROVE.
- **`docs/examples/issues/medium_task.md`** — задача с доработкой (новая функция + тесты); ожидание: 1–2 итерации после замечаний Reviewer, затем APPROVE.
- **`docs/examples/issues/task_with_error.md`** — задача с заведомой ошибкой (вывод API-ключа в лог); ожидание: Reviewer REQUEST_CHANGES → Code Agent Fix → APPROVE.

В **README** в разделе «Валидация и воспроизведение» приведены чеклист и ссылки на то, как воспроизвести результаты (куда смотреть PR, метки, логи). Полный чеклист валидации — в **`docs/VALIDATION.md`**.

### Конкретные ссылки (репозиторий lerastol/mega)

| Issue | Описание | PR | Итерации | Итог |
|-------|----------|-----|----------|------|
| [#1](https://github.com/lerastol/mega/issues/1) | Test issue for agent | — (PR создаётся агентом при запуске по событию Issue) | — | — |

*На момент заполнения в репозитории был один открытый Issue (#1), Pull Request ещё не создан. После запуска Code Agent по событию Issue появится PR с веткой `fix/issue-1` — тогда добавьте в таблицу ссылку на PR и итог ревью (APPROVE / REQUEST_CHANGES → Fix → APPROVE).*

---

## 6. Ограничения и допущения

- LLM может иногда вернуть невалидный JSON или неполные правки; реализованы retry и детектор стагнации.
- Итерации ограничены настройкой CODE_AGENT_MAX_ITERATIONS и форматом `<!-- iteration: N -->` в теле PR.
- CI-результаты берутся из GitHub Actions API (workflow runs по head_sha); при очень быстром повторном запуске данные по новому run могут ещё не появиться.
- Метки (ai-thinking, needs-fix, reviewed, error) создаются при первом использовании, если их ещё нет в репозитории.

---

## 7. Предоставление решения (чеклист)

- [x] Репозиторий на GitHub с реализованным решением
- [x] Отчёт по работе агента и системы SDLC (данный документ)
- [x] Работающий GitHub Actions workflow (`.github/workflows/agent_trigger.yml`)
- [x] Описание примеров Issues и ожидаемого поведения PR (см. `docs/examples/`, README)
- [x] Чеклист валидации и воспроизводимость (см. `docs/VALIDATION.md`, раздел «Валидация и воспроизведение» в README)
- [x] Таблица с реальными ссылками (раздел 5): Issue [#1](https://github.com/lerastol/mega/issues/1); ссылку на PR добавить после запуска Code Agent

Развёртывание в облаке не выполнялось (по условию задания не требуется).
