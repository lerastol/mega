"""
Управление состоянием цикла: счётчик итераций в метаданных PR.
Цель: предотвратить бесконечный цикл Code Agent ↔ Reviewer Agent.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from github_client import GithubClient

ITERATION_PATTERN = re.compile(r"<!--\s*iteration:\s*(\d+)\s*-->")


def get_iteration(gh: "GithubClient", pr_number: int) -> int:
    """
    Прочитать номер итерации из тела PR (тег <!-- iteration: N -->).
    :return: 0 если тег не найден.
    """
    body = gh.get_pr_body(pr_number)
    m = ITERATION_PATTERN.search(body)
    return int(m.group(1)) if m else 0


def set_iteration(gh: "GithubClient", pr_number: int, iteration: int) -> None:
    """
    Записать номер итерации в тело PR: добавить или заменить тег <!-- iteration: N -->.
    """
    body = gh.get_pr_body(pr_number)
    new_tag = f"<!-- iteration: {iteration} -->"
    if ITERATION_PATTERN.search(body):
        new_body = ITERATION_PATTERN.sub(new_tag, body, count=1)
    else:
        new_body = (body.rstrip() + "\n\n" + new_tag).strip()
    gh.update_pr_body(pr_number, new_body)
