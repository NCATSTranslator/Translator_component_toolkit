"""Offline regression tests for Node Normalizer routing and HTTP errors."""

import json

import pytest
import requests

from TCT import node_normalizer
from TCT.TCT import _resolve_node
from TCT.config import configure, reset_config


@pytest.fixture(autouse=True)
def clean_runtime_config():
    reset_config()
    yield
    reset_config()


@pytest.mark.parametrize("environment", ["prod", "ci", "test"])
@pytest.mark.parametrize("mode", ["get", "post"])
@pytest.mark.parametrize("override", [None, "https://example.org/nodenorm/"])
def test_pathfinder_node_resolution_routes_requests(
    monkeypatch, environment, mode, override
):
    configure(
        environment=environment,
        overrides={"node_normalizer": override} if override else None,
    )
    base_url = override or "https://nodenorm.transltr.io/"
    calls = []

    def fake_request(url, **kwargs):
        assert url == base_url + "get_normalized_nodes"
        payload = kwargs["params" if mode == "get" else "json"]
        curie = payload["curie"] if mode == "get" else payload["curies"][0]
        assert payload["conflate"] is False
        calls.append(curie)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            curie: {
                "id": {"identifier": curie, "label": "Disease"},
                "type": ["biolink:Disease"],
            }
        }).encode()
        return response

    monkeypatch.setattr(node_normalizer.requests, mode, fake_request)
    for curie in ["MONDO:0018881", "MONDO:0018874"]:
        node = _resolve_node(
            curie, node_normalizer_kwargs={"mode": mode, "conflate": False}
        )
        assert node.curie == curie
        assert node.categories == ["biolink:Disease"]
    assert calls == ["MONDO:0018881", "MONDO:0018874"]


@pytest.mark.parametrize("mode", ["get", "post"])
def test_http_error_includes_url_status_and_response(monkeypatch, mode):
    response = requests.Response()
    response.status_code = 404
    response.url = "https://example.org/get_normalized_nodes"
    response.request = requests.Request(mode.upper(), response.url).prepare()
    monkeypatch.setattr(
        node_normalizer.requests, mode, lambda *args, **kwargs: response
    )

    with pytest.raises(requests.HTTPError) as error:
        node_normalizer.get_normalized_nodes("MONDO:0018881", mode=mode)

    assert "404" in str(error.value)
    assert response.url in str(error.value)
    assert error.value.response is response
    assert error.value.request is response.request
