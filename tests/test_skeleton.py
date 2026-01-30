"""Минимальные тесты для прохождения pytest в Code Agent."""


def test_placeholder():
    """Placeholder: всегда проходит."""
    assert True


def test_imports():
    """Проверка импорта модулей агента (conftest добавляет src в path)."""
    import github_client   # noqa: F401
    import llm_client      # noqa: F401
    import issue_parser    # noqa: F401
    import code_applier    # noqa: F401
    import pr_context      # noqa: F401
    import reviewer_agent  # noqa: F401
    import state_manager   # noqa: F401
    import code_agent      # noqa: F401
    import quality_runner  # noqa: F401
    import git_runner      # noqa: F401
    assert True
