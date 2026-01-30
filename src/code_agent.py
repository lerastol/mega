"""
Code Agent: оркестрация цикла Issue → контекст → LLM → применение кода → проверки → коммит → PR.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from github_client import GithubClient
from issue_parser import get_issue_context, get_issue_context_for_pr, format_context_for_llm
from prompts import SYSTEM_PROMPT, FIX_PROMPT, build_user_prompt
from llm_client import LLMClient
from code_applier import parse_llm_files_response, apply_changes
from quality_runner import run_quality_checks
from git_runner import ensure_branch, checkout_remote_branch, commit_and_push, get_default_branch
from state_manager import get_iteration, set_iteration


MAX_ITERATIONS = int(os.environ.get("CODE_AGENT_MAX_ITERATIONS", "5"))
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_code_agent(issue_number: int) -> int:
    """
    Полный цикл: парсинг Issue → генерация кода → применение → проверки (с retry) → ветка → коммит → push → PR.
    :return: 0 при успехе, 1 при ошибке.
    """
    try:
        gh = GithubClient()
    except ValueError as e:
        print(f"[Code Agent] Ошибка инициализации GitHub: {e}", file=sys.stderr)
        return 1

    try:
        llm = LLMClient()
    except ValueError as e:
        print(f"[Code Agent] Ошибка инициализации LLM: {e}", file=sys.stderr)
        return 1

    print(f"[Code Agent] Issue #{issue_number}")
    ctx = get_issue_context(gh, issue_number)
    issue = ctx["issue"]
    branch_name = f"fix/issue-{issue_number}"
    base_branch = get_default_branch(REPO_ROOT)

    # Создать и переключиться на ветку (если ещё не на ней)
    if not ensure_branch(REPO_ROOT, branch_name, from_branch=base_branch):
        print("[Code Agent] Не удалось создать/переключить ветку.", file=sys.stderr)
        return 1
    print(f"[Code Agent] Ветка: {branch_name}")

    reviewer_feedback = ctx.get("reviewer_feedback")
    context_text = format_context_for_llm(ctx)
    user_prompt = build_user_prompt(context_text, reviewer_feedback)

    for iteration in range(MAX_ITERATIONS):
        print(f"[Code Agent] Итерация {iteration + 1}/{MAX_ITERATIONS}")
        try:
            response = llm.generate_response(SYSTEM_PROMPT, user_prompt, as_json=False)
        except Exception as e:
            print(f"[Code Agent] Ошибка LLM: {e}", file=sys.stderr)
            return 1

        files = parse_llm_files_response(response)
        if not files:
            print("[Code Agent] LLM не вернул список файлов (ожидается JSON с полем files).", file=sys.stderr)
            if iteration < MAX_ITERATIONS - 1:
                user_prompt = user_prompt + "\n\nОтвет должен быть только JSON: {\"files\": [{\"path\": \"...\", \"content\": \"...\"}]}. Повтори."
                continue
            return 1

        written = apply_changes(files, REPO_ROOT)
        print(f"[Code Agent] Записано файлов: {len(written)}")

        ok, log = run_quality_checks(REPO_ROOT)
        if ok:
            break
        print("[Code Agent] Проверки не прошли, отправляю лог в LLM для исправления.")
        user_prompt = user_prompt + "\n\n--- Результат проверок (нужно исправить код) ---\n" + log
        if iteration == MAX_ITERATIONS - 1:
            print("[Code Agent] Достигнут лимит итераций, коммит с текущим состоянием.", file=sys.stderr)

    if not written:
        print("[Code Agent] Нет изменений для коммита.", file=sys.stderr)
        return 1

    # Коммит и push
    commit_message = f"fix: {issue['title']}\n\nCloses #{issue_number}"
    ok, out = commit_and_push(REPO_ROOT, branch_name, commit_message, paths=written)
    if not ok:
        print(f"[Code Agent] Ошибка коммита/push: {out}", file=sys.stderr)
        return 1
    print("[Code Agent] Коммит и push выполнены.")

    # PR
    pr_body = f"Closes #{issue_number}\n\n## Изменения\n- {chr(10).join('- ' + p for p in written)}\n\n## Локальные проверки\nruff, black, mypy, pytest выполнены."
    try:
        pr = gh.create_pull_request(
            title=f"fix: {issue['title']} (Closes #{issue_number})",
            body=pr_body,
            head=branch_name,
            base=base_branch,
        )
        print(f"[Code Agent] Pull Request создан: {pr.get('url')}")
        try:
            gh.add_label_to_pr(pr["number"], "ai-thinking")
        except Exception:
            pass
    except Exception as e:
        # PR уже может существовать (повторный запуск)
        pr = gh.get_pr_for_issue(issue_number)
        if pr:
            try:
                gh.add_label_to_pr(pr["number"], "ai-thinking")
            except Exception:
                pass
        print(f"[Code Agent] PR: {e}")
    return 0


def run_code_agent_fix(pr_number: int) -> int:
    """
    Режим правок по замечаниям Reviewer: checkout head-ветки PR → контекст с Reviewer → правки → коммит → push.
    Лимит итераций и детектор стагнации прерывают цикл.
    :return: 0 при успехе или при остановке по лимиту/стагнации, 1 при ошибке.
    """
    try:
        gh = GithubClient()
    except ValueError as e:
        print(f"[Code Agent Fix] Ошибка GitHub: {e}", file=sys.stderr)
        return 1

    try:
        llm = LLMClient()
    except ValueError as e:
        print(f"[Code Agent Fix] Ошибка LLM: {e}", file=sys.stderr)
        return 1

    current_iteration = get_iteration(gh, pr_number)
    if current_iteration >= MAX_ITERATIONS:
        msg = "Достигнут лимит итераций. Требуется вмешательство человека."
        print(f"[Code Agent Fix] {msg}", file=sys.stderr)
        gh.add_pr_comment(pr_number, f"🤖 **Code Agent:** {msg}")
        try:
            gh.add_label_to_pr(pr_number, "error")
        except Exception:
            pass
        return 0

    try:
        gh.add_label_to_pr(pr_number, "ai-thinking")
    except Exception:
        pass

    pr_details = gh.get_pr_details(pr_number)
    head_ref = pr_details["head_ref"]
    if not checkout_remote_branch(REPO_ROOT, head_ref):
        print(f"[Code Agent Fix] Не удалось переключиться на ветку {head_ref}", file=sys.stderr)
        return 1
    print(f"[Code Agent Fix] Ветка: {head_ref}")

    ctx = get_issue_context_for_pr(gh, pr_number)
    context_text = format_context_for_llm(ctx)
    user_prompt = (
        "Ниже контекст: Issue, код из ветки PR, замечания Reviewer. "
        "Внеси только правки по замечаниям. Верни JSON {\"files\": [{\"path\": \"...\", \"content\": \"...\"}]}.\n\n"
        + context_text
    )

    try:
        response = llm.generate_response(FIX_PROMPT, user_prompt, as_json=False)
    except Exception as e:
        print(f"[Code Agent Fix] Ошибка LLM: {e}", file=sys.stderr)
        return 1

    files = parse_llm_files_response(response)
    if not files:
        gh.add_pr_comment(pr_number, "🤖 **Code Agent:** Детектор стагнации — LLM не вернул изменения. Цикл прерван.")
        return 0

    written = apply_changes(files, REPO_ROOT)
    if not written:
        gh.add_pr_comment(pr_number, "🤖 **Code Agent:** Детектор стагнации — код не изменился после правок. Цикл прерван.")
        try:
            gh.add_label_to_pr(pr_number, "error")
        except Exception:
            pass
        return 0

    print(f"[Code Agent Fix] Записано файлов: {len(written)}")
    ok, log = run_quality_checks(REPO_ROOT)
    if not ok:
        user_prompt = user_prompt + "\n\n--- Результат проверок (исправь код) ---\n" + log
        try:
            response2 = llm.generate_response(FIX_PROMPT, user_prompt, as_json=False)
            files2 = parse_llm_files_response(response2)
            if files2:
                written = apply_changes(files2, REPO_ROOT)
                ok, _ = run_quality_checks(REPO_ROOT)
        except Exception:
            pass

    commit_message = f"fix: правки по замечаниям ревью (итерация {current_iteration + 1})"
    ok_push, out = commit_and_push(REPO_ROOT, head_ref, commit_message, paths=written)
    if not ok_push:
        print(f"[Code Agent Fix] Ошибка push: {out}", file=sys.stderr)
        return 1
    set_iteration(gh, pr_number, current_iteration + 1)
    try:
        gh.remove_label_from_pr(pr_number, "ai-thinking")
    except Exception:
        pass
    print("[Code Agent Fix] Правки запушены.")
    return 0
