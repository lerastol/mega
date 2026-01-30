"""
Создание репозитория на GitHub и добавление секрета OPENAI_API_KEY.
Читает GITHUB_TOKEN и OPENAI_API_KEY из .env в корне проекта.
Запуск: из корня проекта: python scripts/setup_github_repo.py
"""
from __future__ import annotations

import os
import sys
import base64
from pathlib import Path

# Корень проекта = родитель папки scripts
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# Загрузка .env
from dotenv import load_dotenv
load_dotenv(str(ROOT / ".env"), override=True)

import requests
from github import Github


REPO_NAME = "mega"
GITHUB_API = "https://api.github.com"


def get_public_key(owner: str, repo: str, token: str) -> tuple[str, str]:
    """Получить public key репозитория для шифрования секрета."""
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/secrets/public-key",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["key_id"], data["key"]


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Шифрование секрета для GitHub Actions (LibSodium sealed box)."""
    from nacl.public import PublicKey, SealedBox
    from nacl.encoding import Base64Encoder

    public_key = PublicKey(public_key_b64.encode("utf-8"), Base64Encoder)
    box = SealedBox(public_key)
    encrypted = box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def set_repo_secret(owner: str, repo: str, token: str, secret_name: str, secret_value: str) -> None:
    """Создать или обновить секрет репозитория."""
    key_id, key_b64 = get_public_key(owner, repo, token)
    encrypted = encrypt_secret(key_b64, secret_value)
    r = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/secrets/{secret_name}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"encrypted_value": encrypted, "key_id": key_id},
        timeout=30,
    )
    r.raise_for_status()
    print(f"  Секрет {secret_name} добавлен в репозиторий.")


def update_env_repository(owner: str, repo: str) -> None:
    """Обновить GITHUB_REPOSITORY в .env."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8")
    new_repo = f"{owner}/{repo}"
    if "GITHUB_REPOSITORY=" in text:
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("GITHUB_REPOSITORY="):
                lines.append(f"GITHUB_REPOSITORY={new_repo}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  В .env записан GITHUB_REPOSITORY={new_repo}")
    else:
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nGITHUB_REPOSITORY={new_repo}\n")
        print(f"  В .env добавлен GITHUB_REPOSITORY={new_repo}")


def _load_env_from_file() -> None:
    """Подгрузить .env вручную, если dotenv не подхватил переменные."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and val:
                        os.environ[key] = val
    except Exception:
        pass


def main() -> int:
    _load_env_from_file()
    token = os.environ.get("GITHUB_TOKEN")
    if not token or token.startswith("ghp_xxx"):
        print("Задайте в .env реальный GITHUB_TOKEN (Personal Access Token с правами repo).", file=sys.stderr)
        return 1

    yandex_key = os.environ.get("YANDEX_API_KEY")
    yandex_folder = os.environ.get("YANDEX_FOLDER_ID")
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    has_yandex = yandex_key and yandex_folder and len(yandex_key) > 10
    has_openai = openai_key and not openai_key.startswith("sk-xxx") and len(openai_key) >= 20

    if not has_yandex and not has_openai:
        print(
            "Задайте в .env ключи LLM: либо YANDEX_API_KEY и YANDEX_FOLDER_ID (Yandex GPT), "
            "либо OPENAI_API_KEY (OpenAI).", file=sys.stderr
        )
        return 1

    gh = Github(token)
    user = gh.get_user()
    owner = user.login
    print(f"Пользователь GitHub: {owner}")

    try:
        repo = user.get_repo(REPO_NAME)
        print(f"Репозиторий {owner}/{REPO_NAME} уже существует.")
    except Exception:
        repo = user.create_repo(
            REPO_NAME,
            description="Coding Agents — Мегашкола",
            private=False,
            has_issues=True,
            has_wiki=False,
            auto_init=False,
        )
        print(f"Создан репозиторий: {repo.html_url}")

    if has_yandex:
        set_repo_secret(owner, REPO_NAME, token, "YANDEX_API_KEY", yandex_key)
        set_repo_secret(owner, REPO_NAME, token, "YANDEX_FOLDER_ID", yandex_folder)
    if has_openai:
        set_repo_secret(owner, REPO_NAME, token, "OPENAI_API_KEY", openai_key)
    update_env_repository(owner, REPO_NAME)
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
