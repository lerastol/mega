"""
Парсинг Issue и сбор контекста репозитория для Code Agent.
Цель: извлечь текст задачи, структуру проекта, содержимое ключевых файлов и (при повторе) комментарии Reviewer Agent.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_client import GithubClient


# Расширения и пути, которые считаем «ключевыми» для контекста
KEY_EXTENSIONS = (".py", ".yaml", ".yml", ".toml", ".txt", ".md", ".json")
KEY_PREFIXES = ("src/", "config/", "tests/", ".")
MAX_FILE_SIZE = 32 * 1024  # не более 32 КБ на файл
MAX_TOTAL_CONTEXT = 80 * 1024  # ориентир на объём контекста (примерно)


def _is_key_file(path: str) -> bool:
    if not path or path.count("/") > 4:
        return False
    if any(path.startswith(p) for p in ("src/", "config/", "tests/")):
        return path.endswith(KEY_EXTENSIONS) or "/" not in path
    if path.startswith("."):
        return path in (".env.example", ".gitignore") or path.endswith(KEY_EXTENSIONS)
    return path in ("README.md", "requirements.txt", "pyproject.toml") or path.endswith(KEY_EXTENSIONS)


def get_issue_context(gh: "GithubClient", issue_number: int) -> dict:
    """
    Собрать контекст для агента: Issue, структура репо, ключевые файлы, комментарии Reviewer (если есть PR).
    :return: dict с ключами issue, file_list, files (path -> content), reviewer_feedback (str или None).
    """
    issue = gh.get_issue_details(issue_number)
    ref = os.environ.get("GITHUB_REF_NAME") or gh.repo.default_branch

    file_list = gh.list_repo_files("", ref=ref)
    key_paths = [p for p in file_list if _is_key_file(p)]

    files: dict[str, str] = {}
    total = 0
    for path in key_paths:
        if total >= MAX_TOTAL_CONTEXT:
            break
        try:
            content = gh.get_file_content(path, ref=ref)
            if len(content) > MAX_FILE_SIZE:
                content = content[:MAX_FILE_SIZE] + "\n... (обрезано)\n"
            files[path] = content
            total += len(content)
        except Exception:
            continue

    reviewer_feedback = None
    pr = gh.get_pr_for_issue(issue_number)
    if pr:
        reviewer_feedback = get_reviewer_feedback_from_pr(gh, pr["number"])

    return {
        "issue": issue,
        "file_list": file_list,
        "files": files,
        "reviewer_feedback": reviewer_feedback,
        "ref": ref,
    }


def get_reviewer_feedback_from_pr(gh: "GithubClient", pr_number: int) -> str | None:
    """
    Получить текст последнего ревью от AI Reviewer (CHANGES_REQUESTED или COMMENTED с нашим форматом).
    Отличаем от комментариев пользователя по формату отчёта (## ✅ / ## ❌) или по автору (бот).
    """
    reviews = gh.get_pr_reviews(pr_number)
    for r in reversed(reviews):
        if r.get("state") in ("CHANGES_REQUESTED", "COMMENTED") and r.get("body"):
            body = r["body"]
            if "## " in body or "✅" in body or "❌" in body or "Критические ошибки" in body:
                return f"[Reviewer, {r.get('state')}] {body}"
    return None


def get_issue_context_for_pr(gh: "GithubClient", pr_number: int) -> dict:
    """
    Контекст для Code Agent в режиме правок: Issue из PR, код из head-ветки PR, замечания Reviewer.
    """
    pr_details = gh.get_pr_details(pr_number)
    issue_number = gh.parse_issue_number_from_pr(pr_number)
    head_ref = pr_details["head_ref"]
    if not issue_number:
        issue_number = 0
        issue = {"number": 0, "title": pr_details["title"], "body": pr_details["body"], "state": "open"}
    else:
        issue = gh.get_issue_details(issue_number)
    file_list = gh.list_repo_files("", ref=head_ref)
    key_paths = [p for p in file_list if _is_key_file(p)]
    files = {}
    total = 0
    for path in key_paths:
        if total >= MAX_TOTAL_CONTEXT:
            break
        try:
            content = gh.get_file_content(path, ref=head_ref)
            if len(content) > MAX_FILE_SIZE:
                content = content[:MAX_FILE_SIZE] + "\n... (обрезано)\n"
            files[path] = content
            total += len(content)
        except Exception:
            continue
    reviewer_feedback = get_reviewer_feedback_from_pr(gh, pr_number)
    return {
        "issue": issue,
        "file_list": file_list,
        "files": files,
        "reviewer_feedback": reviewer_feedback,
        "ref": head_ref,
        "pr": pr_details,
    }


def format_context_for_llm(ctx: dict) -> str:
    """Сформировать текстовый контекст для промпта LLM."""
    issue = ctx["issue"]
    parts = [
        f"# Issue #{issue['number']}: {issue['title']}",
        "",
        issue["body"] or "(нет описания)",
        "",
        "## Структура репозитория (файлы)",
        "\n".join(ctx["file_list"][:150]),
        "",
        "## Содержимое ключевых файлов",
    ]
    for path, content in ctx["files"].items():
        parts.append(f"\n### {path}\n```\n{content}\n```")
    if ctx.get("reviewer_feedback"):
        parts.append("\n## Замечания Reviewer (нужно исправить)\n" + ctx["reviewer_feedback"])
    return "\n".join(parts)
