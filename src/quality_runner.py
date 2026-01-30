"""
Локальная проверка качества: ruff, black, mypy, pytest.
Возвращает успех/неуспех и лог для передачи в LLM при исправлении.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], cwd: str | Path) -> tuple[bool, str]:
    """Запустить команду, вернуть (успех, объединённый stdout+stderr)."""
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "Timeout 120s"
    except Exception as e:
        return False, str(e)


def run_quality_checks(repo_root: str | Path) -> tuple[bool, str]:
    """
    Запустить black (форматирование), ruff check, mypy и pytest.
    :return: (всё ли прошло, объединённый лог).
    """
    root = Path(repo_root)
    logs: list[str] = []

    # black — автоформатирование (чтобы не падать на стиле)
    ok, out = run_cmd([sys.executable, "-m", "black", "src", "tests"], root)
    logs.append("=== black ===\n" + out)

    # ruff check
    ok, out = run_cmd([sys.executable, "-m", "ruff", "check", "src", "tests", "--output-format=text"], root)
    logs.append("=== ruff check ===\n" + out)
    if not ok:
        logs.append("(ruff: ошибки)\n")
        return False, "\n".join(logs)

    # mypy (может быть отключён, если нет конфига)
    mypy_ok, mypy_out = run_cmd([sys.executable, "-m", "mypy", "src", "--no-error-summary"], root)
    logs.append("=== mypy ===\n" + mypy_out)
    if not mypy_ok:
        logs.append("(mypy: ошибки типов)\n")
        return False, "\n".join(logs)

    # pytest
    ok, out = run_cmd([sys.executable, "-m", "pytest", "tests", "-v", "--tb=short"], root)
    logs.append("=== pytest ===\n" + out)
    if not ok:
        return False, "\n".join(logs)

    return True, "\n".join(logs)
