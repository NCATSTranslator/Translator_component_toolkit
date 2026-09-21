from collections import Counter

import pandas as pd
from typing import Any, Optional, Union
import requests
import json
import time


from TCT.TCT import (
    CategoryList,
    FinderResult,
    NodeInput,
    TranslatorResources,
    _get_resources,
    _normalize_categories,
    _resolve_nodes,
    sele_predicates_API,
)

#from .TCT_pathfinder import generate_score_results, build_query_graph
#from .TCT_neighborhood_finder import parse_results_for_neighborhood_finder

CI_URL="https://ars.ci.transltr.io/ars/api"
TEST_URL = "https://ars.test.transltr.io/ars/api"



def Query_ARS(url: str, json_file: dict[str, Any]) -> Optional[str]:
    """
    Send a POST request with JSON payload from a file.

    Args:
        url (str): The endpoint to send the POST request to.
        json_file (dict[str, Any]): The JSON payload as a dictionary.

    Returns:
        Optional[str]: The 'pk' from the response if successful, None otherwise.
    """
    print(url)
    payload = json_file

    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url+"/submit", headers=headers, json=payload)
    try:
        response_pk=response.json()['pk']
        return response_pk

    except Exception as e:
        print(response.text)

    return None


def check_ars_results(response_pk: str):
    # add a retry counter
    retry_count = 0
    max_retries = 15
    url = TEST_URL+"/messages/" + response_pk + "?trace=y"
    print("Checking ARS results for PK: " + response_pk)
    print(url)
    parent_json = requests.get(url).json()
    doneness= parent_json["status"]
    if doneness=="Done":
        print ("is done")
        if "merged_version" in parent_json.keys():
            if parent_json["merged_version"] is not None:
                print("has merged_version")
                merged_version_pk = parent_json["merged_version"]
                response = requests.get(TEST_URL+"/messages/" + merged_version_pk)
                return response.json()
            else: 
                print("Query done, but no results returned")
                return None

    else:
        print("Not all results have been returned.  Checking again in 30 seconds")
        time.sleep(30)
        retry_count += 1
        if retry_count < max_retries:
            return check_ars_results(response_pk)
        else:
            print("Max retries reached. Exiting.")
            return None

def format_query_json_forARS(subject_ids:list[str],
        object_ids:list[str]|None = None,
        subject_categories:list[str]|None = None,
        object_categories:list[str]|None = None,
        predicates:list[str]|None = None,
        attribute_constraints:list[dict]|None = None,
        ) -> dict:
    '''
    Formats a query dict, with optional constraints.

    Example input:
    subject_ids = ["NCBIGene:3845"]
    object_ids = []
    subject_categories = ["biolink:Gene"]
    object_categories = ["biolink:Gene"]
    predicates = ["biolink:positively_correlated_with", "biolink:physically_interacts_with"]
    attribute_constraints = [build_attribute_constraint('biolink:has_total', '>', 2)]
    '''
    #edited Dec 5, 2023
    if len(predicates) == 0:
            predicates = ['biolink:related_to']

    query_json_temp = {
        "message": {
            "query_graph": {

                "edges": {
                    "e00": {
                    #"e1": {
                        "subject": "n00",
                        "object": "n01",
                        "predicates": predicates
                        }
                    },
                "nodes": {
                    "n00": {
                        "ids":subject_ids, # required
                        #"categories":[] # optional, if not provided, it will be empty
                        },
                    "n01": {
                        #"ids":[],
                        "categories":object_categories # required
                        }}
                }
            },
       
        "submitter": "TCT"
        }
    
    if attribute_constraints is not None and len(attribute_constraints) > 0:
        query_json_temp['message']['query_graph']['edges']['e00']['attribute_constraints'] = attribute_constraints

    if subject_ids is not None and len(subject_ids) > 0:
        query_json_temp["message"]["query_graph"]["nodes"]["n00"]["ids"] = subject_ids

    if object_ids is not None and len(object_ids) > 0:
        query_json_temp["message"]["query_graph"]["nodes"]["n01"]["ids"] = object_ids

    if subject_categories is not None and len(subject_categories) > 0:
        query_json_temp["message"]["query_graph"]["nodes"]["n00"]["categories"] = subject_categories

    if object_categories is not None and len(object_categories) > 0:
        query_json_temp["message"]["query_graph"]["nodes"]["n01"]["categories"] = object_categories

    if predicates is not None and len(predicates) > 0:
        query_json_temp["message"]["query_graph"]["edges"]["e00"]["predicates"] = predicates

    return query_json_temp

def ARS_neighborhood_finder(
    node: Union[NodeInput, list[NodeInput]],
    neighbor_categories: CategoryList,
    *,
    node_categories: Optional[CategoryList] = None,
    api_names: Optional[dict[str, str]] = None,
    meta_kg: Optional[pd.DataFrame] = None,
    api_predicates: Optional[dict[str, list[str]]] = None,
    resources: Optional[TranslatorResources] = None,
    predicates_subset: Optional[list[str]] = None,
    attribute_constraints: Optional[list[dict[str, Any]]] = None,
    name_resolver_kwargs: Optional[dict[str, Any]] = None,
    node_normalizer_kwargs: Optional[dict[str, Any]] = None,
) -> FinderResult:
    """
    Find one-hop neighbors for one or more biomedical concepts.

    Parameters
    ----------
    node : NodeInput or list[NodeInput]
        Source node or nodes. Each value may be a CURIE or human-readable
        string. Human-readable strings are resolved with Name Resolver and then
        normalized with Node Normalizer.
    neighbor_categories : CategoryList
        Desired neighbor categories. Values may be short names like ``"Drug"``
        or full Biolink names like ``"biolink:Drug"``.
    node_categories : CategoryList, optional
        Category override for source nodes. If omitted, categories are inferred
        from the first normalized source node.
    resources : TranslatorResources, optional
        Preloaded Translator resources. If omitted, the module-level singleton
        is loaded on first use and reused.
    api_names, meta_kg, api_predicates : optional
        Advanced partial overrides for the Translator resources used by the
        neighborhood implementation.
    predicates_subset : list[str], optional
        Optional predicate filter applied after MetaKG predicate selection.
    attribute_constraints : list[dict], optional
        TRAPI attribute constraints passed through to query construction.
    name_resolver_kwargs : dict, optional
        Extra keyword arguments for ``name_resolver.lookup``.
    node_normalizer_kwargs : dict, optional
        Extra keyword arguments for ``node_normalizer.get_normalized_nodes``.

    Returns
    -------
    FinderResult
        Convenience wrapper containing resolved input nodes, parsed neighborhood
        knowledge graph, results, auxiliary graphs, and raw TRAPI-style output.

    Examples
    --------
    >>> from TCT import neighborhood_finder
    >>> result = neighborhood_finder("asthma", ["SmallMolecule", "Drug"])
    >>> result.knowledge_graph["nodes"]
    {...}
    """
    resolved_nodes = _resolve_nodes(
        node,
        name_resolver_kwargs=name_resolver_kwargs,
        node_normalizer_kwargs=node_normalizer_kwargs,
    )
    source_categories = (
        _normalize_categories(node_categories) or resolved_nodes[0].categories
    )
    neighbor_categories = _normalize_categories(neighbor_categories) or []
    resolved_resources = _get_resources(
        resources=resources,
        api_names=api_names,
        meta_kg=meta_kg,
        api_predicates=api_predicates,
    )

    #input_curies = [resolved_node.curie for resolved_node in resolved_nodes]

    query = format_query_json_forARS(
        subject_ids=node,
        object_ids=None,
        subject_categories=None,
        object_categories=neighbor_categories,
        predicates=predicates_subset,
        attribute_constraints=attribute_constraints,
    )

    print("Query JSON:")
    print(json.dumps(query, indent=2))
    result_pk = Query_ARS(url=TEST_URL, json_file=query)
    print("Result PK:" + result_pk)
    ARS_results = check_ars_results(result_pk)

    return ARS_results
