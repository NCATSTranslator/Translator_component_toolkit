"""Client for the Translator Autonomous Relay System (ARS).

The ARS accepts one TRAPI query, fans it out to every registered Autonomous
Relay Agent (ARA), and merges their answers. Submission is asynchronous:

1. ``POST {ars}/submit`` with a TRAPI message returns a *parent* message whose
   ``pk`` identifies the whole query.
2. ``GET {ars}/messages/<pk>?trace=y`` returns the parent's ``status``
   (``Running`` -> ``Done`` or ``Error``), one ``children`` entry per ARA plus
   one for the ARS merge agent, and ``merged_version``: the pk of the merged
   message once the ARS has combined the ARA answers.
3. ``GET {ars}/messages/<merged_version>`` returns the merged message; its
   ``fields.data.message`` holds the combined TRAPI ``knowledge_graph``,
   ``results`` and ``auxiliary_graphs``.

The parent can read ``Done`` a few seconds before the merge agent's child has
finished saving (NCATSTranslator/Relay#621), so :func:`wait_for_results` waits
for both before returning.

The ARS accepts malformed queries at submit time (unresolved names, a string
where ``ids`` needs a list, an empty ``predicates`` list) and only fails later,
usually as ``Done`` with zero results. :func:`ars_neighborhood_finder` resolves
its inputs to CURIEs and omits empty predicates for that reason.

The API root comes from :mod:`TCT.config` (``ars`` service), so
``TCT_ENVIRONMENT`` or :func:`TCT.configure` selects prod, ci, or test.
"""

from __future__ import annotations

import ast
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Union
from urllib.parse import urljoin

import requests

from . import translator_query
from .config import service_url
from .TCT import (
    CategoryList,
    FinderResult,
    NodeInput,
    _build_finder_result,
    _normalize_categories,
    _resolve_nodes,
)

logger = logging.getLogger(__name__)

MERGE_AGENT = "ars-ars-agent"
"""Agent name of the ARS child that holds the merged answer."""

TERMINAL_STATUSES = frozenset({"Done", "Error"})
"""Parent statuses after which the ARS will not change a message again."""

DEFAULT_POLL_INTERVAL = 10.0
DEFAULT_TIMEOUT = 900.0
DEFAULT_MERGE_GRACE = 30.0
HTTP_TIMEOUT = 120.0


class ARSError(RuntimeError):
    """Raised when the ARS rejects a request or reports a failed query."""


class ARSTimeoutError(ARSError):
    """Raised when a query does not finish within the allowed time."""

    def __init__(self, status: "ARSStatus", timeout: float) -> None:
        self.status = status
        self.timeout = timeout
        super().__init__(
            f"ARS query {status.pk} did not finish within {timeout:.0f}s "
            f"(status={status.status!r}; {status.summary()})"
        )


@dataclass(frozen=True)
class ARSChild:
    """One agent's entry in a parent message trace."""

    agent: str
    pk: Optional[str]
    status: Optional[str]
    code: Optional[int]
    result_count: Optional[int]
    infores: Optional[str] = None


@dataclass
class ARSStatus:
    """Parsed ``?trace=y`` view of a parent ARS message."""

    pk: str
    status: Optional[str]
    code: Optional[int]
    merged_version: Optional[str]
    merged_versions_list: list[list[str]] = field(default_factory=list)
    children: list[ARSChild] = field(default_factory=list)
    result_count: Optional[int] = None

    @property
    def is_terminal(self) -> bool:
        """True once the parent reports ``Done`` or ``Error``."""
        return self.status in TERMINAL_STATUSES

    @property
    def merge_child(self) -> Optional[ARSChild]:
        """The child entry written by the ARS merge agent, if present."""
        for child in self.children:
            if child.agent == MERGE_AGENT:
                return child
        return None

    @property
    def merged_ready(self) -> bool:
        """True when a merged message exists and the merge agent is ``Done``."""
        merge = self.merge_child
        return bool(self.merged_version) and merge is not None and merge.status == "Done"

    def summary(self) -> str:
        """One-line summary of child statuses for logs and error messages."""
        parts = [f"{c.agent}={c.status}" for c in self.children]
        return ", ".join(parts) if parts else "no children yet"


@dataclass
class ARSResult:
    """Outcome of :func:`query`."""

    pk: str
    status: ARSStatus
    merged_pk: Optional[str]
    message: Optional[dict[str, Any]]

    @property
    def results(self) -> list[dict[str, Any]]:
        """The TRAPI ``results`` list of the merged message (empty if none)."""
        if not self.message:
            return []
        return list(self.message.get("results") or [])


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _api_root(base_url: Optional[str] = None) -> str:
    root = (base_url or service_url("ars")).strip()
    return root if root.endswith("/") else root + "/"


def _as_trapi_request(query: dict[str, Any]) -> dict[str, Any]:
    """Accept a full TRAPI request, a bare ``message``, or a bare ``query_graph``."""
    if "message" in query:
        return query
    if "query_graph" in query:
        return {"message": query}
    if "nodes" in query and "edges" in query:
        return {"message": {"query_graph": query}}
    raise ValueError(
        "query must be a TRAPI request ({'message': ...}), a message "
        "({'query_graph': ...}), or a query graph ({'nodes': ..., 'edges': ...})"
    )


def _as_version_list(value: Any) -> list[list[str]]:
    """Normalise ``merged_versions_list``.

    The ARS serialises this field as the Python repr of a list of
    ``[pk, agent]`` pairs (a string) rather than JSON, so parse that form and
    accept a real list as well.
    """
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [[value]]
    if not isinstance(value, (list, tuple)):
        return []
    return [list(map(str, item)) if isinstance(item, (list, tuple)) else [str(item)] for item in value]


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def submit(
    query: dict[str, Any],
    *,
    base_url: Optional[str] = None,
) -> str:
    """Submit a TRAPI query to the ARS and return the parent message pk.

    Parameters
    ----------
    query : dict
        A TRAPI request (``{"message": {"query_graph": ...}}``). A bare
        ``message`` or a bare ``query_graph`` is wrapped automatically.
    base_url : str, optional
        ARS API root; defaults to the configured ``ars`` service URL.

    Returns
    -------
    str
        The parent message pk to poll with :func:`get_status`.

    Raises
    ------
    ARSError
        If the ARS returns a non-success status or no pk.

    Examples
    --------
    >>> q = translator_query.format_query_json(["MONDO:0005148"], object_categories=["biolink:ChemicalEntity"])
    >>> pk = submit(q)
    """
    payload = _as_trapi_request(query)
    response = requests.post(
        urljoin(_api_root(base_url), "submit"), json=payload, timeout=HTTP_TIMEOUT
    )
    if response.status_code not in (200, 201):
        raise ARSError(
            f"ARS submit failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    body = response.json()
    pk = body.get("pk")
    if not pk:
        raise ARSError(f"ARS submit response did not contain a pk: {body}")
    logger.info("ARS query submitted: pk=%s", pk)
    return str(pk)


def get_message(
    pk: str,
    *,
    trace: bool = False,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch one ARS message by pk.

    With ``trace=True`` the ARS returns the lightweight status view (parent
    status, children, ``merged_version``) instead of the full TRAPI payload.
    """
    params = {"trace": "y"} if trace else None
    response = requests.get(
        urljoin(_api_root(base_url), f"messages/{pk}"), params=params, timeout=HTTP_TIMEOUT
    )
    if response.status_code == 404:
        raise LookupError(f"ARS message not found: {pk}")
    if response.status_code != 200:
        raise ARSError(
            f"ARS messages/{pk} failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    return response.json()


def parse_trace(pk: str, trace: dict[str, Any]) -> ARSStatus:
    """Convert a ``?trace=y`` response into an :class:`ARSStatus`."""
    children = []
    for child in trace.get("children") or []:
        actor = child.get("actor") or {}
        children.append(
            ARSChild(
                agent=str(actor.get("agent") or ""),
                pk=child.get("message"),
                status=child.get("status"),
                code=_to_int(child.get("code")),
                result_count=_to_int(child.get("result_count")),
                infores=actor.get("inforesid") or None,
            )
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


def get_status(pk: str, *, base_url: Optional[str] = None) -> ARSStatus:
    """Return the current status of a submitted query and its ARA children."""
    return parse_trace(pk, get_message(pk, trace=True, base_url=base_url))


def wait_for_results(
    pk: str,
    *,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    merge_grace: float = DEFAULT_MERGE_GRACE,
    base_url: Optional[str] = None,
) -> ARSStatus:
    """Poll a parent message until the ARS has finished and merged the answers.

    Returns when the parent status is ``Done`` **and** the merge agent's child
    reports ``Done``. If the parent is ``Done`` but no merged message becomes
    ready within ``merge_grace`` seconds (for example, a query with no ARA
    results), the last observed status is returned instead.

    Parameters
    ----------
    pk : str
        Parent message pk from :func:`submit`.
    poll_interval : float
        Seconds between polls.
    timeout : float
        Maximum seconds to wait before raising :class:`ARSTimeoutError`.
    merge_grace : float
        Seconds to keep waiting for the merged message after the parent is
        ``Done``.

    Raises
    ------
    ARSError
        If the parent finishes with status ``Error``.
    ARSTimeoutError
        If ``timeout`` elapses first.
    """
    started = time.monotonic()
    parent_done_at: Optional[float] = None
    while True:
        status = get_status(pk, base_url=base_url)
        logger.info("ARS %s: %s (%s)", pk, status.status, status.summary())
        if status.status == "Error":
            raise ARSError(f"ARS query {pk} finished with status Error ({status.summary()})")
        if status.is_terminal:
            if status.merged_ready:
                return status
            now = time.monotonic()
            parent_done_at = parent_done_at if parent_done_at is not None else now
            if now - parent_done_at >= merge_grace:
                logger.warning(
                    "ARS %s: parent Done but merged message not ready after %.0fs; returning as is",
                    pk,
                    merge_grace,
                )
                return status
        if time.monotonic() - started >= timeout:
            raise ARSTimeoutError(status, timeout)
        time.sleep(poll_interval)


def get_results(
    status_or_pk: Union[ARSStatus, str],
    *,
    base_url: Optional[str] = None,
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Fetch the merged TRAPI message for a finished query.

    Returns ``(merged_pk, message)``. Falls back to the parent message's own
    payload when the ARS produced no merged version.
    """
    status = (
        status_or_pk
        if isinstance(status_or_pk, ARSStatus)
        else get_status(status_or_pk, base_url=base_url)
    )
    target = status.merged_version or status.pk
    body = get_message(target, base_url=base_url)
    data = (body.get("fields") or {}).get("data") or {}
    message = data.get("message") if isinstance(data, dict) else None
    return (status.merged_version, message)


def query(
    query_json: dict[str, Any],
    *,
    wait: bool = True,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    base_url: Optional[str] = None,
) -> ARSResult:
    """Submit a TRAPI query to the ARS and, by default, wait for the merged answer.

    Parameters
    ----------
    query_json : dict
        TRAPI request, message, or query graph (see :func:`submit`).
    wait : bool
        When false, return right after submission with only the pk and initial
        status populated; finish later with :func:`wait_for_results` and
        :func:`get_results`.
    poll_interval, timeout : float
        Passed to :func:`wait_for_results`.

    Returns
    -------
    ARSResult
        The pk, final :class:`ARSStatus`, merged pk, and merged TRAPI message.

    Examples
    --------
    >>> from TCT import ars, translator_query
    >>> q = translator_query.format_query_json(["MONDO:0005148"], object_categories=["biolink:ChemicalEntity"], predicates=["biolink:treats"])
    >>> result = ars.query(q)
    >>> len(result.results)
    140
    """
    pk = submit(query_json, base_url=base_url)
    if not wait:
        return ARSResult(pk=pk, status=get_status(pk, base_url=base_url), merged_pk=None, message=None)
    status = wait_for_results(
        pk, poll_interval=poll_interval, timeout=timeout, base_url=base_url
    )
    merged_pk, message = get_results(status, base_url=base_url)
    return ARSResult(pk=pk, status=status, merged_pk=merged_pk, message=message)


# --------------------------------------------------------------------------- #
# result summarisation
# --------------------------------------------------------------------------- #
def _primary_sources(edge: dict[str, Any]) -> list[str]:
    return sorted(
        {
            s.get("resource_id")
            for s in edge.get("sources") or []
            if s.get("resource_role") == "primary_knowledge_source" and s.get("resource_id")
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

    Parameters
    ----------
    message : dict
        The TRAPI message from :func:`get_results` or :attr:`ARSResult.message`.
    top_n : int, optional
        Number of rows to return; ``None`` returns all results.
    """
    if not message:
        return []
    kg = message.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or {}
    edges = kg.get("edges") or {}
    rows: list[dict[str, Any]] = []
    results = list(message.get("results") or [])
    if top_n is not None:
        results = results[:top_n]
    for rank, result in enumerate(results, start=1):
        bound_nodes = {}
        for qnode, bindings in (result.get("node_bindings") or {}).items():
            bound_nodes[qnode] = [
                {
                    "id": b.get("id"),
                    "name": (nodes.get(b.get("id")) or {}).get("name"),
                    "categories": (nodes.get(b.get("id")) or {}).get("categories"),
                }
                for b in bindings
                if b.get("id")
            ]
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


# --------------------------------------------------------------------------- #
# finder-style entry point
# --------------------------------------------------------------------------- #
def ars_neighborhood_finder(
    node: Union[NodeInput, list[NodeInput]],
    neighbor_categories: CategoryList,
    *,
    predicates: Optional[list[str]] = None,
    attribute_constraints: Optional[list[dict[str, Any]]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    base_url: Optional[str] = None,
    name_resolver_kwargs: Optional[dict[str, Any]] = None,
    node_normalizer_kwargs: Optional[dict[str, Any]] = None,
) -> FinderResult:
    """
    Find one-hop neighbors for one or more concepts by asking the ARS.

    Unlike :func:`TCT.neighborhood_finder`, this does not load the MetaKG or
    pick knowledge providers itself; the ARS fans the query out to every ARA
    and merges their answers. Inputs are resolved to CURIEs first because the
    ARS accepts unresolved names at submit time and then returns no results.

    Parameters
    ----------
    node : str or list[str]
        Source node or nodes, as CURIEs or human-readable strings.
    neighbor_categories : list[str]
        Desired neighbor categories, with or without the ``biolink:`` prefix.
    predicates : list[str], optional
        Edge predicates to require. Omitted (any predicate) when not given; an
        empty list is treated the same way. The query edge runs from the input
        node (subject) to the neighbor (object), so for "what treats X" use an
        inverse such as ``biolink:treated_by`` or leave predicates unset.
    attribute_constraints : list[dict], optional
        TRAPI attribute constraints passed through to query construction.
    poll_interval, timeout : float
        Passed to :func:`wait_for_results`.
    base_url : str, optional
        ARS API root override.
    name_resolver_kwargs, node_normalizer_kwargs : dict, optional
        Extra keyword arguments for name resolution and normalization.

    Returns
    -------
    FinderResult
        The merged ARS message wrapped like the other finders. ``raw`` is the
        full TRAPI message and ``resolved_nodes`` records the input CURIEs.

    Examples
    --------
    >>> from TCT.ars import ars_neighborhood_finder
    >>> result = ars_neighborhood_finder("type 2 diabetes", ["ChemicalEntity"], predicates=["biolink:treats"])
    >>> len(result.results)
    140
    """
    resolved_nodes = _resolve_nodes(
        node,
        name_resolver_kwargs=name_resolver_kwargs,
        node_normalizer_kwargs=node_normalizer_kwargs,
    )
    curies = [resolved.curie for resolved in resolved_nodes]
    trapi_query = translator_query.format_query_json(
        subject_ids=curies,
        object_ids=None,
        subject_categories=None,
        object_categories=_normalize_categories(neighbor_categories) or None,
        predicates=list(predicates) if predicates else None,
        attribute_constraints=attribute_constraints,
    )
    outcome = query(
        trapi_query, poll_interval=poll_interval, timeout=timeout, base_url=base_url
    )
    raw = outcome.message or {
        "query_graph": trapi_query["message"]["query_graph"],
        "knowledge_graph": {"nodes": {}, "edges": {}},
        "results": [],
        "auxiliary_graphs": {},
    }
    if isinstance(node, str):
        result_nodes = {"node": resolved_nodes[0]}
    else:
        result_nodes = {
            f"node_{index}": resolved for index, resolved in enumerate(resolved_nodes)
        }
    return _build_finder_result(raw, resolved_nodes=result_nodes)


__all__ = [
    "ARSChild",
    "ARSError",
    "ARSResult",
    "ARSStatus",
    "ARSTimeoutError",
    "MERGE_AGENT",
    "ars_neighborhood_finder",
    "get_message",
    "get_results",
    "get_status",
    "parse_trace",
    "query",
    "submit",
    "summarize_results",
    "wait_for_results",
]
