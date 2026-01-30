"""Скрипт: вывести список Issues и PR репозитория для заполнения REPORT.md."""
from __future__ import annotations

import os
import sys

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Добавить src в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def main() -> None:
    repo_name = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not repo_name:
        print("GITHUB_TOKEN и GITHUB_REPOSITORY должны быть заданы в .env", file=sys.stderr)
        sys.exit(1)

    from github import Github
    gh = Github(token)
    repo = gh.get_repo(repo_name)

    print("=== Issues (open + closed, последние 20) ===")
    for i, issue in enumerate(repo.get_issues(state="all", sort="updated", direction="desc")):
        if i >= 20:
            break
        # Issues — это и issues, и PR в API; у PR есть pull_request
        if issue.pull_request:
            continue
        print(f"  #{issue.number} | {issue.state} | {issue.title[:60]}")

    print("\n=== Pull Requests (open + closed, последние 20) ===")
    for i, pr in enumerate(repo.get_pulls(state="all", sort="updated", direction="desc")):
        if i >= 20:
            break
        body = pr.body or ""
        closes = "#" in body and "Closes" in body
        print(f"  #{pr.number} | {pr.state} | head={pr.head.ref} | {pr.title[:50]} | Closes in body: {closes}")

    # Связки Issue -> PR (по ветке fix/issue-N или по "Closes #N" в теле PR)
    print("\n=== Связки Issue -> PR (по ветке fix/issue-*) ===")
    import re
    for pr in repo.get_pulls(state="all", sort="updated", direction="desc"):
        m = re.match(r"fix/issue-(\d+)", pr.head.ref)
        if m:
            issue_num = m.group(1)
            print(f"  Issue #{issue_num} -> PR #{pr.number} | {pr.state} | {pr.title[:50]}")

if __name__ == "__main__":
    main()
