"""
Клиент для работы с GitHub API.
Цель: получать задачи (Issues), создавать ветки и Pull Request, ревью PR.
"""
from __future__ import annotations

import os
import re
import requests
from github import Github


class GithubClient:
    """Обёртка над PyGithub для работы с репозиторием."""

    def __init__(self, token: str | None = None, repo_name: str | None = None):
        self._token = token or os.environ.get("GITHUB_TOKEN")
        if not self._token:
            raise ValueError("GITHUB_TOKEN не задан (аргумент или переменная окружения)")
        self._repo_name = repo_name or os.environ.get("GITHUB_REPOSITORY")
        if not self._repo_name:
            raise ValueError("GITHUB_REPOSITORY не задан (owner/repo)")
        self._gh = Github(self._token)
        self._repo = self._gh.get_repo(self._repo_name)

    def get_issue_details(self, issue_number: int) -> dict:
        """
        Получить текст задачи (Issue).
        :return: dict с ключами title, body, state, number.
        """
        issue = self._repo.get_issue(issue_number)
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
        }

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> None:
        """
        Создать ветку от указанной (или от default branch).
        :param branch_name: имя новой ветки (без refs/heads/).
        :param from_branch: от какой ветки (например main). Если None — default branch репо.
        """
        base = from_branch or self._repo.default_branch
        ref = self._repo.get_git_ref(f"heads/{base}")
        sha = ref.object.sha
        self._repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=sha)

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
    ) -> dict:
        """
        Создать Pull Request.
        :param head: ветка с изменениями.
        :param base: целевая ветка (по умолчанию default branch).
        :return: dict с number, url, state.
        """
        base_branch = base or self._repo.default_branch
        pr = self._repo.create_pull(title=title, body=body, head=head, base=base_branch)
        return {
            "number": pr.number,
            "url": pr.html_url,
            "state": pr.state,
        }

    def add_issue_comment(self, issue_number: int, body: str) -> None:
        """Оставить комментарий в Issue (для теста записи)."""
        issue = self._repo.get_issue(issue_number)
        issue.create_comment(body)

    def get_file_content(self, path: str, ref: str | None = None) -> str:
        """Получить содержимое файла из репозитория (ref — ветка или sha, по умолчанию default branch)."""
        ref = ref or self._repo.default_branch
        fc = self._repo.get_contents(path, ref=ref)
        if fc.content:
            import base64
            return base64.b64decode(fc.content).decode("utf-8", errors="replace")
        return ""

    def list_repo_files(self, path: str = "", ref: str | None = None, max_depth: int = 4) -> list[str]:
        """
        Список путей файлов в репозитории (рекурсивно, с ограничением глубины).
        Игнорирует .git и прочие служебные папки.
        """
        ref = ref or self._repo.default_branch
        result: list[str] = []

        def walk(p: str, depth: int) -> None:
            if depth <= 0:
                return
            try:
                contents = self._repo.get_contents(p, ref=ref)
            except Exception:
                return
            for item in contents:
                if item.path.startswith(".git") or "/.git" in item.path:
                    continue
                if item.type == "dir":
                    walk(item.path, depth - 1)
                else:
                    result.append(item.path)
            return None

        walk(path or "", max_depth)
        return sorted(result)

    def get_pr_for_issue(self, issue_number: int) -> dict | None:
        """Найти открытый PR, в теле которого есть «Closes #N» или «Fixes #N» для данного Issue. Возвращает {number, head_ref, body} или None."""
        issue = self._repo.get_issue(issue_number)
        for pr in issue.get_pulls(state="open"):
            body = pr.body or ""
            if f"#{issue_number}" in body or f"Closes #{issue_number}" in body:
                return {"number": pr.number, "head_ref": pr.head.ref, "body": body}
        return None

    def get_pr_comments(self, pr_number: int) -> list[dict]:
        """Комментарии к PR (включая review comments). Возвращает список {body, user, created_at}."""
        pr = self._repo.get_pull(pr_number)
        out: list[dict] = []
        for c in pr.get_comments():
            out.append({"body": c.body or "", "user": getattr(c.user, "login", ""), "created_at": str(c.created_at)})
        for c in pr.get_review_comments():
            out.append({"body": c.body or "", "user": getattr(c.user, "login", ""), "created_at": str(c.created_at)})
        out.sort(key=lambda x: x["created_at"])
        return out

    # --- PR Context и Review (для AI Reviewer Agent) ---

    def get_pr_details(self, pr_number: int) -> dict:
        """Детали PR: title, body, head_sha, head_ref, base_ref."""
        pr = self._repo.get_pull(pr_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "head_sha": pr.head.sha,
            "head_ref": pr.head.ref,
            "base_ref": pr.base.ref,
        }

    def get_pr_diff(self, pr_number: int) -> str:
        """Полный diff PR (unified diff)."""
        owner, repo = self._repo.full_name.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        r = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github.v3.diff",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.text

    def get_pr_changed_files(self, pr_number: int) -> list[dict]:
        """Список изменённых файлов: path, status, patch (если есть)."""
        pr = self._repo.get_pull(pr_number)
        out = []
        for f in pr.get_files():
            out.append({
                "path": f.filename,
                "status": f.status,
                "patch": f.patch or "",
            })
        return out

    def parse_issue_number_from_pr(self, pr_number: int) -> int | None:
        """Извлечь номер Issue из тела/заголовка PR (Closes #N, Fixes #N или #N)."""
        pr = self._repo.get_pull(pr_number)
        text = (pr.body or "") + "\n" + (pr.title or "")
        # Closes #123, Fixes #123 или просто #123
        m = re.search(r"(?:Closes|Fixes)\s*#(\d+)", text, re.I) or re.search(r"#(\d+)", text)
        return int(m.group(1)) if m else None

    def create_pr_review(
        self,
        pr_number: int,
        event: str,
        body: str,
        comments: list[dict] | None = None,
    ) -> dict:
        """
        Создать ревью PR: APPROVE, REQUEST_CHANGES или COMMENT.
        comments: список {path, line, body} или {path, line, side, body} для inline-комментариев.
        """
        pr = self._repo.get_pull(pr_number)
        review_comments = []
        if comments:
            for c in comments:
                path = c.get("path", "")
                line = c.get("line") or c.get("line_number")
                comment_body = c.get("body", "")
                if path and line is not None and comment_body:
                    review_comments.append({
                        "path": path,
                        "line": int(line),
                        "body": comment_body,
                    })
        review = pr.create_review(body=body, event=event, comments=review_comments)
        return {"id": review.id, "state": review.state}

    def get_workflow_runs_for_head(self, head_sha: str, limit: int = 10) -> list[dict]:
        """Список последних workflow runs для коммита head_sha. Возвращает conclusion и имя job'ов."""
        owner, repo = self._repo.full_name.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
        r = requests.get(
            url,
            params={"per_page": limit},
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        runs = data.get("workflow_runs", [])
        result = []
        for run in runs:
            if run.get("head_sha") != head_sha:
                continue
            run_name = run.get("name", "?")
            conclusion = run.get("conclusion") or run.get("status")
            result.append({"name": run_name, "conclusion": conclusion, "html_url": run.get("html_url", "")})
            if len(result) >= 5:
                break
        return result

    def get_review_count_by_user(self, pr_number: int, login: str) -> int:
        """Количество ревью от пользователя login по данному PR (для лимита итераций)."""
        pr = self._repo.get_pull(pr_number)
        count = 0
        for r in pr.get_reviews():
            if getattr(r.user, "login", None) == login:
                count += 1
        return count

    def get_current_user_login(self) -> str:
        """Логин пользователя, от имени которого выполняется запрос (для подсчёта ревью)."""
        return self._gh.get_user().login

    def get_pr_reviews(self, pr_number: int) -> list[dict]:
        """Список ревью PR: body, user, state (APPROVED, CHANGES_REQUESTED, COMMENTED)."""
        pr = self._repo.get_pull(pr_number)
        out = []
        for r in pr.get_reviews():
            out.append({
                "id": r.id,
                "body": r.body or "",
                "user": getattr(r.user, "login", ""),
                "state": r.state,
            })
        out.sort(key=lambda x: (x["user"], x["id"]))
        return out

    def get_pr_body(self, pr_number: int) -> str:
        """Текущее тело PR (для чтения/обновления метаданных итерации)."""
        pr = self._repo.get_pull(pr_number)
        return pr.body or ""

    def update_pr_body(self, pr_number: int, new_body: str) -> None:
        """Обновить тело PR (для записи Iteration: N)."""
        pr = self._repo.get_pull(pr_number)
        pr.edit(body=new_body)

    def add_label_to_pr(self, pr_number: int, label: str) -> None:
        """Добавить метку к PR (создаётся при отсутствии)."""
        pr = self._repo.get_pull(pr_number)
        try:
            self._repo.get_label(label)
        except Exception:
            try:
                self._repo.create_label(label, "ededed", "Auto label")
            except Exception:
                pass
        pr.add_to_labels(label)

    def remove_label_from_pr(self, pr_number: int, label: str) -> None:
        """Снять метку с PR."""
        pr = self._repo.get_pull(pr_number)
        try:
            pr.remove_from_labels(label)
        except Exception:
            pass

    def add_pr_comment(self, pr_number: int, body: str) -> None:
        """Добавить обычный комментарий к PR (в обсуждение)."""
        pr = self._repo.get_pull(pr_number)
        pr.create_issue_comment(body)

    @property
    def repo(self):
        """Доступ к репозиторию PyGithub при необходимости."""
        return self._repo
