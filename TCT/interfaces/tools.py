"""Curated, interface-neutral tool surface for TCT.

The functions in this module are ordinary Python callables. Their names,
signatures, type annotations, defaults, and docstrings are the shared source
used to describe TCT operations to interfaces such as MCP and the CLI.

Keep protocol concerns out of this module: it must remain importable without
the optional MCP dependencies installed. ``TOOLS`` is intentionally explicit
so adding a library function does not publish it to agents by accident.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..name_resolver import batch_lookup, lookup, synonyms
from ..node_normalizer import get_normalized_nodes
from ..Query_ARS import (
    ARS_neighborhood_finder as _ars_neighborhood_finder,
    ARS_pathfinder as _ars_pathfinder,
    format_query_json_forARS_neighborhood as _format_query_json_forARS_neighborhood,
    get_ARS_result as _get_ARS_result,
    get_ARS_status as _get_ARS_status,
    submit_ARS as _submit_ARS,
)
from ..TCT import _normalize_categories, _resolve_nodes
from ..TCT import get_translator_resources as _get_translator_resources
from ..TCT_neighborhood_finder import neighborhood_finder as tct_neighborhood_finder
from ..TCT_pathfinder import query_TCT_pathfinder
from ..translator_kpinfo import get_translator_kp_info
from ..translator_metakg import add_new_API_for_query, add_plover_API, get_KP_metadata
from ..translator_query import (
    get_translator_API_predicates,
    optimize_query_json,
    parallel_api_query,
    query_KP,
)
from ..trapi import query as trapi_query


def get_translator_resources() -> Any:
    """Load the Translator resources used by the finder tools.

    Returns:
        Translator API names, MetaKG data, and supported predicates packaged
        as the library's ``TranslatorResources`` object.
    """
    return _get_translator_resources()


def name_lookup(
    query: str,
    return_top_response: bool = True,
    return_synonyms: bool = False,
) -> Any:
    """Resolve a biomedical name or term to Translator node information.

    Args:
        query: Name or term to resolve.
        return_top_response: Return only the highest-ranked response when true;
            return all responses when false.
        return_synonyms: Include synonyms in each returned node when true.

    Returns:
        A ``TranslatorNode`` for the highest-ranked response, or a list of
        nodes when ``return_top_response`` is false.
    """
    return lookup(query, return_top_response, return_synonyms)


def get_name_synonyms(query: str) -> Any:
    """Return synonyms and Translator node information for a CURIE.

    Args:
        query: CURIE whose synonyms should be returned.

    Returns:
        A mapping from the input CURIE to its ``TranslatorNode`` information.
    """
    return synonyms(query)


def batch_name_lookup(
    strings: list[str],
    size: int = 25,
    return_top_response: bool = True,
    return_synonyms: bool = False,
) -> Any:
    """Resolve multiple biomedical names or terms in batches.

    Args:
        strings: Names or terms to resolve.
        size: Maximum number of terms sent in each batch.
        return_top_response: Return only the highest-ranked response for each
            term when true; return all responses when false.
        return_synonyms: Include synonyms in returned nodes when true.

    Returns:
        A mapping from each input string to its resolved ``TranslatorNode`` or
        list of nodes.
    """
    return batch_lookup(strings, size, return_top_response, return_synonyms)


def normalize_nodes(
    query: str | list[str],
    return_equivalent_identifiers: bool = False,
    conflate: bool = True,
    drug_chemical_conflate: bool = False,
) -> Any:
    """Normalize one or more CURIEs with the Translator Node Normalizer.

    Args:
        query: A CURIE or list of CURIEs to normalize.
        return_equivalent_identifiers: Include equivalent identifiers in the
            returned node information when true.
        conflate: Enable gene-protein conflation.
        drug_chemical_conflate: Enable drug-chemical conflation.

    Returns:
        A normalized ``TranslatorNode`` for a single CURIE, or a mapping from
        CURIE to normalized node for multiple inputs.
    """
    return get_normalized_nodes(
        query,
        return_equivalent_identifiers,
        conflate=conflate,
        drug_chemical_conflate=drug_chemical_conflate,
    )


def get_kp_info() -> Any:
    """Return SmartAPI information for Translator Knowledge Providers.

    Returns:
        A pair containing the Knowledge Provider information table and a
        mapping from API names to query URLs.
    """
    return get_translator_kp_info()


def get_metakg_data(api_names: dict[str, str]) -> Any:
    """Return MetaKG metadata for a set of Knowledge Providers.

    Args:
        api_names: Mapping from Knowledge Provider names to query URLs.

    Returns:
        A table containing API, predicate, subject, object, and URL metadata.
    """
    return get_KP_metadata(api_names)


def add_custom_api_to_metakg(
    api_names: dict[str, str],
    metakg_df: Any,
    new_api_name: str,
    new_api_url: str,
    new_api_predicate: str,
    new_api_subject: str,
    new_api_object: str,
) -> Any:
    """Add a custom API and one edge definition to existing MetaKG data.

    Args:
        api_names: Current mapping from API names to query URLs.
        metakg_df: Current MetaKG table.
        new_api_name: Name used to identify the custom API.
        new_api_url: Query URL for the custom API.
        new_api_predicate: Predicate supported by the custom API.
        new_api_subject: Subject category supported by the custom API.
        new_api_object: Object category supported by the custom API.

    Returns:
        The updated API-name mapping and MetaKG table.
    """
    return add_new_API_for_query(
        api_names,
        metakg_df,
        new_api_name,
        new_api_url,
        new_api_predicate,
        new_api_subject,
        new_api_object,
    )


def add_plover_apis_to_metakg(
    api_names: dict[str, str],
    metakg_df: Any,
) -> Any:
    """Add the standard CATRAX Plover APIs to existing MetaKG data.

    Args:
        api_names: Current mapping from API names to query URLs.
        metakg_df: Current MetaKG table.

    Returns:
        The updated API-name mapping and MetaKG table.
    """
    return add_plover_API(api_names, metakg_df)


def get_api_predicates() -> Any:
    """Return the predicates supported by Translator APIs.

    Returns:
        API-name mappings, the MetaKG table, and a mapping from each API name
        to its supported predicates.
    """
    return get_translator_API_predicates()


def optimize_query_for_api(
    query_json: dict[str, Any],
    api_name: str,
    api_predicates: dict[str, list[str]],
) -> Any:
    """Remove predicates from a TRAPI query that an API does not support.

    Args:
        query_json: TRAPI query to optimize.
        api_name: Name of the API that will receive the query.
        api_predicates: Mapping from API names to their supported predicates.

    Returns:
        A copy of the query containing only predicates supported by the API.
    """
    return optimize_query_json(query_json, api_name, api_predicates)


def query_knowledge_provider(
    api_name: str,
    query_json: dict[str, Any],
    api_names: dict[str, str],
    api_predicates: dict[str, list[str]],
) -> Any:
    """Send a TRAPI query to one Translator Knowledge Provider.

    Args:
        api_name: Name of the API to query.
        query_json: TRAPI query sent to the provider.
        api_names: Mapping from API names to query URLs.
        api_predicates: Mapping from API names to supported predicates.

    Returns:
        The provider's knowledge graph, or ``None`` when the response contains
        no knowledge-graph edges.
    """
    return query_KP(api_name, query_json, api_names, api_predicates)


def parallel_query_apis(
    query_json: dict[str, Any],
    selected_apis: list[str],
    api_names: dict[str, str],
    api_predicates: dict[str, list[str]],
    max_workers: int = 1,
) -> Any:
    """Query multiple Translator APIs and merge their knowledge graphs.

    Args:
        query_json: TRAPI query sent to each selected API.
        selected_apis: Names of APIs to query.
        api_names: Mapping from API names to query URLs.
        api_predicates: Mapping from API names to supported predicates.
        max_workers: Maximum number of API queries executed concurrently.

    Returns:
        A merged knowledge graph from successful provider responses.
    """
    return parallel_api_query(
        query_json,
        selected_apis,
        api_names,
        api_predicates,
        max_workers,
    )


def trapi_query_endpoint(url: str) -> Any:
    """Invoke the legacy TRAPI endpoint placeholder.

    Args:
        url: URL of the TRAPI query endpoint.

    Returns:
        This tool has no successful return value in the current release.

    Raises:
        TypeError: Always in the current release because the underlying
            ``trapi.query`` function also requires a query body. The missing
            public parameter is retained for compatibility.
    """
    return trapi_query(url)


def neighborhood_finder(
    node: list[str],
    neighbor_categories: list[str],
) -> Any:
    """Find category-filtered neighbors for one or more CURIEs using TCT.

    Args:
        node: CURIEs whose neighboring nodes should be found.
        neighbor_categories: Biolink categories used to filter returned
            neighbors.

    Returns:
        A ``FinderResult`` containing the query, resolved nodes, knowledge
        graph, results, auxiliary graphs, and raw parsed response.
    """
    resources = _get_translator_resources()
    return tct_neighborhood_finder(
        node=node,
        neighbor_categories=neighbor_categories,
        resources=resources,
    )


def path_finder(
    start: str,
    end: str,
    intermediate_categories: list[str] | None = None,
) -> Any:
    """Find paths between two CURIEs using TCT.

    Args:
        start: CURIE of the starting node.
        end: CURIE of the ending node.
        intermediate_categories: Optional Biolink categories allowed for
            intermediate path nodes.

    Returns:
        A ``FinderResult`` containing the query, resolved nodes, knowledge
        graph, results, auxiliary graphs, and raw parsed response.
    """
    resources = _get_translator_resources()
    return query_TCT_pathfinder(
        start,
        end,
        intermediate_categories=intermediate_categories,
        resources=resources,
    )


def ARS_neighborhood_finder(
    json_file: dict[str, Any] | None = None,
    node: list[str] | None = None,
    neighbor_categories: list[str] | None = None,
) -> Any:
    """Find neighbors for concepts by querying every ARA through the ARS.

    Args:
        json_file: Parsed TRAPI query from an uploaded file. Submitted
            unchanged, so both edge and path query graphs work. When given,
            ``node`` and ``neighbor_categories`` must be omitted.
        node: One or more names or CURIEs; a one-hop query is built instead.
            Names are resolved to CURIEs before submission.
        neighbor_categories: Biolink categories wanted for neighbors, with or
            without the "biolink:" prefix (for example ["Drug"]).

    Returns:
        Resolved inputs plus ranked summary rows (rank, essence, predicates,
        primary sources, ARAs). Blocks until the ARS finishes: expect ~15 s to
        several minutes. Prefer submit_ars_query / get_ars_status /
        get_ars_results when polling is better than waiting.
    """
    result = _ars_neighborhood_finder(
        node=node,
        neighbor_categories=neighbor_categories,
        json_file=json_file,
    )
    if json_file is not None:
        return {
            "merged_pk": result.merged_pk,
            "status": result.status.status,
            "message": result.raw,
        }
    return {
        "resolved_nodes": result.resolved_nodes,
        "status": result.status.status,
        "result_count": len(result.results),
        "results": result.summarize(20),
    }


def ARS_pathfinder(
    start: str = "",
    end: str = "",
    intermediate_categories: list[str] | None = None,
    json_file: dict[str, Any] | None = None,
) -> Any:
    """Find paths between two concepts by querying every ARA through the ARS.

    Args:
        start: Name or CURIE of the starting node.
        end: Name or CURIE of the ending node.
        intermediate_categories: Optional single Biolink category restricting
            intermediate path nodes (for example ["Gene"]).
        json_file: Parsed TRAPI query from an uploaded file, submitted
            unchanged instead of building a paths query.

    Returns:
        Resolved start and end nodes plus ranked summary rows. Blocks until
        the ARS finishes: expect ~15 s to several minutes. Prefer
        submit_ars_query / get_ars_status / get_ars_results when polling is
        better than waiting.
    """
    if json_file is None and (not start or not end):
        raise ValueError("Provide start and end, or json_file")
    result = _ars_pathfinder(
        start,
        end,
        intermediate_categories=intermediate_categories,
        json_file=json_file,
    )
    if json_file is not None:
        return {
            "merged_pk": result.merged_pk,
            "status": result.status.status,
            "message": result.raw,
        }
    return {
        "resolved_nodes": result.resolved_nodes,
        "status": result.status.status,
        "result_count": len(result.results),
        "results": result.summarize(20),
    }


def submit_ars_query(
    node: list[str],
    neighbor_categories: list[str],
    predicates: list[str] | None = None,
) -> Any:
    """Submit a one-hop biomedical query to the Translator ARS and return immediately.

    The ARS fans the query out to every registered ARA and merges their answers;
    completion typically takes ~15 s to several minutes, so this does NOT wait
    for results. Track progress by passing the returned pk to get_ars_status
    (poll every ~15 s) until its status is Done, then fetch answers with
    get_ars_results.

    Args:
        node: One or more input nodes, as names ("asthma") or CURIEs
            ("MONDO:0004979"). Names are resolved to CURIEs before submission.
        neighbor_categories: Biolink categories wanted for neighbors, with or
            without the "biolink:" prefix (for example ["Drug"]).
        predicates: Optional edge predicates to require, for example
            ["biolink:treated_by"]. Omit for any predicate; the ARS returns an
            empty merge for some directional predicates. Defaults to
            biolink:related_to, which spans directions.

    Returns:
        {"pk", "resolved_nodes", "status"}. Keep the pk for the follow-up calls.

    Fails only on unresolvable inputs or submission rejection; later failure
    shows up as status Error in get_ars_status.
    """
    resolved = _resolve_nodes(node)
    pk = _submit_ARS(_format_query_json_forARS_neighborhood(
        subject_ids=[resolved_node.curie for resolved_node in resolved],
        object_categories=_normalize_categories(neighbor_categories),
        predicates=predicates,
    ))
    return {
        "pk": pk,
        "resolved_nodes": {
            f"node_{index}": resolved_node
            for index, resolved_node in enumerate(resolved)
        },
        "status": _get_ARS_status(pk).status,
    }


def get_ars_status(pk: str) -> Any:
    """Check progress of an ARS query submitted with submit_ars_query, without blocking.

    Args:
        pk: Parent message pk returned by submit_ars_query.

    Returns:
        Parent status ("Running", "Done", or "Error"), the merged message pk
        once available, and one entry per ARA with its own status and result
        count. Poll until status is Done, then call get_ars_results once.
        "Done" with zero results means the query matched nothing and will not
        change.
    """
    return _get_ARS_status(pk)


def get_ars_results(pk: str, top_n: int = 20) -> Any:
    """Fetch the merged answer of a finished ARS query as ranked summary rows.

    Args:
        pk: Parent message pk returned by submit_ars_query.
        top_n: Number of ranked rows to return (default 20). Keep the default
            unless explicitly asked for more; pass 0 only when exporting the
            full merged TRAPI message, which can be tens of megabytes.

    Returns:
        {"pk", "merged_pk", "status", "ready", "result_count", "results"}. Rows
        give rank, score, essence (answer node with name and categories),
        predicates, primary knowledge sources, and contributing ARAs. When
        ready is false the query is still running: poll get_ars_status instead
        of retrying this.
    """
    status = _get_ARS_status(pk)
    if not status.is_terminal:
        return {"pk": pk, "merged_pk": status.merged_version, "status": status.status, "ready": False}
    result = _get_ARS_result(status)
    payload = {
        "pk": result.pk,
        "merged_pk": result.merged_pk,
        "status": result.status.status,
        "ready": True,
        "result_count": len(result.results),
    }
    if top_n <= 0:
        payload["message"] = result.raw
    else:
        payload["results"] = result.summarize(top_n)
    return payload


TOOLS: tuple[Callable[..., Any], ...] = (
    get_translator_resources,
    name_lookup,
    get_name_synonyms,
    batch_name_lookup,
    normalize_nodes,
    get_kp_info,
    get_metakg_data,
    add_custom_api_to_metakg,
    add_plover_apis_to_metakg,
    get_api_predicates,
    optimize_query_for_api,
    query_knowledge_provider,
    parallel_query_apis,
    trapi_query_endpoint,
    neighborhood_finder,
    path_finder,
    ARS_neighborhood_finder,
    ARS_pathfinder,
    submit_ars_query,
    get_ars_status,
    get_ars_results,
)

__all__ = [tool.__name__ for tool in TOOLS] + ["TOOLS"]
