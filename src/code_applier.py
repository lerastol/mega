"""
Применение изменений кода от LLM к файловой системе.
Читает JSON с полями path и content, создаёт/перезаписывает файлы.
"""
from __future__ import annotations

import os
import json
from pathlib import Path


def parse_llm_files_response(text: str) -> list[dict]:
    """
    Извлечь из ответа LLM список {path, content}.
    Допускает обёртку в ```json ... ``` и мелкие артефакты.
    """
    text = text.strip()
    for start in ("```json", "```"):
        if text.startswith(start):
            text = text[len(start) :].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    files = data.get("files")
    if not isinstance(files, list):
        return []
    out = []
    for item in files:
        if isinstance(item, dict) and "path" in item and "content" in item:
            path = item.get("path")
            content = item.get("content")
            if path and isinstance(path, str):
                out.append({"path": path.strip(), "content": content if isinstance(content, str) else ""})
    return out


def apply_changes(files: list[dict], repo_root: str | Path) -> list[str]:
    """
    Записать файлы в репозиторий. Создаёт директории при необходимости.
    :return: список записанных путей (относительно repo_root).
    """
    root = Path(repo_root)
    written: list[str] = []
    for item in files:
        path = item.get("path", "").strip()
        content = item.get("content", "")
        if not path or ".." in path or path.startswith("/"):
            continue
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        written.append(path)
    return written
