"""Small runtime configuration surface for Translator service URLs."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Literal, Mapping


Environment = Literal["prod", "ci", "test"]


@dataclass(frozen=True)
class ServiceEndpoint:
    """Production endpoint with an optional CI deployment."""

    prod: str
    ci: str | None = None
    test: str | None = None

    def resolve(self, environment: Environment) -> str:
        if environment == "ci" and self.ci is not None:
            return self.ci
        elif environment == "test" and self.test is not None:
            return self.test
        return self.prod


SERVICE_ENDPOINTS: dict[str, ServiceEndpoint] = {
    "name_resolver": ServiceEndpoint(
        prod="https://name-lookup.transltr.io/",
        ci="https://name-lookup.ci.transltr.io/",
    ),
    "node_normalizer": ServiceEndpoint(
        prod="https://nodenorm.transltr.io/",
        ci="https://nodenorm.ci.transltr.io/",
    ),
    "node_annotator": ServiceEndpoint(
        prod="https://annotator.transltr.io/",
        ci="https://annotator.ci.transltr.io/",
        test="https://annotator.test.transltr.io/",
    ),
    "smartapi_registry": ServiceEndpoint(
        prod="https://smart-api.info/api/query?q=tags.name:translator AND tags.name:trapi&size=1000&sort=_seq_no&raw=1&fields=paths,servers,tags,components.x-bte*,info,_meta",
    ),
    "smartapi_catalog": ServiceEndpoint(
        prod="https://smart-api.info/api/query?q=tags.name:translator&fields=info,_meta,tags&meta=1&size=500",
        ci="https://dev.smart-api.info/api/query?q=tags.name:translator&fields=info,_meta,tags&meta=1&size=500",
    ),
    "arax": ServiceEndpoint(
        # ARAX should only be accessed through Shepherd
        prod="https://arax.transltr.io/api/arax/v1.4/query",
        ci="https://shepherd.ci.transltr.io/arax/query",
        test="https://shepherd.test.transltr.io/arax/query",
    ),
    "aragorn": ServiceEndpoint(
        prod="https://shepherd.prod.transltr.io/aragorn/query",
        ci="https://shepherd.ci.transltr.io/aragorn/query",
        test="https://shepherd.test.transltr.io/aragorn/query",
    ),
}


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime environment and explicit service URL replacements."""

    environment: Environment = "prod"
    overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.environment not in ("prod", "ci", "test"):
            raise ValueError("environment must be 'prod', 'ci', or 'test'")
        unknown = set(self.overrides) - set(SERVICE_ENDPOINTS)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown service override(s): {names}")

    def service_url(self, service: str) -> str:
        """Resolve a known service URL for this configuration."""
        if service not in SERVICE_ENDPOINTS:
            raise KeyError(f"unknown service: {service}")
        return self.overrides.get(
            service,
            SERVICE_ENDPOINTS[service].resolve(self.environment),
        )


_configured_runtime: RuntimeConfig | None = None


def load_config(
    environment: Environment | None = None,
    overrides: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    """Build configuration from explicit values and ``TCT_ENVIRONMENT``."""
    selected_environment = environment or os.getenv("TCT_ENVIRONMENT", "prod")
    return RuntimeConfig(
        environment=selected_environment,  # type: ignore[arg-type]
        overrides=overrides or {},
    )


def configure(
    environment: Environment | None = None,
    overrides: Mapping[str, str] | None = None,
) -> RuntimeConfig:
    """Set the process-wide configuration used by existing TCT functions."""
    global _configured_runtime
    _configured_runtime = load_config(environment, overrides)
    return _configured_runtime


def get_runtime_config() -> RuntimeConfig:
    """Return explicit configuration or one derived from the environment."""
    return _configured_runtime or load_config()


def reset_config() -> None:
    """Clear process-wide configuration, primarily for tests."""
    global _configured_runtime
    _configured_runtime = None


def service_url(service: str) -> str:
    """Resolve a service using the current process configuration."""
    return get_runtime_config().service_url(service)
