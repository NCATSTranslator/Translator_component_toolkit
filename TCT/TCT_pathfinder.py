# TCT Pathfinder...

from collections import Counter

from . import node_normalizer
from . import translator_query
from .TCT import sele_predicates_API, parse_KG, rank_by_primary_infores, merge_ranking_by_number_of_infores

def format_query_json_for_pathfinder(subject_ids, object_ids=None,
        subject_categories=None,
        object_categories=None,
        predicates=None):
    '''
    Example input:
    subject_ids = ["NCBIGene:3845"]
    object_ids = []
    subject_categories = ["biolink:Gene"]
    object_categories = ["biolink:Gene"]
    predicates = ["biolink:positively_correlated_with", "biolink:physically_interacts_with"]
    '''
    query_json_temp = {
        "message": {
            "query_graph": {

                "edges": {
                    "e00": {
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
                        "categories":[] # required
                        }
                    }
                }
            }
        }

    if len(subject_ids) > 0:
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


def build_query_graph(start_node_id, end_node_id, start_node_categories=None, end_node_categories=None):
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
                    "ids": [
                        start_node_id
                    ],
                    "is_set": False,
                    "option_group_id": None,
                    "set_id": None,
                    "set_interpretation": "BATCH"
                }
            },
            "paths": {
                "p0": {
                    "constraints": None,
                    "object": "on",
                    "predicates": None,
                    "subject": "sn"
                }
            }
        }
    return q


def parse_results_for_pathfinder(start_node_id:str, end_node_id:str, result1:dict, result2:dict,
        start_node_categories=None, end_node_categories=None):
    """
    Converts the results of two TRAPI queries into the same general json format as the other pathfinder APIs.
    """
    # TODO: parse results...
    # nodes
    # edges is a dict of intermediate nodes
    intermediate_node_edges = {}
    for k, v in result1.items():
        i1 = v['subject']
        i2 = v['object']
        if i1 == start_node_id:
            intermediate_node_id = i2
        elif i2 == start_node_id:
            intermediate_node_id = i1
        else:
            continue
        if (i1 == start_node_id or i2 == start_node_id) and intermediate_node_id in intermediate_node_edges:
            intermediate_node_edges[intermediate_node_id].append((k, v))
        else:
            intermediate_node_edges[intermediate_node_id] = [(k, v)]
    connecting_intermediate_nodes = {}
    for k, v in result2.items():
        i1 = v['subject']
        i2 = v['object']
        if i1 == end_node_id:
            intermediate_node_id = i2
        elif i2 == end_node_id:
            intermediate_node_id = i1
        else:
            continue
        if (i1 == end_node_id or i2 == end_node_id) and intermediate_node_id in intermediate_node_edges:
            if intermediate_node_id in connecting_intermediate_nodes:
                connecting_intermediate_nodes[intermediate_node_id]['e2'].append((k, v))
            else:
                connecting_intermediate_nodes[intermediate_node_id] = {'e1': intermediate_node_edges[intermediate_node_id], 'e2' : [(k, v)]}
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
    output = {
        'query_graph': build_query_graph(start_node_id, end_node_id, start_node_categories, end_node_categories),
        'knowledge_graph': {'nodes': {x: {} for x in connection_counts.keys()},
                            'edges': all_edges,
                           },
        'results': [{'analyses': []}],
        'auxiliary_graphs': all_auxiliary_graphs
    }
    return output


def pathfinder(input_node1_id:str, input_node2_id:str,
        intermediate_categories:list, APInames, metaKG, API_predicates):
    # get categories for input nodes
    normalized_node_dict = node_normalizer.get_normalized_nodes([input_node1_id, input_node2_id])
    input_node1_info = normalized_node_dict[input_node1_id]
    input_node1_list = [input_node1_id]
    input_node1_category = input_node1_info.types

    input_node2_info = normalized_node_dict[input_node2_id]
    print(input_node2_id)
    input_node2_list = [input_node2_id]

    input_node2_category = input_node2_info.types

    # Select predicates and APIs based on the intermediate categories
    sele_predicates1, sele_APIs1, API_URLs1 = sele_predicates_API(input_node1_category,
                                                                  intermediate_categories,
                                                                  metaKG, APInames)
    sele_predicates2, sele_APIs2, API_URLs2 = sele_predicates_API(intermediate_categories,
                                                                  input_node2_category,
                                                                  metaKG, APInames)
    query_json1 = format_query_json_for_pathfinder(input_node1_list,  # a list of identifiers for input node1
                                    [],  # id list for the intermediate node, it can be empty list if only want to query node1
                                    input_node1_category,  # a list of categories of input node1
                                    intermediate_categories,  # a list of categories of the intermediate node
                                    sele_predicates1) # a list of predicates

    # for the second hop, we want the predicates to be...
    query_json2 = format_query_json_for_pathfinder([], 
                                    input_node2_list,  
                                    intermediate_categories,  # a list of categories of input node2
                                    input_node2_category,  # a list of categories of the intermediate node
                                    sele_predicates2) # a list of predicates

    result1 = translator_query.parallel_api_query(query_json=query_json1,
                             select_APIs = sele_APIs1,
                             APInames=APInames,
                             API_predicates=API_predicates,
                             max_workers=len(sele_APIs1))
    result2 = translator_query.parallel_api_query(query_json=query_json2,
                                select_APIs = sele_APIs2,
                                APInames=APInames,
                                API_predicates=API_predicates,
                                max_workers=len(sele_APIs2))

    result_parsed1 = parse_KG(result1)
        # Step 7: Ranking the results. This ranking method is based on the number of unique
        # primary infores. It can only be used to rank the results with one defined node.
    result_ranked_by_primary_infores1 = rank_by_primary_infores(result_parsed1, input_node1_id)   # input_node1_id is the curie id of the

    result_parsed2 = parse_KG(result2)
    result_ranked_by_primary_infores2 = rank_by_primary_infores(result_parsed2, input_node2_id)   # input_node2_id is the curie id of the

    possible_paths = len(set(result_ranked_by_primary_infores1['output_node']).intersection(set(result_ranked_by_primary_infores2['output_node'])))
    print("Number of possible paths: ", possible_paths)

    paths = merge_ranking_by_number_of_infores(result_ranked_by_primary_infores1, result_ranked_by_primary_infores2,
            plot=False)

    output = parse_results_for_pathfinder(input_node1_id, input_node2_id, result1, result2,
            start_node_categories=input_node1_category,
            end_node_categories=input_node2_category)

    return result1, result2, output, paths

