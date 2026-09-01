import pytest

from TCT.config import (
    RuntimeConfig,
    configure,
    get_runtime_config,
    load_config,
)
from TCT.translator_kpinfo import _select_provider_url

def test_prod_ci_and_test_endpoint_resolution():
    prod = RuntimeConfig(environment="prod")
    ci = RuntimeConfig(environment="ci")
    test = RuntimeConfig(environment="test")

    assert prod.service_url("arax") == "https://arax.transltr.io/api/arax/v1.4/query"
    assert ci.service_url("arax") == "https://shepherd.ci.transltr.io/arax/query"
    assert test.service_url("arax") == "https://shepherd.test.transltr.io/arax/query"


def test_environment_specific_and_fallback_endpoint_resolution():
    ci = RuntimeConfig(environment="ci")
    test = RuntimeConfig(environment="test")

    assert ci.service_url("node_normalizer") == "https://nodenorm.ci.transltr.io/"
    assert test.service_url("node_normalizer") == "https://nodenorm.transltr.io/"


def test_explicit_override_wins():
    config = RuntimeConfig(
        environment="ci",
        overrides={"arax": "http://localhost:8080/query"},
    )

    assert config.service_url("arax") == "http://localhost:8080/query"


def test_environment_variable_selects_ci(monkeypatch):
    monkeypatch.setenv("TCT_ENVIRONMENT", "ci")

    assert load_config().environment == "ci"


def test_suite_does_not_inherit_runtime_environment():
    assert get_runtime_config().environment == "prod"


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
        RuntimeConfig(environment="dev")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown service"):
        RuntimeConfig(overrides={"missing": "https://example.org"})
