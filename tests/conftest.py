"""Shared isolation for tests that use TCT's runtime configuration."""

from collections.abc import Iterator

import pytest

from TCT.config import configure, reset_config


@pytest.fixture(autouse=True)
def isolated_runtime_config() -> Iterator[None]:
    """Give every test an explicit runtime independent of ambient state."""
    configure(environment="prod")
    yield
    reset_config()
