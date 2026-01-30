"""
Сбор контекста Pull Request для AI Reviewer Agent.
Цель: diff, связанный Issue, список файлов, результаты CI (workflow runs).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_client import GithubClient


def get_pr_context(gh: "GithubClient", pr_number: int) -> dict:
    """
    Собрать контекст PR: diff, детали PR, связанный Issue, изменённые файлы, результаты CI.
    :return: dict с ключами pr, diff, issue, changed_files, ci_summary.
    """
    pr = gh.get_pr_details(pr_number)
    diff = gh.get_pr_diff(pr_number)
    changed_files = gh.get_pr_changed_files(pr_number)
    issue_number = gh.parse_issue_number_from_pr(pr_number)
    issue = None
    if issue_number:
        try:
            issue = gh.get_issue_details(issue_number)
        except Exception:
            pass
    ci_runs = gh.get_workflow_runs_for_head(pr["head_sha"])
    ci_summary = "\n".join(
        f"- {r['name']}: {r['conclusion']}" + (f" ({r['html_url']})" if r.get("html_url") else "")
        for r in ci_runs
    ) or "Нет данных о CI."

    return {
        "pr": pr,
        "diff": diff,
        "issue": issue,
        "changed_files": changed_files,
        "ci_summary": ci_summary,
        "ci_runs": ci_runs,
    }


def format_pr_context_for_llm(ctx: dict) -> str:
    """Текстовый контекст для промпта Reviewer LLM."""
    parts = [
        "## Pull Request",
        f"**#{ctx['pr']['number']}** {ctx['pr']['title']}",
        "",
        ctx["pr"]["body"] or "(нет описания)",
        "",
        "## Исходная задача (Issue)",
    ]
    if ctx.get("issue"):
        issue = ctx["issue"]
        parts.append(f"**#{issue['number']}** {issue['title']}")
        parts.append("")
        parts.append(issue.get("body") or "(нет описания)")
    else:
        parts.append("(Issue не найден по Closes #N в PR)")
    parts.extend([
        "",
        "## Изменённые файлы",
        "\n".join(f"- {f['path']} ({f['status']})" for f in ctx["changed_files"]),
        "",
        "## Результаты CI",
        ctx["ci_summary"],
        "",
        "## Diff (изменения в коде)",
        "```diff",
        ctx["diff"][:50000] + ("\n... (обрезано)" if len(ctx["diff"]) > 50000 else ""),
        "```",
    ])
    return "\n".join(parts)
