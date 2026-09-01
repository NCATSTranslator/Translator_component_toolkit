"""Shared isolation for tests that use TCT's runtime configuration."""

from collections.abc import Iterator

import pytest

from TCT.config import reset_config


@pytest.fixture(autouse=True)
def isolated_runtime_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent ambient environment or earlier tests from selecting services."""
    monkeypatch.delenv("TCT_ENVIRONMENT", raising=False)
    reset_config()
    yield
    reset_config()
