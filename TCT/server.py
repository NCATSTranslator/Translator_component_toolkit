"""Compatibility imports for the TCT MCP server.

The MCP implementation now lives in :mod:`TCT.interfaces.mcp`. Existing
consumers may continue importing ``mcp`` and registered tool objects from
``TCT.server``.
"""

from .interfaces.mcp import (
    add_custom_api_to_metakg,
    ars_neighborhood_finder,
    add_plover_apis_to_metakg,
    batch_name_lookup,
    get_api_predicates,
    get_ars_results,
    get_ars_status,
    get_kp_info,
    get_metakg_data,
    get_name_synonyms,
    get_translator_resources,
    mcp,
    name_lookup,
    neighborhood_finder,
    normalize_nodes,
    optimize_query_for_api,
    parallel_query_apis,
    path_finder,
    query_ars,
    query_knowledge_provider,
    submit_ars_query,
    trapi_query_endpoint,
    wait_for_ars_results,
)

__all__ = [
    "add_custom_api_to_metakg",
    "ars_neighborhood_finder",
    "add_plover_apis_to_metakg",
    "batch_name_lookup",
    "get_api_predicates",
    "get_ars_results",
    "get_ars_status",
    "get_kp_info",
    "get_metakg_data",
    "get_name_synonyms",
    "get_translator_resources",
    "mcp",
    "name_lookup",
    "neighborhood_finder",
    "normalize_nodes",
    "optimize_query_for_api",
    "parallel_query_apis",
    "path_finder",
    "query_ars",
    "query_knowledge_provider",
    "submit_ars_query",
    "trapi_query_endpoint",
    "wait_for_ars_results",
]
