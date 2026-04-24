"""
This is a wrapper around making calls to the Translator Reasoner API (TRAPI).

API Documentation: https://github.com/NCATSTranslator/ReasonerAPI

Additional API Documentation: https://github.com/NCATSTranslator/ReasonerAPI/blob/master/docs/reference.md
"""
import json

import requests

# TODO: incorporate object ids into the method.
def build_query(subject_ids:list[str],
        object_categories:list[str], predicates:list[str],
        return_json:bool=False,
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
        If true, returns a json string; if false, returns a dict (default).

    object_ids
        None by default
    subject_categories
        None by default

    Returns
    -------
    A dict (default) or json string if return_json=True

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


def process_result(result:dict):
    """
    Processes a TRAPI query result, returning a table of edges.

    Params
    ------

    Returns
    -------

    Examples
    --------
    """


def query(url:str, query:dict):
    """
    Queries a single TRAPI endpoint.

    Params
    ------
    url : str
        The URL for the API endpoint.
    query : dict
        A dict representing the query, as produced by build_query

    Returns
    -------
    A dict representing a result.

    Examples
    --------
    >>> query_dict = build_query(['NCBIGene:3845'], ['biolink:Gene'], ['biolink:physically_interacts_with'])
    >>> response = query(url, query_dict)
    >>> print(response)
    """
    if isinstance(query, str):
        raise TypeError(
            "query must be a dict, not a JSON string. "
            "Use build_query(...) without return_json=True, "
            "or pass json.loads(query) instead."
        )
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


def parallel_query(url_list:list[str]):
    """
    """
