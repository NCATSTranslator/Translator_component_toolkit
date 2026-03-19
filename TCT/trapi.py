"""
This is a wrapper around making calls to the Translator Reasoner API (TRAPI).

API Documentation: https://github.com/NCATSTranslator/ReasonerAPI

Additional API Documentation: https://github.com/NCATSTranslator/ReasonerAPI/blob/master/docs/reference.md
"""
import json
from dataclasses import dataclass

import requests


@dataclass
class HopSpec:
    """Specification for one hop (edge) in a multi-hop TRAPI query chain."""

    predicates: list[str] | None = None
    object_categories: list[str] | None = None
    object_ids: list[str] | None = None


def _build_node_spec(
    ids: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict:
    """Build a TRAPI node specification, omitting empty keys."""
    spec = {}
    if ids is not None:
        spec["ids"] = ids
    if categories is not None:
        spec["categories"] = categories
    return spec


def build_multi_hop_query(
    subject_ids: list[str] | None = None,
    subject_categories: list[str] | None = None,
    hops: list[HopSpec] | None = None,
    return_json: bool = True,
) -> str | dict:
    """Build a multi-hop TRAPI query graph from a chain of HopSpec objects.

    Parameters
    ----------
    subject_ids
        CURIE IDs for the starting node (n00).
    subject_categories
        Categories for the starting node (n00).
    hops
        List of HopSpec objects, each defining one edge in the chain.
    return_json
        If True, return a JSON string; otherwise return a dict.

    Returns
    -------
    str or dict
        A TRAPI query message.
    """
    if not hops:
        raise ValueError("At least one HopSpec is required in 'hops'.")
    if subject_ids is None and subject_categories is None:
        raise ValueError(
            "At least one of 'subject_ids' or 'subject_categories' is required."
        )

    nodes = {f"n{0:02d}": _build_node_spec(ids=subject_ids, categories=subject_categories)}
    edges = {}

    for i, hop in enumerate(hops):
        src = f"n{i:02d}"
        tgt = f"n{i + 1:02d}"

        edge: dict = {"subject": src, "object": tgt}
        if hop.predicates is not None:
            edge["predicates"] = hop.predicates

        nodes[tgt] = _build_node_spec(ids=hop.object_ids, categories=hop.object_categories)
        edges[f"e{i:02d}"] = edge

    query_dict = {"message": {"query_graph": {"edges": edges, "nodes": nodes}}}

    if return_json:
        return json.dumps(query_dict)
    return query_dict


# TODO: incorporate object ids into the method.
def build_query(subject_ids:list[str],
        object_categories:list[str], predicates:list[str],
        return_json:bool=True,
        object_ids=None, subject_categories=None):
    """
    This constructs a query json for use with TRAPI. Queries are of the form [subject_ids]-[predicates]-[object_categories].
    The output for the query contains all the subject-predicate-object triples where the subject is in subject_ids,
    the object's category is in object_categories, and the predicate for the edge is in predicates.

    For a description of the existing biolink categories and predicates, see https://biolink.github.io/biolink-model/

    Params
    ------
    subject_ids
        A list of subject CURIE IDs - example: ["NCBIGene:3845"]

    object_categories
        A list of strings representing the object categories that we are interested in. Example: ["biolink:Gene"]

    predicates
        A list of predicates that we are interested in. Example: ["biolink:positively_correlated_with", "biolink:physically_interacts_with"].

    return_json
        If true, returns a json string; if false, returns a dict.

    object_ids
        None by default
    subject_categories
        None by default

    Returns
    -------
    A json string

    Examples
    --------
    In this example, we want all genes that physically interact with gene 3845.
    >>> build_query(['NCBIGene:3845'], ['biolink:Gene'], ['biolink:physically_interacts_with'])
    "{'message': {'query_graph': {
        'edges': {'e00': {'subject': 'n00', 'object': 'n01', 'predicates':['biolink:physically_interacts_with]}},
        'nodes': {'n00': {'ids': ['NCBIGene:3845']}, 'n01': {'categories': ['biolink':Gene']}}}}}"
    """
    query_dict = {
        'message': {
            'query_graph': {
                'edges': {
                    'e00': {
                        'subject': 'n00',
                        'object': 'n01',
                        'predicates': predicates
                    }
                },
                'nodes': {
                    'n00': {
                        'ids': subject_ids
                    },
                    'n01': {
                        'categories': object_categories
                    }
                },
            }
        }
    }
    if return_json:
        return json.dumps(query_dict)
    else:
        return query_dict


def process_result(result:dict):  # pragma: no cover
    """
    Processes a TRAPI query result, returning a table of edges.

    Params
    ------

    Returns
    -------

    Examples
    --------
    """


def query(url:str, query:str):
    """
    Queries a single TRAPI endpoint.

    Params
    ------
    url : str
        The URL for the API endpoint.
    query : str
        A JSON string representing the query, as produced by build_query

    Returns
    -------
    A dict representing a result.

    Examples
    --------
    >>> query = build_query(['NCBIGene:3845'], ['biolink:Gene'], ['biolink:physically_interacts_with'])
    >>> response = query(url, query)
    >>> print(response)
    """
    # example: 1. get APIs, 2. get APIs that have the target object and subject types, and the target predicates. 3. build the query and run the query.
    response = requests.post(url, json=query)
    if response.status_code == 200:
        # TODO
        result = response.json().get("message", {})
        kg = result.get("knowledge_graph", {})
        edges = kg.get("edges", {})
        if edges:
            return result
        elif "knowledge_graph" in result:
            return None
    else:
        raise requests.RequestException('Response from server had error, code ' + str(response.status_code) + ' ' + str(response))


def parallel_query(url_list:list[str]):  # pragma: no cover
    """
    """
