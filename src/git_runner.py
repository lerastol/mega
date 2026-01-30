"""
Git: создание ветки, коммит, push. Для использования в Code Agent.
В GitHub Actions репозиторий уже клонирован; локально предполагается работа из корня репо.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> tuple[bool, str]:
    """Выполнить git команду."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (r.stdout or "").strip() + "\n" + (r.stderr or "").strip()
        return r.returncode == 0, out
    except Exception as e:
        return False, str(e)


def ensure_branch(repo_root: Path, branch_name: str, from_branch: str = "main") -> bool:
    """Создать ветку (если не существует) и переключиться на неё."""
    ok, _ = run_git(["rev-parse", "--verify", branch_name], repo_root)
    if ok:
        run_git(["checkout", branch_name], repo_root)
        return True
    ok, _ = run_git(["checkout", "-b", branch_name, from_branch], repo_root)
    return ok


def checkout_remote_branch(repo_root: Path, branch_name: str) -> bool:
    """Подтянуть и переключиться на удалённую ветку (для режима правок по PR)."""
    run_git(["fetch", "origin", branch_name], repo_root)
    ok, _ = run_git(["checkout", branch_name], repo_root)
    return ok


def set_remote_push_url(repo_root: Path, token: str, repo_slug: str) -> None:
    """Настроить origin для push по HTTPS с токеном (для GitHub Actions)."""
    url = f"https://x-access-token:{token}@github.com/{repo_slug}.git"
    run_git(["remote", "set-url", "origin", url], repo_root)


def _ensure_git_user(repo_root: Path) -> None:
    """Установить user.name и user.email для коммита (в т.ч. в GitHub Actions)."""
    run_git(["config", "user.name", os.environ.get("GIT_USER_NAME", "github-actions[bot]")], repo_root)
    run_git(["config", "user.email", os.environ.get("GIT_USER_EMAIL", "github-actions[bot]@users.noreply.github.com")], repo_root)


def commit_and_push(
    repo_root: Path,
    branch_name: str,
    message: str,
    paths: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Добавить файлы, коммит, push.
    :param paths: список путей для add; если None — add -A.
    """
    _ensure_git_user(repo_root)
    token = os.environ.get("GITHUB_TOKEN")
    repo_slug = os.environ.get("GITHUB_REPOSITORY")
    if token and repo_slug:
        set_remote_push_url(repo_root, token, repo_slug)
    if paths:
        for p in paths:
            run_git(["add", p], repo_root)
    else:
        run_git(["add", "-A"], repo_root)
    ok, out = run_git(["status", "--short"], repo_root)
    if not out.strip():
        return True, "(нет изменений)"
    ok, out1 = run_git(["commit", "-m", message], repo_root)
    if not ok:
        return False, out1
    ok, out2 = run_git(["push", "-u", "origin", branch_name], repo_root)
    return ok, out2


def get_current_branch(repo_root: Path) -> str:
    """Текущая ветка."""
    ok, out = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    return out.strip() if ok else ""


def get_default_branch(repo_root: Path) -> str:
    """Default branch (main/master)."""
    ok, out = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], repo_root)
    if ok and out.strip():
        # refs/remotes/origin/main -> main
        return out.strip().replace("refs/remotes/origin/", "")
    return "main"
