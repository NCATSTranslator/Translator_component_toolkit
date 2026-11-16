"""Offline validation against checksum-pinned upstream TRAPI schemas."""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).with_name("schemas")


@lru_cache(maxsize=2)
def schema(version):
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry

    manifest = json.loads((ROOT / "manifest.json").read_text())
    if version not in manifest:
        raise ValueError(
            f"Unsupported TRAPI version {version!r}; available: {sorted(manifest)}"
        )
    raw = (ROOT / f"trapi-{version}.yaml").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest[version]["sha256"]:
        raise ValueError("Pinned TRAPI schema checksum mismatch")
    document = yaml.safe_load(raw)

    def convert(value):
        # OpenAPI 3.0 nullable is not a JSON Schema keyword. Preserve its meaning.
        if isinstance(value, list):
            return [convert(x) for x in value]
        if not isinstance(value, dict):
            return value
        result = {k: convert(v) for k, v in value.items() if k != "nullable"}
        return (
            {"anyOf": [result, {"type": "null"}]} if value.get("nullable") else result
        )

    root = {
        "$ref": "#/components/schemas/Response",
        "components": convert(document["components"]),
    }

    def no_network(uri):
        raise ValueError(f"External schema reference is not vendored: {uri}")

    return Draft202012Validator(root, registry=Registry(retrieve=no_network)), manifest[
        version
    ]


def validate(response, version="1.5.0"):
    validator, pin = schema(version)

    def leaves(error):
        if error.context:
            for child in error.context:
                yield from leaves(child)
        elif error.schema != {"type": "null"}:
            yield error

    try:
        errors = sorted(
            [
                {
                    "path": "/" + "/".join(str(x) for x in e.absolute_path),
                    "message": e.message[:1000],
                }
                for parent in validator.iter_errors(response)
                for e in leaves(parent)
            ],
            key=lambda e: (e["path"], e["message"]),
        )
    except Exception as error:
        errors = [{"path": "/", "message": f"Validation unavailable: {error}"}]
    return {
        "version": version,
        "schema": deepcopy(pin),
        "valid": not errors,
        "errors": errors,
        "scope": "TRAPI structural schema only; not Biolink semantic validation",
    }
