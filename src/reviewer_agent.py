"""
AI Reviewer Agent: анализ PR, вердикт (APPROVE / REQUEST_CHANGES), публикация отчёта и комментариев.
"""
from __future__ import annotations

import os
import sys
import json
import re
from pathlib import Path

from github_client import GithubClient
from pr_context import get_pr_context, format_pr_context_for_llm
from prompts import REVIEWER_SYSTEM_PROMPT
from llm_client import LLMClient

MAX_REVIEW_ITERATIONS = int(os.environ.get("REVIEWER_MAX_ITERATIONS", "3"))


def _load_reviewer_prompt_file() -> str | None:
    """Загрузить промпт из prompts/reviewer_v1.txt при наличии."""
    for base in (Path(__file__).resolve().parent.parent, Path.cwd()):
        path = base / "prompts" / "reviewer_v1.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def _parse_review_response(text: str) -> dict:
    """Извлечь из ответа LLM verdict, summary, inline_comments."""
    text = text.strip()
    for start in ("```json", "```"):
        if text.startswith(start):
            text = text[len(start) :].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"verdict": "REQUEST_CHANGES", "summary": "Не удалось разобрать ответ Reviewer.", "inline_comments": []}
    verdict = (data.get("verdict") or "REQUEST_CHANGES").upper()
    if verdict not in ("APPROVE", "REQUEST_CHANGES"):
        verdict = "REQUEST_CHANGES"
    summary = data.get("summary") or "Нет текста отчёта."
    comments = data.get("inline_comments") or []
    out_comments = []
    for c in comments:
        if isinstance(c, dict) and c.get("path") and c.get("body"):
            line = c.get("line") or c.get("line_number")
            if line is not None:
                out_comments.append({"path": str(c["path"]), "line": int(line), "body": str(c["body"])[:1000]})
    return {"verdict": verdict, "summary": summary, "inline_comments": out_comments[:30]}


def run_reviewer_agent(pr_number: int) -> int:
    """
    Собрать контекст PR → вызвать LLM → разобрать вердикт → опубликовать ревью (APPROVE или REQUEST_CHANGES).
    :return: 0 при успехе, 1 при ошибке.
    """
    try:
        gh = GithubClient()
    except ValueError as e:
        print(f"[Reviewer] Ошибка GitHub: {e}", file=sys.stderr)
        return 1

    try:
        llm = LLMClient()
    except ValueError as e:
        print(f"[Reviewer] Ошибка LLM: {e}", file=sys.stderr)
        return 1

    # Лимит итераций: не более N ревью от этого бота по данному PR
    try:
        bot_login = os.environ.get("GITHUB_ACTOR") or gh.get_current_user_login()
    except Exception:
        bot_login = "github-actions"
    review_count = gh.get_review_count_by_user(pr_number, bot_login)
    if review_count >= MAX_REVIEW_ITERATIONS:
        print(f"[Reviewer] Достигнут лимит ревью ({MAX_REVIEW_ITERATIONS}), пропуск.", file=sys.stderr)
        return 0

    print(f"[Reviewer] PR #{pr_number}")
    ctx = get_pr_context(gh, pr_number)
    context_text = format_pr_context_for_llm(ctx)
    system_prompt = _load_reviewer_prompt_file() or REVIEWER_SYSTEM_PROMPT
    user_prompt = "Ниже контекст Pull Request (описание, Issue, изменённые файлы, CI, diff). Верни JSON: verdict (APPROVE или REQUEST_CHANGES), summary (Markdown), inline_comments (массив {path, line, body}).\n\n" + context_text

    try:
        response = llm.generate_response(system_prompt, user_prompt, as_json=False)
    except Exception as e:
        print(f"[Reviewer] Ошибка LLM: {e}", file=sys.stderr)
        return 1

    parsed = _parse_review_response(response)
    verdict = parsed["verdict"]
    summary = parsed["summary"]
    inline_comments = parsed["inline_comments"]

    # Логирование для GitHub Actions
    print(f"[Reviewer] Вердикт: {verdict}")
    print(f"[Reviewer] Summary (фрагмент): {summary[:500]}...")

    event = "APPROVE" if verdict == "APPROVE" else "REQUEST_CHANGES"
    try:
        review = gh.create_pr_review(pr_number, event=event, body=summary, comments=inline_comments)
        print(f"[Reviewer] Ревью опубликовано: {review.get('state')}")
    except Exception as e:
        print(f"[Reviewer] Ошибка публикации ревью: {e}", file=sys.stderr)
        return 1

    try:
        if verdict == "APPROVE":
            gh.add_label_to_pr(pr_number, "reviewed")
            gh.remove_label_from_pr(pr_number, "ai-thinking")
            gh.remove_label_from_pr(pr_number, "needs-fix")
        else:
            gh.add_label_to_pr(pr_number, "needs-fix")
    except Exception:
        pass

    return 0
