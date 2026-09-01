"""Expose the Translator Component Toolkit through an MCP server.

The server presents a curated set of TCT operations for name resolution, node
normalization, Translator resource discovery, TRAPI querying, and graph
finding. Tool names, signatures, defaults, and docstrings in this module are
part of the public MCP discovery contract.

The server uses FastMCP's default stdio transport when run through
``tct-server`` or ``python main.py``. Install the optional ``mcp`` dependency
set before starting it. Core TCT runtime configuration, including
``TCT_ENVIRONMENT``, is resolved by the underlying library functions.

This module currently contains both the tool surface and FastMCP registration.
It intentionally converts unexpected tool failures to MCP internal errors so
clients receive consistent protocol-level failures.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, ErrorData

from .name_resolver import batch_lookup, lookup, synonyms
from .node_normalizer import get_normalized_nodes
from .TCT import get_translator_resources as _get_translator_resources
from .TCT_neighborhood_finder import (
    neighborhood_finder as tct_neighborhood_finder,
)
from .TCT_pathfinder import query_TCT_pathfinder
from .translator_kpinfo import get_translator_kp_info
from .translator_metakg import add_new_API_for_query, add_plover_API, get_KP_metadata
from .translator_query import (
    get_translator_API_predicates,
    optimize_query_json,
    parallel_api_query,
    query_KP,
)
from .trapi import query as trapi_query


mcp = FastMCP("TCT")


@mcp.tool()
def get_translator_resources() -> Any:
    """Load the Translator resources used by the finder tools.

    Returns:
        Translator API names, MetaKG data, and supported predicates packaged
        as the library's ``TranslatorResources`` object.

    Raises:
        McpError: If Translator resources cannot be loaded.
    """
    try:
        return _get_translator_resources()
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Get translator resources error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If the Name Resolver request fails.
    """
    try:
        return lookup(query, return_top_response, return_synonyms)
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"Name lookup error: {str(e)}")
        ) from e


@mcp.tool()
def get_name_synonyms(query: str) -> Any:
    """Return synonyms and Translator node information for a CURIE.

    Args:
        query: CURIE whose synonyms should be returned.

    Returns:
        A mapping from the input CURIE to its ``TranslatorNode`` information.

    Raises:
        McpError: If the Name Resolver request fails.
    """
    try:
        return synonyms(query)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Synonyms lookup error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If a Name Resolver request fails.
    """
    try:
        return batch_lookup(strings, size, return_top_response, return_synonyms)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Batch lookup error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If the Node Normalizer request fails.
    """
    try:
        return get_normalized_nodes(
            query,
            return_equivalent_identifiers,
            conflate=conflate,
            drug_chemical_conflate=drug_chemical_conflate,
        )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Node normalization error: {str(e)}",
            )
        ) from e


@mcp.tool()
def get_kp_info() -> Any:
    """Return SmartAPI information for Translator Knowledge Providers.

    Returns:
        A pair containing the Knowledge Provider information table and a
        mapping from API names to query URLs.

    Raises:
        McpError: If SmartAPI information cannot be loaded.
    """
    try:
        return get_translator_kp_info()
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"KP info error: {str(e)}")
        ) from e


@mcp.tool()
def get_metakg_data(api_names: dict[str, str]) -> Any:
    """Return MetaKG metadata for a set of Knowledge Providers.

    Args:
        api_names: Mapping from Knowledge Provider names to query URLs.

    Returns:
        A table containing API, predicate, subject, object, and URL metadata.

    Raises:
        McpError: If MetaKG information cannot be loaded.
    """
    try:
        return get_KP_metadata(api_names)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"MetaKG data error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If the API cannot be added to the supplied metadata.
    """
    try:
        return add_new_API_for_query(
            api_names,
            metakg_df,
            new_api_name,
            new_api_url,
            new_api_predicate,
            new_api_subject,
            new_api_object,
        )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Add custom API error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If Plover metadata cannot be retrieved or added.
    """
    try:
        return add_plover_API(api_names, metakg_df)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Add Plover APIs error: {str(e)}",
            )
        ) from e


@mcp.tool()
def get_api_predicates() -> Any:
    """Return the predicates supported by Translator APIs.

    Returns:
        API-name mappings, the MetaKG table, and a mapping from each API name
        to its supported predicates.

    Raises:
        McpError: If API or MetaKG information cannot be loaded.
    """
    try:
        return get_translator_API_predicates()
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"API predicates error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If the query cannot be optimized.
    """
    try:
        return optimize_query_json(query_json, api_name, api_predicates)
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Query optimization error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If query preparation or the provider request fails.
    """
    try:
        return query_KP(api_name, query_json, api_names, api_predicates)
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"KP query error: {str(e)}")
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If parallel query processing fails.
    """
    try:
        return parallel_api_query(
            query_json,
            selected_apis,
            api_names,
            api_predicates,
            max_workers,
        )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Parallel query error: {str(e)}",
            )
        ) from e


@mcp.tool()
def trapi_query_endpoint(url: str) -> Any:
    """Invoke the legacy TRAPI endpoint placeholder.

    Args:
        url: URL of the TRAPI query endpoint.

    Returns:
        This tool has no successful return value in the current release.

    Raises:
        McpError: Always in the current release because the underlying
            ``trapi.query`` function also requires a query body. The missing
            public parameter is retained here for MCP compatibility and will
            be addressed separately from this documentation-only stage.
    """
    try:
        return trapi_query(url)
    except Exception as e:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"TRAPI query error: {str(e)}")
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If Translator resources cannot be loaded or a finder request
            fails.
    """
    try:
        resources = _get_translator_resources()
        return tct_neighborhood_finder(
            node=node,
            neighbor_categories=neighbor_categories,
            resources=resources,
        )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Neighborhood finder error: {str(e)}",
            )
        ) from e


@mcp.tool()
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

    Raises:
        McpError: If Translator resources cannot be loaded or a finder request
            fails.
    """
    try:
        resources = _get_translator_resources()
        return query_TCT_pathfinder(
            start,
            end,
            intermediate_categories=intermediate_categories,
            resources=resources,
        )
    except Exception as e:
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Path finder error: {str(e)}",
            )
        ) from e
