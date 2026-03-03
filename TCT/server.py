"""
Translator Component Toolkit MCP Server

This server provides access to biomedical translator tools including:
- Name resolution and lookup
- Node normalization 
- Knowledge provider information
- Meta knowledge graph operations
- Query orchestration
- TRAPI protocol support
"""

import functools

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR

# Import functions from translator_component_toolkit modules using relative imports
from .name_resolver import lookup, synonyms, batch_lookup
from .node_normalizer import get_normalized_nodes
from .translator_kpinfo import get_translator_kp_info
from .translator_metakg import get_KP_metadata, add_new_API_for_query, add_plover_API
from .translator_query import get_translator_API_predicates, optimize_query_json, query_KP, parallel_api_query
from .translator_resources import TranslatorResources
from .trapi import query as trapi_query


def mcp_error_handler(error_prefix: str):
    """Decorator that wraps tool functions with standardized MCP error handling."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                raise McpError(ErrorData(INTERNAL_ERROR, f"{error_prefix}: {str(e)}")) from e
        return wrapper
    return decorator


# Create unified MCP server
mcp = FastMCP("translator-toolkit")

# Name Resolver Tools
@mcp.tool()
@mcp_error_handler("Name lookup error")
def name_lookup(query: str, return_top_response: bool = True, return_synonyms: bool = False):
    """
    Look up a name/term and return normalized TranslatorNode information.

    Args:
        query: Query string to look up
        return_top_response: If true, returns only the top response; if false, returns all responses
        return_synonyms: If true, includes synonyms in the result

    Returns:
        TranslatorNode object(s) with curie, label, types, and optional synonyms
    """
    return lookup(query, return_top_response, return_synonyms)

@mcp.tool()
@mcp_error_handler("Synonyms lookup error")
def get_name_synonyms(query: str):
    """
    Get synonyms for a given CURIE.

    Args:
        query: Query CURIE to get synonyms for

    Returns:
        Dictionary of CURIE id to TranslatorNode information
    """
    return synonyms(query)

@mcp.tool()
@mcp_error_handler("Batch lookup error")
def batch_name_lookup(strings: list[str], size: int = 25, return_top_response: bool = True, return_synonyms: bool = False):
    """
    Batch lookup multiple names/terms and return normalized TranslatorNode information.

    Args:
        strings: List of query strings to look up
        size: Chunking size for batch processing (default: 25)
        return_top_response: If true, returns only the top response per string
        return_synonyms: If true, includes synonyms in the results

    Returns:
        Dictionary mapping strings to their TranslatorNode information
    """
    return batch_lookup(strings, size, return_top_response, return_synonyms)

# Node Normalizer Tools
@mcp.tool()
@mcp_error_handler("Node normalization error")
def normalize_nodes(query: str, return_equivalent_identifiers: bool = False, conflate: bool = True, drug_chemical_conflate: bool = False):
    """
    Normalize node CURIEs using the Node Normalizer API.

    Args:
        query: CURIE string or list of CURIEs to normalize
        return_equivalent_identifiers: Whether to return equivalent identifiers
        conflate: Enable gene-protein conflation (default: True)
        drug_chemical_conflate: Enable drug-chemical conflation (default: False)

    Returns:
        Normalized TranslatorNode(s) with curie, label, types, and optional synonyms
    """
    return get_normalized_nodes(query, return_equivalent_identifiers, conflate=conflate, drug_chemical_conflate=drug_chemical_conflate)

# Knowledge Provider Info Tools
@mcp.tool()
@mcp_error_handler("KP info error")
def get_kp_info():
    """
    Get SmartAPI Translator Knowledge Provider information.

    Returns:
        Tuple of (DataFrame with KP info, Dictionary mapping API names to URLs)
    """
    return get_translator_kp_info()

# Meta Knowledge Graph Tools
@mcp.tool()
@mcp_error_handler("MetaKG data error")
def get_metakg_data(api_names: dict):
    """
    Get metadata for Knowledge Providers including predicates, subjects, and objects.

    Args:
        api_names: Dictionary mapping API names to URLs

    Returns:
        DataFrame containing MetaKG information
    """
    return get_KP_metadata(api_names)

@mcp.tool()
@mcp_error_handler("Add custom API error")
def add_custom_api_to_metakg(api_names: dict, metakg_df, new_api_name: str, new_api_url: str,
                             new_api_predicate: str, new_api_subject: str, new_api_object: str):
    """
    Add a custom API to the knowledge graph metadata.

    Args:
        api_names: Current API names dictionary
        metakg_df: Current MetaKG DataFrame
        new_api_name: Name of the new API
        new_api_url: URL of the new API
        new_api_predicate: Predicate for the new API
        new_api_subject: Subject type for the new API
        new_api_object: Object type for the new API

    Returns:
        Tuple of (updated api_names dict, updated metakg DataFrame)
    """
    return add_new_API_for_query(api_names, metakg_df, new_api_name, new_api_url,
                                 new_api_predicate, new_api_subject, new_api_object)

@mcp.tool()
@mcp_error_handler("Add Plover APIs error")
def add_plover_apis_to_metakg(api_names: dict, metakg_df):
    """
    Add Plover APIs (CATRAX team APIs) to the knowledge graph metadata.

    Args:
        api_names: Current API names dictionary
        metakg_df: Current MetaKG DataFrame

    Returns:
        Tuple of (updated api_names dict, updated metakg DataFrame)
    """
    return add_plover_API(api_names, metakg_df)

# Query Tools
@mcp.tool()
@mcp_error_handler("API predicates error")
def get_api_predicates():
    """
    Get the predicates supported by each Translator API.

    Returns:
        Tuple of (API names dict, MetaKG DataFrame, API predicates dict)
    """
    return get_translator_API_predicates().as_tuple()

@mcp.tool()
@mcp_error_handler("Query optimization error")
def optimize_query_for_api(query_json: dict, api_name: str, api_predicates: dict):
    """
    Optimize a query JSON by removing predicates not supported by the selected API.

    Args:
        query_json: TRAPI 1.5.0 format query
        api_name: Name of the API to query
        api_predicates: Dictionary of API names and their predicates

    Returns:
        Modified query JSON with only supported predicates
    """
    return optimize_query_json(query_json, api_name, api_predicates)

@mcp.tool()
@mcp_error_handler("KP query error")
def query_knowledge_provider(api_name: str, query_json: dict, api_names: dict, api_predicates: dict):
    """
    Query an individual Knowledge Provider API with a TRAPI 1.5.0 query.

    Args:
        api_name: Name of the API to query
        query_json: TRAPI 1.5.0 format query
        api_names: Dictionary mapping API names to URLs
        api_predicates: Dictionary of API names and their predicates

    Returns:
        Query result from the API or None if no results
    """
    import pandas as pd
    resources = TranslatorResources(api_names=api_names, meta_kg=pd.DataFrame(), api_predicates=api_predicates)
    return query_KP(api_name, query_json, resources)

@mcp.tool()
@mcp_error_handler("Parallel query error")
def parallel_query_apis(query_json: dict, selected_apis: list[str], api_names: dict, api_predicates: dict, max_workers: int = 1):
    """
    Query multiple APIs in parallel and merge results into a single knowledge graph.

    Args:
        query_json: TRAPI 1.5.0 format query
        selected_apis: List of API names to query
        api_names: Dictionary mapping API names to URLs
        api_predicates: Dictionary of API names and their predicates
        max_workers: Number of parallel workers (default: 1)

    Returns:
        Merged knowledge graph from all successful API responses
    """
    import pandas as pd
    resources = TranslatorResources(api_names=api_names, meta_kg=pd.DataFrame(), api_predicates=api_predicates)
    return parallel_api_query(query_json, selected_apis, resources, max_workers)

# TRAPI Tools
@mcp.tool()
@mcp_error_handler("TRAPI query error")
def trapi_query_endpoint(url: str):
    """
    Query a TRAPI endpoint (currently unimplemented - placeholder).

    Args:
        url: The URL for the TRAPI API endpoint

    Returns:
        TODO: Implementation needed
    """
    return trapi_query(url)


@mcp.tool()
@mcp_error_handler("Graph conversion error")
def convert_result_to_graph(result: dict, resolve_names: bool = False):
    """Convert TRAPI query result to a NetworkX graph summary.

    Args:
        result: Raw TRAPI edges dict from a query
        resolve_names: Whether to resolve CURIEs to preferred names

    Returns:
        Dictionary with node/edge counts, node list, and predicates
    """
    from .results import KnowledgeGraph
    kg = KnowledgeGraph(edges=result)
    G = kg.to_networkx(resolve_names=resolve_names)
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_list": list(G.nodes()),
        "predicates": list({d.get("predicate", "") for _, _, d in G.edges(data=True)}),
    }

