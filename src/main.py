"""
Точка входа агента.
Запуск: python src/main.py
В GitHub Actions контекст передаётся через переменные окружения.
"""
from __future__ import annotations

import os
import sys
import json
import argparse

# Загрузка .env при локальном запуске
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def run_skeleton_tests(
    *,
    issue_number: int | None = None,
    test_llm: bool = True,
    test_github_read: bool = True,
    test_github_write: bool = False,
    branch_name: str | None = None,
) -> int:
    """
    Проверка «скелета»:
    - Тест Issues: прочитать Issue.
    - Тест API: запрос в LLM и вывод в консоль.
    - Тест записи: пустая ветка или комментарий в Issue.
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("GITHUB_REPOSITORY не задан. Пропуск тестов GitHub.", file=sys.stderr)
        test_github_read = False
        test_github_write = False

    # --- Тест чтения Issue ---
    if test_github_read and repo and issue_number:
        try:
            from github_client import GithubClient
            gh = GithubClient()
            details = gh.get_issue_details(issue_number)
            print("[GitHub] Прочитана Issue:", details.get("number"), details.get("title"))
            print("[GitHub] Body (первые 200 символов):", (details.get("body") or "")[:200])
        except Exception as e:
            print("[GitHub] Ошибка чтения Issue:", e, file=sys.stderr)
            return 1

    # --- Тест LLM ---
    if test_llm:
        try:
            from llm_client import LLMClient
            client = LLMClient()
            reply = client.generate_response(
                system_prompt="Ты помощник. Отвечай кратко.",
                user_prompt="Скажи одним словом: ок.",
            )
            print("[LLM] Ответ:", reply)
        except Exception as e:
            print("[LLM] Ошибка (возможно не заданы ключи):", e, file=sys.stderr)
            # Не падаем, если ключей нет — в CI могут не передать
            if os.environ.get("OPENAI_API_KEY") or os.environ.get("YANDEX_API_KEY") or os.environ.get("LLM_API_KEY"):
                return 1

    # --- Тест записи: ветка или комментарий ---
    if test_github_write and repo:
        try:
            from github_client import GithubClient
            gh = GithubClient()
            if branch_name:
                gh.create_branch(branch_name)
                print("[GitHub] Создана ветка:", branch_name)
            elif issue_number:
                gh.add_issue_comment(
                    issue_number,
                    "🤖 Агент: скелет запущен, проверка записи прошла успешно.",
                )
                print("[GitHub] Добавлен комментарий в Issue", issue_number)
        except Exception as e:
            print("[GitHub] Ошибка записи:", e, file=sys.stderr)
            return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Coding Agent — CLI")
    parser.add_argument("--issue", type=int, help="Номер Issue: запуск Code Agent (ветка → код → проверки → PR)")
    parser.add_argument("--pr", type=int, help="Номер PR: запуск AI Reviewer Agent (ревью и вердикт)")
    parser.add_argument("--skeleton", action="store_true", help="Режим скелета: только тесты чтения/LLM/записи")
    parser.add_argument("--no-llm", action="store_true", help="(скелет) Не вызывать LLM")
    parser.add_argument("--no-github-read", action="store_true", help="(скелет) Не читать Issue")
    parser.add_argument("--test-write", action="store_true", help="(скелет) Тест записи: комментарий в Issue или ветка")
    parser.add_argument("--branch", type=str, help="(скелет) Имя ветки для теста создания")
    args = parser.parse_args()

    # Контекст из аргументов или из GitHub Actions
    issue_number = args.issue
    pr_number = args.pr
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.isfile(event_path):
        try:
            with open(event_path, encoding="utf-8") as f:
                event = json.load(f)
            event_name = os.environ.get("GITHUB_EVENT_NAME", "")
            if "pull_request" in event_name and event.get("pull_request"):
                pr_number = pr_number or event["pull_request"].get("number")
            if "issues" in event_name and event.get("issue"):
                issue_number = issue_number or event["issue"].get("number")
            if not pr_number and not issue_number:
                issue_number = (event.get("issue") or event.get("pull_request", {})).get("number")
        except Exception:
            pass
    if pr_number is None:
        pr_number = int(os.environ.get("PR_NUMBER", "0")) or None
    if issue_number is None:
        issue_number = int(os.environ.get("ISSUE_NUMBER", "0")) or None

    # Code Agent Fix: правки по замечаниям Reviewer (триггер: review REQUEST_CHANGES)
    if pr_number and not args.skeleton and os.environ.get("FIX_MODE") == "1":
        try:
            from code_agent import run_code_agent_fix
            return run_code_agent_fix(pr_number)
        except Exception as e:
            print(f"[main] Ошибка Code Agent Fix: {e}", file=sys.stderr)
            return 1

    # AI Reviewer Agent: по событию PR (opened/synchronize)
    if pr_number and not args.skeleton:
        try:
            from reviewer_agent import run_reviewer_agent
            return run_reviewer_agent(pr_number)
        except Exception as e:
            print(f"[main] Ошибка Reviewer Agent: {e}", file=sys.stderr)
            return 1

    # Code Agent: по событию Issue (полный цикл по Issue)
    if issue_number and not args.skeleton:
        try:
            from code_agent import run_code_agent
            return run_code_agent(issue_number)
        except Exception as e:
            print(f"[main] Ошибка Code Agent: {e}", file=sys.stderr)
            return 1

    # Скелет: тесты
    return run_skeleton_tests(
        issue_number=issue_number,
        test_llm=not args.no_llm,
        test_github_read=not args.no_github_read,
        test_github_write=args.test_write,
        branch_name=args.branch,
    )


if __name__ == "__main__":
    sys.exit(main())
