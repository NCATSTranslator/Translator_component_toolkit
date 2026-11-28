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
from ..execution import capture_trapi, capture_operation
from ..workflow import replay_workflow, run_workflow, validate_workflow
from ..evidence import evidence as _evidence


@capture_operation()
def get_translator_resources() -> Any:
    """Load the Translator resources used by the finder tools.

    Returns:
        Translator API names, MetaKG data, and supported predicates packaged
        as the library's ``TranslatorResources`` object.
    """
    return _get_translator_resources()


@capture_operation()
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


@capture_operation()
def get_name_synonyms(query: str) -> Any:
    """Return synonyms and Translator node information for a CURIE.

    Args:
        query: CURIE whose synonyms should be returned.

    Returns:
        A mapping from the input CURIE to its ``TranslatorNode`` information.
    """
    return synonyms(query)


@capture_operation()
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


@capture_operation()
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


@capture_operation()
def get_kp_info() -> Any:
    """Return SmartAPI information for Translator Knowledge Providers.

    Returns:
        A pair containing the Knowledge Provider information table and a
        mapping from API names to query URLs.
    """
    return get_translator_kp_info()


@capture_operation()
def get_metakg_data(api_names: dict[str, str]) -> Any:
    """Return MetaKG metadata for a set of Knowledge Providers.

    Args:
        api_names: Mapping from Knowledge Provider names to query URLs.

    Returns:
        A table containing API, predicate, subject, object, and URL metadata.
    """
    return get_KP_metadata(api_names)


@capture_operation()
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


@capture_operation()
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


@capture_operation()
def get_api_predicates() -> Any:
    """Return the predicates supported by Translator APIs.

    Returns:
        API-name mappings, the MetaKG table, and a mapping from each API name
        to its supported predicates.
    """
    return get_translator_API_predicates()


@capture_operation()
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


@capture_trapi("message")
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
    result = query_KP(api_name, query_json, api_names, api_predicates)

    return result


@capture_trapi("edges")
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
    result = parallel_api_query(
        query_json,
        selected_apis,
        api_names,
        api_predicates,
        max_workers,
    )

    return result


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


@capture_trapi("finder")
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
    result = tct_neighborhood_finder(
        node=node,
        neighbor_categories=neighbor_categories,
        resources=resources,
    )

    return result


@capture_trapi("finder")
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
    result = query_TCT_pathfinder(
        start,
        end,
        intermediate_categories=intermediate_categories,
        resources=resources,
    )

    return result


@capture_operation()
def validate_query_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Validate a composable query recipe without contacting any providers.

    Recipes have schema_version=1, steps, and named outputs. Each step has
    id and op. Data references are {"$ref": "step_id", "path": "/json/pointer"}.
    Supported operations: literal (value); query (url, query, timeout_seconds);
    rows (input object); filter (input, conditions); project (input, fields);
    pluck (input, path, unique); join (left, right, left_on, right_on).
    Transformation inputs and named outputs must be references. Filters AND
    conditions with path/operator/value; operators are eq, ne, in, not_in,
    gt, gte, lt, lte, exists. Joins are exact inner joins. Paths are JSON
    pointers, not Python expressions. Descriptions are caller-supplied intent.

    Args:
        workflow: Versioned JSON recipe with steps and named output references.

    Returns:
        Normalized recipe, execution order, and explicit step dependencies.
        Dynamic paths and types are checked only when upstream outputs exist.
    """
    return validate_workflow(workflow)


@capture_trapi("workflow")
def run_query_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Execute a query DAG and return replayable evidence with row lineage.

    Use validate_query_workflow to inspect the recipe first. Query operations
    POST explicit TRAPI bodies to explicit URLs without pruning predicates,
    retries, redirects, or automatic provider expansion. Full synchronous
    responses, resolved requests, filter decisions, and join lineage are saved.
    Errors remain distinct from valid empty results; dependent steps are skipped.
    Check the returned status and output_errors before interpreting outputs.

    Agent effort (advisory):
        Routine: Execute an agreed, bounded recipe using resolved identifiers.
        Escalate: Review identifiers, direction, qualifiers, source selection,
            and evidence before interpreting a joined path as a mechanism.
        Execution: Up to 100 steps, 10,000 transformation rows, 8 MiB per
            response, and 120 seconds per query socket timeout. Evidence is
            returned inline; callers are responsible for saving the bundle.

    Args:
        workflow: Version-1 recipe described by validate_query_workflow.

    Returns:
        Structured bundle containing recipe, per-step evidence and failures,
        row lineage, named outputs, timestamps, versions, and content hashes.
        A traceable graph connection does not establish biological causality.
    """
    result = run_workflow(workflow)

    return result


@capture_trapi("workflow")
def replay_query_workflow(
    bundle: dict[str, Any], mode: str = "snapshot"
) -> dict[str, Any]:
    """Inspect saved query evidence offline, or explicitly rerun the recipe.

    Snapshot mode makes no network calls: it verifies bundle checksums, reuses
    saved query responses, and recomputes filters, projections, and joins.
    Live mode contacts the recorded endpoints again; changing remote data can
    change results. Checksums detect modification, not evidence authenticity.

    Args:
        bundle: Complete evidence bundle returned by run_query_workflow.
        mode: snapshot (offline, default) or live (new remote requests).

    Returns:
        New bundle linked to the original, with replayed or freshly queried
        evidence. Snapshot replay requires the same workflow engine version.
    """
    result = replay_workflow(bundle, mode)

    return result


@capture_operation()
def evidence(request: dict[str, Any]) -> dict[str, Any]:
    """Inspect captured evidence, replay composition, or export validated TRAPI.

    Export with view="trace" for recorded calls or view="providers" for service
    outcomes, view="edges" for merge provenance, or view="page" for a
    standalone HTML report. Use view="diff" with an against object containing
    events or a store and run_id to compare two recorded runs offline.
    Inspect first to obtain source IDs and local query graphs. Composition requires
    closed=true, query_graph, sources, workflow and selection. sources maps each
    source ID to nodes/edges/paths dictionaries mapping local query IDs to global
    query IDs. Direction must be preserved; all local IDs need explicit mappings.

    workflow uses the version-1 recipe described by validate_query_workflow, plus
    source steps {id, op: "source", source_id} that provide recorded responses.
    Network query steps are forbidden. Filters and joins use explicit references;
    for example, rows can read a source at /message/knowledge_graph/edges.

    selection has output (workflow output name), resource_id (composition producer),
    nodes (query node ID to row JSON pointer), and edges/paths (query ID to an object
    with source_id and path, a row pointer to original edge/auxiliary-graph IDs).
    Each query element must be bound. The operation retains retrieved evidence
    separately from selected answers. Schema validation does not establish
    biomedical correctness or complete source coverage.

    Args:
        request: Object with action (inspect, replay, export), either events or
            store/run_id. Replay and TRAPI export require a composition. Version
            defaults to 1.5.0; 2.0.0-beta2 is an explicit prerelease target.

    Returns:
        Inventory, replay diagnostics, a run view, or a validated TRAPI response. No network
        calls occur. Invalid or unsupported exports raise an error.
    """
    return _evidence(request)


@capture_operation()
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


@capture_operation()
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


@capture_operation()
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


@capture_operation()
def get_ars_status(pk: str) -> Any:
    """Check progress of an ARS query submitted with submit_ars_query, without blocking.

    Args:
        pk: Parent message pk returned by submit_ars_query.

    Returns:
        Parent status ("Running", "Done", or "Error"), the merged message pk
        once available, and one entry per ARA with its own status and result
        count. Poll until status is Done, then call get_ars_results; it
        reports ready false until the ARS merge agent has saved the merged
        message, so keep polling until ready is true. "Done" with ready true
        and zero results means the query matched nothing and will not change.
    """
    return _get_ARS_status(pk)


@capture_operation()
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
        ready is false the query is still running, or the ARS merge agent is
        still saving the merged message after the parent reported Done
        (NCATSTranslator/Relay#621): poll get_ars_status and retry instead of
        reporting zero results. A failed ARS query raises an error.
    """
    status = _get_ARS_status(pk)
    if not status.is_terminal or status.merge_pending:
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
    validate_query_workflow,
    run_query_workflow,
    replay_query_workflow,
    evidence,
    ARS_neighborhood_finder,
    ARS_pathfinder,
    submit_ars_query,
    get_ars_status,
    get_ars_results,
)

__all__ = [tool.__name__ for tool in TOOLS] + ["TOOLS"]
