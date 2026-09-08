# TCT Pathfinder...
# reviewed by yjzhang, 2026-08-20
import requests

import pandas as pd
from collections import Counter

from typing import Any, Optional, Sequence

from . import translator_query
from .config import service_url
from .TCT import (
    CategoryList,
    FinderResult,
    NodeInput,
    TranslatorResources,
    _build_finder_result,
    _get_resources,
    _normalize_categories,
    _resolve_node,
    sele_predicates_API,
)



def format_query_json_for_pathfinder_with_constraints(subject_ids:str,
        object_ids:str,
        subject_categories=None,
        object_categories=None,
        predicates=None,
        constraints=None
        ) -> dict:
    """
    Format user's input into a query json for pathfinder pipeline with constraints on the intermediate node categories.

    Parameters
    ----------
    subject_ids : str
        a curie id for the subject node
    object_ids : str
        a curie id for the object node
    subject_categories : list
        a list of categories for the subject node
    object_categories : list
        a list of categories for the object node
    predicates : list
        a list of predicates for the edge between subject and object nodes
    constraints : list
        a list of intermediate categories for the pathfinder pipeline, currently only one intermediate category is allowed in the constraints list. 

    Returns
    -------
    query_json_temp : dict
        a query json for pathfinder pipeline
    
    Examples
    --------
    >>> query_json_temp = format_query_json_for_pathfinder_with_constraints(
        subject_ids='NCBIGene:6774',
        object_ids='NCBIGene:4170',
        subject_categories=['biolink:Gene'],
        object_categories=['biolink:Gene'],
        predicates=['biolink:related_to'],
        constraints=['biolink:Protein'])
    """
    if constraints is None or len(constraints) == 0:
        constraints_intermediate_category = None
    if len(constraints) == 1:
        constraints_intermediate_category = constraints
    
    else:
        constraints_intermediate_category = [constraints[0]]
        print("Warning: for ARAGORN or ARAX pathfinder pipeline, it is only allowed to have only one intermediate category in the constraints list. If there are multiple intermediate categories, the query will return an error. Therefore, we will only use one intermediate category in  the constraints list. ")
    q =  {
        "message": {
            "query_graph": {
            "nodes": {
                "n0": {
                "ids": [
                    subject_ids
                ]
                },
                "n1": {
                "ids": [
                    object_ids
                ]
                }
            },
            "paths": {
                "p0": {
                    "subject": "n0",
                    "object": "n1",
                    #"predicates": [
                    #    "biolink:related_to"
                    #],
                    "constraints": [
                        {
                            "intermediate_categories": constraints_intermediate_category
                        }
                ]
                }
            }
            }
        },
        "submitter": "TCT",
        #"stream_progress": True,
        "query_options": {
            "kp_timeout": "30",
            "prune_threshold": "50",
            "max_pathfinder_paths": "500",
            "max_path_length": 4
        }
        }
  
    return q

def build_query_graph(start_node_id:str, end_node_id:str, start_node_categories=None, end_node_categories=None, constraints_path=None):
    """
    start_node_categories and end_node_categories are lists of categories.
    """
    q = {
            "nodes": {
                "on": {
                    "categories": end_node_categories,
                    "constraints": [],
                    "ids": [
                        end_node_id
                    ],
                    "is_set": False,
                    "option_group_id": None,
                    "set_id": None,
                    "set_interpretation": "BATCH"
                },
                "sn": {
                    "categories": start_node_categories,
                    "constraints": [],
                    "ids": [start_node_id] if isinstance(start_node_id, str) else start_node_id,
                    "is_set": False,
                    "option_group_id": None,
                    "set_id": None,
                    "set_interpretation": "BATCH"
                }
            },
            "paths": {
                "p0": {
                    "constraints": constraints_path,
                    "object": "on",
                    "predicates": None,
                    "subject": "sn"
                }
            }
        }
    return q


def generate_score_results(results:dict, method='infores'):
    """
    Generates a score dict, and a list of "analyses".
    method can be 'infores' or 'edges'
    """
    graph_scores = {}
    max_score = 0
    auxiliary_graphs = results['auxiliary_graphs']
    for k, graph in auxiliary_graphs.items():
        if method == 'infores':
            sources = set()
            for edge_index in graph:
                edge = results['knowledge_graph']['edges'][edge_index]
                for resource in edge['sources']:
                    sources.add(resource['resource_id'])
            score = len(sources)
            if score > max_score:
                max_score = score
        else:
            score = len(graph)
            if score > max_score:
                max_score = score
        graph_scores[k] = score
    graph_scores_formatted = []
    for k in graph_scores.keys():
        graph_scores[k] = graph_scores[k]/max_score
        graph_scores_formatted.append({
            'attributes': None,
            'path_bindings': {
                'p0': [{'id': k}]},
            'resource_id': 'infores:tct',
            'score': graph_scores[k],
            'scoring_method': None,
            'support_graphs': None
            })
    return graph_scores, graph_scores_formatted


def parse_results_for_pathfinder(start_node_id:str, end_node_id:str, result1:dict, result2:dict,
        start_node_categories=None, end_node_categories=None,
        get_node_info=True,
        scoring_method='infores'):
    """
    Converts the results of two TRAPI queries into the same general json format as the other pathfinder APIs.
    scoring_method is how the node scores are generated, and could be 'infores' or 'edges'.
    """
    # nodes
    # TODO: get some node info? node attributes
    node_info = {}
    # edges is a dict of intermediate nodes
    intermediate_node_edges = {}
    for k, v in result1.items():
        i1 = v['subject']
        i2 = v['object']
        s_o = 'object'
        if i1 == start_node_id:
            intermediate_node_id = i2
            s_o = 'object'
        elif i2 == start_node_id:
            intermediate_node_id = i1
            s_o = 'subject'
        else:
            continue
        if (i1 == start_node_id or i2 == start_node_id) and intermediate_node_id in intermediate_node_edges:
            intermediate_node_edges[intermediate_node_id].append((k, v))
        else:
            intermediate_node_edges[intermediate_node_id] = [(k, v)]
        # add node dict
        if intermediate_node_id not in node_info:
            node_dict = {
            }
            node_info[intermediate_node_id] = node_dict
        else:
            node_dict = node_info[intermediate_node_id]
        for attribute in v['attributes']:
            if attribute['attribute_type_id'] == f'{s_o}_category':
                if 'categories' not in node_dict:
                    node_dict['categories'] = set([attribute['value']])
                else:
                    node_dict['categories'].add(attribute['value'])
            if attribute['attribute_type_id'] == f'{s_o}_name' and 'name' not in node_dict:
                node_dict['name'] = attribute['value']
        node_info[intermediate_node_id] = node_dict
    connecting_intermediate_nodes = {}
    for k, v in result2.items():
        i1 = v['subject']
        i2 = v['object']
        if i1 == end_node_id:
            intermediate_node_id = i2
            s_o = 'object'
        elif i2 == end_node_id:
            intermediate_node_id = i1
            s_o = 'subject'
        else:
            continue
        if (i1 == end_node_id or i2 == end_node_id) and intermediate_node_id in intermediate_node_edges:
            if intermediate_node_id in connecting_intermediate_nodes:
                connecting_intermediate_nodes[intermediate_node_id]['e2'].append((k, v))
            else:
                connecting_intermediate_nodes[intermediate_node_id] = {'e1': intermediate_node_edges[intermediate_node_id], 'e2' : [(k, v)]}
        if intermediate_node_id not in node_info:
            node_dict = {
            }
            node_info[intermediate_node_id] = node_dict
        else:
            node_dict = node_info[intermediate_node_id]
        for attribute in v['attributes']:
            if attribute['attribute_type_id'] == f'{s_o}_category':
                if 'categories' not in node_dict:
                    node_dict['categories'] = set([attribute['value']])
                else:
                    node_dict['categories'].add(attribute['value'])
            if attribute['attribute_type_id'] == f'{s_o}_name' and 'name' not in node_dict:
                node_dict['name'] = attribute['value']
        node_info[intermediate_node_id] = node_dict
    for k, v in node_info.items():
        if 'categories' in v:
            v['categories'] = list(v['categories'])
    all_edges = {}
    all_auxiliary_graphs = {}
    i = 1
    # sort connecting_intermediate_nodes by total number of connections
    connection_counts = Counter({k: len(v['e1'])*len(v['e2']) for k, v in connecting_intermediate_nodes.items()})
    for i1, count in connection_counts.most_common():
        kv = connecting_intermediate_nodes[i1]
        e1s = kv['e1']
        e2s = kv['e2']
        edges = {k: v for k, v in e1s}
        edges.update({k: v for k, v in e2s})
        all_edges.update(edges)
        keys = [x[0] for x in e1s] + [x[0] for x in e2s]
        all_auxiliary_graphs[f'aux_{i}_{i1}'] = keys
        i += 1
    # generate output json
    output = {
        'query_graph': build_query_graph(start_node_id, end_node_id, start_node_categories, end_node_categories),
        # TODO: don't drop the nodes
        'knowledge_graph': {'nodes': {x: node_info[x] for x in connection_counts.keys()},
                            'edges': all_edges,
                           },
        'results': [{'analyses': []}],
        'auxiliary_graphs': all_auxiliary_graphs
    }
    graph_scores, graph_scores_formatted = generate_score_results(output, method=scoring_method)
    output['results'][0]['analyses'] = graph_scores_formatted
    if get_node_info:
        from .node_normalizer import get_normalized_nodes
        nodes_to_add = []
        for k, v in output['knowledge_graph']['nodes'].items():
            if 'name' not in v or 'categories' not in v:
                nodes_to_add.append(k)
        if nodes_to_add:
            normalized_nodes = get_normalized_nodes(nodes_to_add, mode='post')
            for node_id in nodes_to_add:
                nn = normalized_nodes.get(node_id)
                if nn is not None:
                    output['knowledge_graph']['nodes'][node_id] = {'name': nn.label, 'categories': nn.types}
    return output


# define a function that uses the query_json as an template and change the ids and categories of the nodes
def format_pathfinder_query(node1_id:str, node1_category:str, node2_id:str, node2_category:str) -> dict:
    '''
    Formats a query to the Pathfinder API.

    Params
    ------
    node1_id : str
    node1_category : str
    node2_id : str
    node2_category : str

    Returns
    -------
    A dict formatted as a JSON query to the Pathfinder API.
    '''
    query_json = {
        "message": {
            "query_graph": {
                "nodes": {
                    "SN": {
                        "ids": [
                            node1_id
                        ],
                        "categories": [
                            node1_category
                        ]
                    },
                    "ON": {
                        "ids": [
                            node2_id
                        ],
                        "categories": [
                            node2_category
                        ]
                    }
                },
                "paths": {
                    "qpath": {
                        "subject": "SN",
                        "object": "ON"
                    }
                }
            }
        },
        "submitter": "TCT",
    }
    return query_json


PATHFINDER_ARAS = ("aragorn", "arax")


def query_pathfinder(
    ara: str,
    node1_id: str,
    node1_category: str,
    node2_id: str,
    node2_category: str,
    constraints: Optional[Sequence[str]] = None,
    timeout: Optional[float] = None,
) -> requests.Response:
    """
    Queries an ARA's Pathfinder API, with or without intermediate constraints.

    Params
    ------
    ara : str
        'aragorn' or 'arax'
    node1_id : str
    node1_category : str
    node2_id : str
    node2_category : str
    constraints : sequence of str, optional
        Intermediate node categories. Only up to one allowed.
    timeout : float, optional

    Returns
    -------
    pathfinder response
    """
    ara_key = ara.strip().lower()
    if ara_key not in PATHFINDER_ARAS:
        raise ValueError(
            f"unknown pathfinder ARA: {ara!r}; "
            f"expected one of {', '.join(PATHFINDER_ARAS)}"
        )
    if constraints:
        query_json = format_query_json_for_pathfinder_with_constraints(
            subject_ids=node1_id,
            object_ids=node2_id,
            subject_categories=node1_category,
            object_categories=node2_category,
            constraints=list(constraints),
        )
    else:
        query_json = format_pathfinder_query(node1_id, node1_category, node2_id, node2_category)
    return requests.post(service_url(ara_key), json=query_json, timeout=timeout)


def query_TCT_pathfinder(
    start: NodeInput,
    end: NodeInput,
    intermediate_categories: CategoryList,
    *,
    start_categories: Optional[CategoryList] = None,
    end_categories: Optional[CategoryList] = None,
    api_names: Optional[dict[str, str]] = None,
    meta_kg: Optional[pd.DataFrame] = None,
    api_predicates: Optional[dict[str, list[str]]] = None,
    resources: Optional[TranslatorResources] = None,
    scoring_method: str = "infores",
    name_resolver_kwargs: Optional[dict[str, Any]] = None,
    node_normalizer_kwargs: Optional[dict[str, Any]] = None,
) -> FinderResult:
    """
    Find paths between two biomedical concepts using Translator KPs.

    Parameters
    ----------
    start : str
        Start node as either a CURIE (for example, ``"MONDO:0004979"``) or a
        human-readable string (for example, ``"asthma"``).
    end : str
        End node as either a CURIE or human-readable string.
    intermediate_categories : list[str]
        Allowed categories for intermediate path nodes. Values may be short
        names like ``"Gene"`` or full Biolink names like ``"biolink:Gene"``.
    start_categories : list[str], optional
        Category override for the start node. If omitted, categories are
        inferred from Node Normalizer.
    end_categories : list[str], optional
        Category override for the end node. If omitted, categories are inferred
        from Node Normalizer.
    resources : TranslatorResources, optional
        Preloaded Translator resources. If omitted, the module-level singleton
        is loaded on first use and reused.
    api_names, meta_kg, api_predicates : optional
        Advanced partial overrides for the Translator resources used by the
        pathfinder implementation.
    scoring_method : str
        Scoring method passed to the legacy parser. Current values are
        ``"infores"`` and ``"edges"``.
    name_resolver_kwargs : dict, optional
        Extra keyword arguments for ``name_resolver.lookup``.
    node_normalizer_kwargs : dict, optional
        Extra keyword arguments for ``node_normalizer.get_normalized_nodes``.

    Returns
    -------
    FinderResult
        Convenience wrapper containing resolved input nodes, the parsed
        knowledge graph, results, auxiliary graphs, and the raw TRAPI-style
        output dictionary.

    Examples
    --------
    >>> from TCT import query_TCT_pathfinder
    >>> result = query_TCT_pathfinder("asthma", "albuterol", ["Gene"])
    >>> result.resolved_nodes["start"].curie
    'MONDO:0004979'
    """
    start_node = _resolve_node(
        start,
        name_resolver_kwargs=name_resolver_kwargs,
        node_normalizer_kwargs=node_normalizer_kwargs,
    )
    end_node = _resolve_node(
        end,
        name_resolver_kwargs=name_resolver_kwargs,
        node_normalizer_kwargs=node_normalizer_kwargs,
    )
    intermediate_categories = _normalize_categories(intermediate_categories) or []
    start_categories = _normalize_categories(start_categories) or start_node.categories
    end_categories = _normalize_categories(end_categories) or end_node.categories
    resolved_resources = _get_resources(
        resources=resources,
        api_names=api_names,
        meta_kg=meta_kg,
        api_predicates=api_predicates,
    )

    predicates1, apis1, _ = sele_predicates_API(
        start_categories,
        intermediate_categories,
        resolved_resources.meta_kg,
        resolved_resources.api_names,
    )
    predicates2, apis2, _ = sele_predicates_API(
        intermediate_categories,
        end_categories,
        resolved_resources.meta_kg,
        resolved_resources.api_names,
    )
    query1 = translator_query.format_query_json(
        [start_node.curie],
        [],
        start_categories,
        intermediate_categories,
        predicates1,
    )
    query2 = translator_query.format_query_json(
        [],
        [end_node.curie],
        intermediate_categories,
        end_categories,
        predicates2,
    )
    result1 = translator_query.parallel_api_query(
        query_json=query1,
        select_APIs=apis1,
        APInames=resolved_resources.api_names,
        API_predicates=resolved_resources.api_predicates,
        max_workers=max(1, len(apis1)),
    )
    result2 = translator_query.parallel_api_query(
        query_json=query2,
        select_APIs=apis2,
        APInames=resolved_resources.api_names,
        API_predicates=resolved_resources.api_predicates,
        max_workers=max(1, len(apis2)),
    )
    raw_output = parse_results_for_pathfinder(
        start_node.curie,
        end_node.curie,
        result1,
        result2,
        start_node_categories=start_categories,
        end_node_categories=end_categories,
        scoring_method=scoring_method,
        get_node_info=True,
    )
    return _build_finder_result(
        raw_output,
        resolved_nodes={"start": start_node, "end": end_node},
    )
