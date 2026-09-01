import pytest

from TCT.config import (
    RuntimeConfig,
    configure,
    get_runtime_config,
    load_config,
    reset_config,
)
from TCT.translator_kpinfo import _select_provider_url


@pytest.fixture(autouse=True)
def clean_runtime_config():
    reset_config()
    yield
    reset_config()


def test_prod_and_ci_endpoint_resolution():
    prod = RuntimeConfig(environment="prod")
    ci = RuntimeConfig(environment="ci")

    assert prod.service_url("arax") == (
        "https://arax.transltr.io/api/arax/v1.4/query"
    )
    assert ci.service_url("arax") == (
        "https://arax.ci.transltr.io/api/arax/v1.4/query"
    )


def test_ci_uses_common_endpoint_when_no_distinction_exists():
    config = RuntimeConfig(environment="ci")

    assert config.service_url("node_normalizer") == "https://nodenorm.transltr.io/"


def test_explicit_override_wins():
    config = RuntimeConfig(
        environment="ci",
        overrides={"arax": "http://localhost:8080/query"},
    )

    assert config.service_url("arax") == "http://localhost:8080/query"


def test_environment_variable_selects_ci(monkeypatch):
    monkeypatch.setenv("TCT_ENVIRONMENT", "ci")

    assert load_config().environment == "ci"


def test_configure_sets_process_configuration():
    configured = configure(environment="ci")

    assert configured.environment == "ci"
    assert get_runtime_config() is configured


def test_provider_selection_changes_only_when_ci_is_available():
    prod = "https://provider.example/query"
    ci = "https://provider.ci.example/query"

    assert _select_provider_url(prod, ci, "prod") == prod
    assert _select_provider_url(prod, ci, "ci") == ci
    assert _select_provider_url(prod, None, "ci") == prod


def test_invalid_environment_and_override_are_rejected():
    with pytest.raises(ValueError, match="environment"):
        RuntimeConfig(environment="test")
    with pytest.raises(ValueError, match="unknown service"):
        RuntimeConfig(overrides={"missing": "https://example.org"})
