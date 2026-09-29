"""Submit TRAPI queries to ARS and retrieve their merged responses.

The Autonomous Relay System (ARS) accepts one TRAPI query, fans it out to every
registered ARA, and merges their answers. Submission is asynchronous:

1. ``POST {ars}/submit`` returns the *parent* message ``pk``.
2. ``GET {ars}/messages/<pk>?trace=y`` reports the parent ``status``
   (``Running`` -> ``Done`` or ``Error``), one ``children`` entry per ARA plus
   one for the ARS merge agent, and ``merged_version``: the pk of the merged
   message once the ARS has combined the ARA answers.
3. ``GET {ars}/messages/<merged_version>`` returns the merged message; its
   ``fields.data.message`` holds the combined TRAPI ``knowledge_graph``,
   ``results``, and ``auxiliary_graphs``.

The parent can read ``Done`` a few seconds before the merge agent's child has
finished saving (NCATSTranslator/Relay#621), so :func:`wait_for_ARS` waits for
both before returning.

The API root comes from :mod:`TCT.config` (the ``ars`` service), so
``TCT_ENVIRONMENT`` or :func:`TCT.configure` selects prod, ci, or test.
"""

from __future__ import annotations

import ast
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Union

import requests

from .config import service_url
from .TCT import (
    CategoryList,
    FinderResult,
    NodeInput,
    _build_finder_result,
    _normalize_categories,
    _resolve_nodes,
)
from .TCT_pathfinder import build_query_graph

logger = logging.getLogger(__name__)

MERGE_AGENT = "ars-ars-agent"
"""Agent name of the ARS child that holds the merged answer."""

TERMINAL_STATUSES = frozenset({"Done", "Error"})
"""Parent statuses after which the ARS will not change a message again."""

HTTP_TIMEOUT = 120.0

__all__ = [
    "ARSChild",
    "ARSError",
    "ARSPendingError",
    "ARSResult",
    "ARSStatus",
    "ARSTimeoutError",
    "MERGE_AGENT",
    "ARS_neighborhood_finder",
    "ARS_pathfinder",
    "Query_ARS",
    "check_ars_results",
    "fetch_ars_results",
    "format_query_json_forARS_neighborhood",
    "format_query_json_forARS_pathfinder",
    "get_ARS_result",
    "get_ARS_status",
    "submit_ARS",
    "summarize_results",
    "wait_for_ARS",
]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
class ARSError(RuntimeError):
    """Raised when the ARS rejects a request or reports a failed query."""


class ARSTimeoutError(ARSError, TimeoutError):
    """Raised when a query does not finish within the allowed time."""

    def __init__(self, status: "ARSStatus", timeout: float) -> None:
        self.status = status
        self.timeout = timeout
        super().__init__(
            f"ARS query {status.pk} did not finish within {timeout:.0f}s "
            f"(status={status.status!r}; {status.summary()})"
        )


class ARSPendingError(ARSError):
    """Raised when results are requested before a query reaches a merged state."""

    def __init__(self, status: "ARSStatus") -> None:
        self.status = status
        super().__init__(
            f"ARS query {status.pk} is not finished yet (status={status.status!r}); "
            "poll get_ARS_status or use wait_for_ARS first"
        )


# ---------------------------------------------------------------------------
# status model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ARSChild:
    """One agent's entry in a parent message trace."""

    agent: str
    pk: Optional[str]
    status: Optional[str]
    code: Optional[int]
    result_count: Optional[int]
    infores: Optional[str] = None


@dataclass(frozen=True)
class ARSStatus:
    """Parsed ``?trace=y`` view of a parent ARS message."""

    pk: str
    status: Optional[str]
    code: Optional[int]
    merged_version: Optional[str]
    merged_versions_list: tuple[tuple[str, ...], ...] = ()
    children: tuple[ARSChild, ...] = ()
    result_count: Optional[int] = None
    _children_by_agent: dict[str, ARSChild] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # Index children once so lookups by agent name are O(1).
        object.__setattr__(
            self, "_children_by_agent", {child.agent: child for child in self.children}
        )

    @property
    def is_terminal(self) -> bool:
        """True once the parent reports ``Done`` or ``Error``."""
        return self.status in TERMINAL_STATUSES

    @property
    def merge_child(self) -> Optional[ARSChild]:
        """The child entry written by the ARS merge agent, if present."""
        return self._children_by_agent.get(MERGE_AGENT)

    @property
    def merged_ready(self) -> bool:
        """True when a merged message exists and the merge agent is ``Done``."""
        merge = self.merge_child
        return bool(self.merged_version) and merge is not None and merge.status == "Done"

    def summary(self) -> str:
        """One-line summary of child statuses for logs and error messages."""
        parts = [f"{child.agent}={child.status}" for child in self.children]
        return ", ".join(parts) if parts else "no children yet"


@dataclass
class ARSResult(FinderResult):
    """Merged ARS answer wrapped like the other finder results.

    Extends :class:`TCT.TCT.FinderResult` with the ARS identifiers, the final
    status, and a ranked row summarizer. ``raw`` holds the merged TRAPI
    message; ``query``, ``knowledge_graph``, ``results``, ``auxiliary_graphs``,
    ``resolved_nodes``, and ``to_dict()`` behave exactly like the other finders.
    """

    pk: str = ""
    merged_pk: Optional[str] = None
    status: Optional[ARSStatus] = None

    def summarize(self, top_n: Optional[int] = 20) -> list[dict[str, Any]]:
        """Return up to ``top_n`` ranked, agent-friendly result rows."""
        return summarize_results(self.raw, top_n=top_n)


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
_SHARED_SESSION: Optional[requests.Session] = None


def _session() -> requests.Session:
    """Return the shared HTTP session (keep-alive across ARS calls)."""
    global _SHARED_SESSION
    if _SHARED_SESSION is None:
        _SHARED_SESSION = requests.Session()
    return _SHARED_SESSION


def _ars_root(url: Optional[str] = None) -> str:
    """Resolve the ARS API root, defaulting to the configured ``ars`` service."""
    root = (url or service_url("ars")).rstrip("/")
    return root


def _post(url: str, json_body: dict[str, Any]) -> requests.Response:
    return _session().post(url, json=json_body, timeout=HTTP_TIMEOUT)


def _get(url: str, params: Optional[dict[str, str]] = None) -> requests.Response:
    return _session().get(url, params=params, timeout=HTTP_TIMEOUT)


def _api_root(url: Optional[str]) -> str:
    root = (url or service_url("ars")).rstrip("/")
    return root


def _message_from_envelope(envelope: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Extract the merged TRAPI message from a full ARS message envelope."""
    data = (envelope.get("fields") or {}).get("data") or {}
    message = data.get("message") if isinstance(data, dict) else None
    return message if isinstance(message, dict) else None


# ---------------------------------------------------------------------------
# query construction
# ---------------------------------------------------------------------------
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


def format_query_json_forARS_pathfinder(
    start_node_id: str,
    end_node_id: str,
    subject_categories: list[str] | None = None,
    object_categories: list[str] | None = None,
    constraints_path: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a paths TRAPI query from the shared pathfinder query graph.

    ``constraints_path`` optionally restricts intermediate path nodes; see
    :func:`TCT.TCT_pathfinder.build_query_graph` for the accepted shape.
    """
    if not start_node_id or not end_node_id:
        raise ValueError("start_node_id and end_node_id are required")
    graph = build_query_graph(
        start_node_id=start_node_id,
        end_node_id=end_node_id,
        start_node_categories=subject_categories,
        end_node_categories=object_categories,
        constraints_path=constraints_path,
    )
    return {"message": {"query_graph": graph}, "submitter": "TCT"}


# ---------------------------------------------------------------------------
# submit / poll / fetch
# ---------------------------------------------------------------------------
def submit_ARS(query_json: dict[str, Any], *, url: str | None = None) -> str:
    """Validate and submit a TRAPI query to the ARS; return the parent pk."""
    message = query_json.get("message") if isinstance(query_json, dict) else None
    if not isinstance(message, dict) or not isinstance(message.get("query_graph"), dict):
        raise ValueError("ARS input must be a JSON object with message.query_graph")

    response = _post(f"{_ars_root(url)}/submit", query_json)
    if response.status_code not in (200, 201):
        raise ARSError(
            f"ARS submit failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    pk = response.json().get("pk")
    if not isinstance(pk, str) or not pk:
        raise ValueError("ARS submission did not return a message pk")
    logger.info("ARS query submitted: pk=%s", pk)
    return pk


def Query_ARS(url: str, json_file: dict[str, Any]) -> str:
    """Submit a TRAPI JSON object to ARS and return its message identifier."""
    return submit_ARS(json_file, url=url)


def _as_version_list(value: Any) -> tuple[tuple[str, ...], ...]:
    """Normalize ``merged_versions_list``.

    The ARS serializes this field as the Python repr of a list of
    ``[pk, agent]`` pairs (a string) rather than JSON, so parse that form and
    accept a real list as well.
    """
    if not value:
        return ()
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return ((value,),)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        tuple(str(part) for part in item) if isinstance(item, (list, tuple)) else (str(item),)
        for item in value
    )


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_trace(pk: str, trace: dict[str, Any]) -> ARSStatus:
    """Convert a ``?trace=y`` response into an :class:`ARSStatus`."""
    children = tuple(
        ARSChild(
            agent=str((child.get("actor") or {}).get("agent") or ""),
            pk=child.get("message"),
            status=child.get("status"),
            code=_to_int(child.get("code")),
            result_count=_to_int(child.get("result_count")),
            infores=(child.get("actor") or {}).get("inforesid") or None,
        )
        for child in trace.get("children") or []
    )
    return ARSStatus(
        pk=pk,
        status=trace.get("status"),
        code=_to_int(trace.get("code")),
        merged_version=trace.get("merged_version") or None,
        merged_versions_list=_as_version_list(trace.get("merged_versions_list")),
        children=children,
        result_count=_to_int(trace.get("result_count")),
    )


def get_message(pk: str, *, trace: bool = False, url: str | None = None) -> dict[str, Any]:
    """Fetch one ARS message by pk, optionally in lightweight trace form."""
    params = {"trace": "y"} if trace else None
    response = _get(f"{_ars_root(url)}/messages/{pk}", params=params)
    if response.status_code == 404:
        raise LookupError(f"ARS message not found: {pk}")
    if response.status_code != 200:
        raise ARSError(
            f"ARS messages/{pk} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )
    return response.json()


def get_ARS_status(pk: str, *, url: str | None = None) -> ARSStatus:
    """Return the current status of a submitted query and its ARA children."""
    return parse_trace(pk, get_message(pk, trace=True, url=url))


def check_ars_results(
    response_pk: str,
    *,
    url: str | None = None,
    max_retries: int = 15,
    poll_interval: float = 30,
    merge_grace: float = 30.0,
) -> str | None:
    """Poll the parent ARS message and return its merged message identifier.

    Return ``None`` when ARS finishes without a merged result. Raise
    :class:`ARSTimeoutError` (a ``TimeoutError``) if the message never reaches a
    terminal state. The parent reads ``Done`` before the merge agent has saved
    (NCATSTranslator/Relay#621), so polling continues until the merge child is
    also ``Done`` or ``merge_grace`` seconds elapse after the parent finished.
    """
    return wait_for_ARS(
        response_pk,
        url=url,
        max_retries=max_retries,
        poll_interval=poll_interval,
        merge_grace=merge_grace,
    ).merged_version


def wait_for_ARS(
    pk: str,
    *,
    url: str | None = None,
    max_retries: int = 15,
    poll_interval: float = 30.0,
    merge_grace: float = 30.0,
) -> ARSStatus:
    """Poll a parent message until the ARS has finished and merged the answers.

    Returns when the parent status is ``Done`` **and** the merge agent's child
    reports ``Done``. If the parent is ``Done`` but no merged message becomes
    ready within ``merge_grace`` seconds (for example, a query with no ARA
    results), the last observed status is returned instead.

    Raises
    ------
    ARSError
        If the parent finishes with status ``Error``.
    ARSTimeoutError
        After ``max_retries`` polls spaced ``poll_interval`` seconds apart.
    """
    if not pk:
        raise ValueError("An ARS message pk is required")
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    deadline_polls = time.monotonic() + max_retries * poll_interval
    parent_done_at: Optional[float] = None
    attempt = 0
    while True:
        attempt += 1
        status = get_ARS_status(pk, url=url)
        logger.info("ARS %s: %s (%s)", pk, status.status, status.summary())
        if status.status == "Error":
            raise ARSError(f"ARS query {pk} finished with status Error ({status.summary()})")
        if status.is_terminal:
            if status.merged_ready:
                return status
            now = time.monotonic()
            if parent_done_at is None:
                parent_done_at = now
            if now - parent_done_at >= merge_grace:
                logger.warning(
                    "ARS %s: parent Done but merged message not ready after %.0fs; "
                    "returning as is",
                    pk,
                    merge_grace,
                )
                return status
        if attempt >= max_retries or time.monotonic() >= deadline_polls:
            raise ARSTimeoutError(status, max_retries * poll_interval)
        time.sleep(poll_interval)


def fetch_ars_results(merged_pk: str, *, url: str | None = None) -> dict[str, Any]:
    """Fetch the full merged ARS message, including ``fields.data.message``."""
    if not merged_pk:
        raise ValueError("A merged ARS message pk is required")
    response = _get(f"{_ars_root(url)}/messages/{merged_pk}")
    if response.status_code != 200:
        raise ARSError(
            f"ARS messages/{merged_pk} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )
    return response.json()


def get_ARS_result(
    pk_or_status: Union[str, ARSStatus],
    *,
    url: str | None = None,
) -> ARSResult:
    """Fetch the merged answer for a finished query as an :class:`ARSResult`.

    Falls back to the parent message's own payload when the ARS produced no
    merged version.
    """
    status = (
        pk_or_status
        if isinstance(pk_or_status, ARSStatus)
        else get_ARS_status(pk_or_status, url=url)
    )
    if not status.is_terminal:
        raise ARSPendingError(status)
    target = status.merged_version or status.pk
    message = _message_from_envelope(fetch_ars_results(target, url=url))
    return ARSResult(
        pk=status.pk,
        merged_pk=status.merged_version,
        status=status,
        raw=message or {},
        query={},
        knowledge_graph=message.get("knowledge_graph") or {} if message else {},
        results=list(message.get("results") or []) if message else [],
        auxiliary_graphs=message.get("auxiliary_graphs") or {} if message else {},
        resolved_nodes={},
    )


# ---------------------------------------------------------------------------
# result summarization
# ---------------------------------------------------------------------------
def _primary_sources(edge: dict[str, Any]) -> list[str]:
    return sorted(
        {
            source.get("resource_id")
            for source in edge.get("sources") or []
            if source.get("resource_role") == "primary_knowledge_source"
            and source.get("resource_id")
        }
    )


def summarize_results(
    message: Optional[dict[str, Any]],
    *,
    top_n: Optional[int] = 20,
) -> list[dict[str, Any]]:
    """Flatten a merged ARS message into ranked, agent-friendly rows.

    Each row carries the result rank and score, the answer node (``essence``),
    every bound node with its name and categories, and the predicates and
    primary knowledge sources of the edges bound in the result's analyses.
    Only the first ``top_n`` results are visited; ``None`` returns all rows.
    """
    if not message:
        return []
    kg = message.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or {}
    edges = kg.get("edges") or {}
    results = list(message.get("results") or [])
    if top_n is not None:
        results = results[:top_n]

    rows: list[dict[str, Any]] = []
    for rank, result in enumerate(results, start=1):
        bound_nodes = {
            qnode: [
                {
                    "id": binding.get("id"),
                    "name": (nodes.get(binding.get("id")) or {}).get("name"),
                    "categories": (nodes.get(binding.get("id")) or {}).get("categories"),
                }
                for binding in bindings
                if binding.get("id")
            ]
            for qnode, bindings in (result.get("node_bindings") or {}).items()
        }
        predicates: set[str] = set()
        sources: set[str] = set()
        aras: set[str] = set()
        edge_count = 0
        for analysis in result.get("analyses") or []:
            if analysis.get("resource_id"):
                aras.add(analysis["resource_id"])
            for bindings in (analysis.get("edge_bindings") or {}).values():
                for binding in bindings:
                    edge = edges.get(binding.get("id")) or {}
                    if not edge:
                        continue
                    edge_count += 1
                    if edge.get("predicate"):
                        predicates.add(edge["predicate"])
                    sources.update(_primary_sources(edge))
        rows.append(
            {
                "rank": result.get("rank", rank),
                "score": result.get("normalized_score", result.get("score")),
                "essence": result.get("essence"),
                "essence_category": result.get("essence_category"),
                "nodes": bound_nodes,
                "predicates": sorted(predicates),
                "primary_sources": sorted(sources),
                "aras": sorted(aras),
                "edge_count": edge_count,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# finder-style entry points
# ---------------------------------------------------------------------------
def _empty_raw(query_graph: dict[str, Any]) -> dict[str, Any]:
    """Shell TRAPI message used when the ARS produced no merged message."""
    return {
        "query_graph": query_graph,
        "knowledge_graph": {"nodes": {}, "edges": {}},
        "results": [],
        "auxiliary_graphs": {},
    }


def _collect_result(
    pk: str,
    query_json: dict[str, Any],
    *,
    resolved_nodes: dict[str, Any],
    url: str | None,
    max_retries: int,
    poll_interval: float,
    merge_grace: float,
) -> ARSResult:
    """Run submit -> wait -> fetch and wrap the outcome as an ``ARSResult``."""
    status = wait_for_ARS(
        pk,
        url=url,
        max_retries=max_retries,
        poll_interval=poll_interval,
        merge_grace=merge_grace,
    )
    target = status.merged_version or status.pk
    message = _message_from_envelope(fetch_ars_results(target, url=url))
    raw = message if message else _empty_raw(query_json["message"]["query_graph"])
    base = _build_finder_result(raw, resolved_nodes=resolved_nodes)
    return ARSResult(
        query=base.query,
        knowledge_graph=base.knowledge_graph,
        results=base.results,
        auxiliary_graphs=base.auxiliary_graphs,
        resolved_nodes=base.resolved_nodes,
        raw=base.raw,
        pk=pk,
        merged_pk=status.merged_version,
        status=status,
    )


def _node_keyed_inputs(
    node: Union[NodeInput, list[NodeInput]],
    resolved_nodes: list,
) -> dict[str, Any]:
    """Key resolved inputs ``node`` for a single input, ``node_{i}`` for lists."""
    if isinstance(node, str):
        return {"node": resolved_nodes[0]}
    return {f"node_{index}": resolved for index, resolved in enumerate(resolved_nodes)}


def ARS_neighborhood_finder(
    node: Union[NodeInput, list[NodeInput], None] = None,
    neighbor_categories: CategoryList | None = None,
    *,
    json_file: dict[str, Any] | None = None,
    node_categories: CategoryList | None = None,
    predicates: list[str] | None = None,
    attribute_constraints: list[dict[str, Any]] | None = None,
    max_retries: int = 15,
    poll_interval: float = 30.0,
    merge_grace: float = 30.0,
    name_resolver_kwargs: dict[str, Any] | None = None,
    node_normalizer_kwargs: dict[str, Any] | None = None,
) -> ARSResult:
    """Find one-hop neighbors for one or more concepts by asking the ARS.

    Unlike :func:`TCT.neighborhood_finder`, this does not load the MetaKG or
    pick knowledge providers itself; the ARS fans the query out to every ARA
    and merges their answers.

    Pass the parsed contents of an uploaded JSON file as ``json_file``; it is
    submitted unchanged, so both ``edges`` and ``paths`` query graphs work.
    Otherwise ``node`` and ``neighbor_categories`` build a one-hop query, with
    names resolved to CURIEs first (the ARS accepts unresolved names at submit
    time and then returns no results).

    Returns
    -------
    ARSResult
        The merged answer wrapped like the other finders. ``raw`` is the
        merged TRAPI message and ``resolved_nodes`` records the input CURIEs.
    """
    if json_file is not None:
        if node is not None or neighbor_categories is not None:
            raise ValueError("Provide json_file or node and neighbor_categories")
        query = json_file
        resolved: dict[str, Any] = {}
    else:
        if node is None:
            raise ValueError("Provide json_file or node")
        resolved_list = _resolve_nodes(
            node,
            name_resolver_kwargs=name_resolver_kwargs,
            node_normalizer_kwargs=node_normalizer_kwargs,
        )
        query = format_query_json_forARS_neighborhood(
            subject_ids=[resolved.curie for resolved in resolved_list],
            subject_categories=_normalize_categories(node_categories),
            object_categories=_normalize_categories(neighbor_categories),
            predicates=predicates,
            attribute_constraints=attribute_constraints,
        )
        resolved = _node_keyed_inputs(node, resolved_list)

    pk = submit_ARS(query)
    return _collect_result(
        pk,
        query,
        resolved_nodes=resolved,
        url=None,
        max_retries=max_retries,
        poll_interval=poll_interval,
        merge_grace=merge_grace,
    )


def ARS_pathfinder(
    start: NodeInput,
    end: NodeInput,
    *,
    intermediate_categories: CategoryList | None = None,
    predicates: list[str] | None = None,
    json_file: dict[str, Any] | None = None,
    attribute_constraints: list[dict[str, Any]] | None = None,
    max_retries: int = 15,
    poll_interval: float = 30.0,
    merge_grace: float = 30.0,
    name_resolver_kwargs: dict[str, Any] | None = None,
    node_normalizer_kwargs: dict[str, Any] | None = None,
) -> ARSResult:
    """Find paths between two concepts by asking the ARS.

    Like :func:`ARS_neighborhood_finder`, the ARS fans the query out to every
    ARA instead of using locally selected knowledge providers. At most one
    ``intermediate_categories`` value is applied, mirroring the local
    pathfinder. A ``json_file`` with a complete TRAPI query (``paths`` or
    ``edges`` query graph) is submitted unchanged instead.

    Returns
    -------
    ARSResult
        The merged answer wrapped like the other finders; ``resolved_nodes``
        records the resolved ``start`` and ``end`` inputs.
    """
    if json_file is not None:
        query = json_file
        resolved: dict[str, Any] = {}
    else:
        resolved_list = _resolve_nodes(
            [start, end],
            name_resolver_kwargs=name_resolver_kwargs,
            node_normalizer_kwargs=node_normalizer_kwargs,
        )
        intermediate = _normalize_categories(intermediate_categories)
        if intermediate and len(intermediate) > 1:
            logger.warning(
                "ARS pathfinder supports a single intermediate category; using %r",
                intermediate[0],
            )
        query = format_query_json_forARS_pathfinder(
            resolved_list[0].curie,
            resolved_list[1].curie,
            subject_categories=resolved_list[0].categories or None,
            object_categories=resolved_list[1].categories or None,
            constraints_path=(
                [{"intermediate_categories": [intermediate[0]]}] if intermediate else None
            ),
        )
        resolved = {"start": resolved_list[0], "end": resolved_list[1]}

    pk = submit_ARS(query)
    return _collect_result(
        pk,
        query,
        resolved_nodes=resolved,
        url=None,
        max_retries=max_retries,
        poll_interval=poll_interval,
        merge_grace=merge_grace,
    )
