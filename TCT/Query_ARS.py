"""Submit TRAPI queries to ARS and retrieve their merged responses."""

from __future__ import annotations

import time
from typing import Any

import requests


CI_URL = "https://ars.ci.transltr.io/ars/api"
BASE_URL = CI_URL
TEST_URL = "https://ars.test.transltr.io/ars/api"


def Query_ARS(url: str, json_file: dict[str, Any]) -> str:
    """Submit a TRAPI JSON object to ARS and return its message identifier."""
    message = json_file.get("message") if isinstance(json_file, dict) else None
    if not isinstance(message, dict) or not isinstance(message.get("query_graph"), dict):
        raise ValueError("ARS input must be a JSON object with message.query_graph")

    response = requests.post(
        f"{url.rstrip('/')}/submit", json=json_file, timeout=30
    )
    response.raise_for_status()
    pk = response.json().get("pk")
    if not isinstance(pk, str) or not pk:
        raise ValueError("ARS submission did not return a message pk")
    return pk


def check_ars_results(
    response_pk: str,
    *,
    url: str = BASE_URL,
    max_retries: int = 15,
    poll_interval: float = 30,
) -> str | None:
    """Poll the parent ARS message and return its merged message identifier.

    Return ``None`` when ARS finishes without a merged result. Raise
    ``TimeoutError`` if the message never reaches a terminal state.
    """
    if not response_pk:
        raise ValueError("An ARS message pk is required")
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    base_url = url.rstrip("/")
    for attempt in range(max_retries):
        response = requests.get(
            f"{base_url}/messages/{response_pk}",
            params={"trace": "y"}, timeout=30,
        )
        response.raise_for_status()
        parent = response.json()
        status = parent.get("status")
        if status == "Done":
            return parent.get("merged_version")
        if status in {"Error", "Failed"}:
            raise RuntimeError(f"ARS message {response_pk} ended with status {status}")
        if attempt + 1 < max_retries:
            time.sleep(poll_interval)

    raise TimeoutError(f"ARS message {response_pk} was not done after {max_retries} checks")


def fetch_ars_results(merged_pk: str, *, url: str = BASE_URL) -> dict[str, Any]:
    """Fetch the full merged ARS message, including ``fields.data.message``."""
    if not merged_pk:
        raise ValueError("A merged ARS message pk is required")
    response = requests.get(f"{url.rstrip('/')}/messages/{merged_pk}", timeout=30)
    response.raise_for_status()
    return response.json()




def format_query_json_forARS_neighborhood(
    subject_ids: list[str],
    object_ids: list[str] | None = None,
    subject_categories: list[str] | None = None,
    object_categories: list[str] | None = None,
    predicates: list[str] | None = None,
    attribute_constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a one-hop TRAPI query for callers without uploaded JSON."""
    if not subject_ids:
        raise ValueError("subject_ids must contain at least one CURIE")
    if not object_ids and not object_categories:
        raise ValueError("object_ids or object_categories must be provided")

    subject: dict[str, Any] = {"ids": subject_ids}
    object_node: dict[str, Any] = {}
    if subject_categories:
        subject["categories"] = subject_categories
    if object_ids:
        object_node["ids"] = object_ids
    if object_categories:
        object_node["categories"] = object_categories

    edge: dict[str, Any] = {
        "subject": "n00", "object": "n01",
        "predicates": predicates or ["biolink:related_to"],
    }
    if attribute_constraints:
        edge["attribute_constraints"] = attribute_constraints

    return {
        "message": {"query_graph": {
            "edges": {"e00": edge},
            "nodes": {"n00": subject, "n01": object_node},
        }},
        "submitter": "TCT",
    }


def ARS_neighborhood_finder(
    node: str | list[str] | None = None,
    neighbor_categories: list[str] | None = None,
    *,
    json_file: dict[str, Any] | None = None,
    node_categories: list[str] | None = None,
    predicates_subset: list[str] | None = None,
    attribute_constraints: list[dict[str, Any]] | None = None,
    url: str = BASE_URL,
) -> dict[str, Any] | None:
    """Return full merged ARS results for uploaded JSON or a one-hop query.

    Pass the parsed contents of an uploaded JSON file as ``json_file``. When
    ``node`` is supplied instead, build a one-hop query from the given CURIEs.
    The uploaded query is submitted unchanged, so both ``edges`` and ``paths``
    query graphs work. The result is the full merged ARS message envelope;
    its TRAPI response is under ``fields.data.message``. ARS may return no
    merged result.
    """
    if json_file is not None:
        if node is not None or neighbor_categories is not None:
            raise ValueError("Provide json_file or node and neighbor_categories")
        query = json_file
    else:
        if node is None:
            raise ValueError("Provide json_file or node")
        nodes = [node] if isinstance(node, str) else node
        query = format_query_json_forARS_neighborhood(
            subject_ids=nodes,
            subject_categories=node_categories,
            object_categories=neighbor_categories,
            predicates=predicates_subset,
            attribute_constraints=attribute_constraints,
        )

    pk = Query_ARS(url, query)
    merged_pk = check_ars_results(pk, url=url)
    return fetch_ars_results(merged_pk, url=url) if merged_pk else None
