from collections import Counter

from .TCT import sele_predicates_API, format_query_json, parse_KG, rank_by_primary_infores


def format_query_json_for_neighborhood_finder(subject_ids, object_ids=None,
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


def generate_score_results(results, method='infores'):
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


def parse_results_for_neighborhood_finder(start_node_id:str, results:dict,
        start_node_categories=None, end_node_categories=None,
        get_node_info=True,
        scoring_method='infores'):
    """
    Converts the results of two TRAPI queries into the same general json format as the other pathfinder APIs.
    scoring_method is how the node scores are generated, and could be 'infores' or 'edges'.
    """
    # nodes
    node_info = {}
    # edges is a dict of intermediate nodes
    node_edges = {}
    for k, v in results.items():
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
        if (i1 == start_node_id or i2 == start_node_id) and intermediate_node_id in node_edges:
            node_edges[intermediate_node_id].append((k, v))
        else:
            node_edges[intermediate_node_id] = [(k, v)]
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
    for k, v in node_info.items():
        if 'categories' in v:
            v['categories'] = list(v['categories'])
    all_edges = {}
    all_auxiliary_graphs = {}
    i = 1
    # sort connecting_intermediate_nodes by total number of connections
    connection_counts = Counter({k: len(v) for k, v in node_edges.items()})
    for i1, count in connection_counts.most_common():
        edges = node_edges[i1]
        all_edges.update({k: v for k, v in edges})
        keys = [x[0] for x in edges]
        all_auxiliary_graphs[f'aux_{i}_{i1}'] = keys
        i += 1
    # generate output json
    output = {
        'query_graph': build_query_graph(start_node_id, '', start_node_categories, end_node_categories),
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
        normalized_nodes = get_normalized_nodes(nodes_to_add, mode='post')
        for node_id in nodes_to_add:
            nn = normalized_nodes[node_id]
            if nn is not None:
                output['knowledge_graph']['nodes'][node_id] = {'name': nn.label, 'categories': nn.types}
    return output


def neighborhood_finder(input_node, node2_categories, APInames, metaKG, API_predicates, input_node_category = []):
    """
    This function is used to find the neighborhood of a given input node with intermediate categories.

    --------------
    Parameters:
    input_node (str): The input node - should be a CURIE id.
    node2_categories (list): A list of intermediate categories to be used in the neighborhood finding process.
    APInames (dict): A dictionary containing the names of the APIs to be used.
    metaKG (DataFrame): The metadata knowledge graph containing information about the APIs and their predicates.
    API_predicates (dict): A dictionary containing the predicates for each API.
    input_node_category (list): Optional. A list of categories for the input node. If empty, it will be derived from the input node's types.

    --------------
    Returns:
    input_node_id (str): The curie id of the input node.
    result (dict): The result of the query for the input node.
    result_parsed (DataFrame): The parsed results for the input node.
    result_ranked_by_primary_infores (DataFrame): The ranked results based on primary infores.

    --------------
    Example:
    >>> input_node_id, result, result_parsed, result_ranked_by_primary_infores1 = Neighborhood_finder('MONDO:0008170', #Ovarian Cancer
                                                                                            node2_categories = ['biolink:SmallMolecule', 'biolink:Drug', 'biolink:ChemicalEntity'],
                                                                                            APInames = APInames,
                                                                                            metaKG = metaKG,
                                                                                            API_predicates = API_predicates)
    --------------

    """
    from . import node_normalizer
    from . import translator_query

    input_node_id = input_node
    # Step 1: Resolve the input node to get its curie id and categories
    input_node_info = node_normalizer.get_normalized_nodes(input_node_id)
    print(input_node_id)

    if len(input_node_category) == 0:
        input_node_category = input_node_info.types
    else:
        input_node_category = list(set(input_node_category).intersection(set(input_node_info.types)))
        if len(input_node_category) == 0:
            input_node_category = input_node_info.types

    # Step 2: Select predicates and APIs based on the intermediate categories
    sele_predicates, sele_APIs, API_URLs = sele_predicates_API(input_node_category,
                                                                node2_categories,
                                                                metaKG, APInames)

    # Step 3: Format the query JSON for the input node
    query_json = format_query_json([input_node_id], [],
                                   [input_node_category],
                                   node2_categories,
                                   sele_predicates)

    # Step 4: Query the APIs in parallel
    result = translator_query.parallel_api_query(query_json=query_json,
                             select_APIs= sele_APIs,
                             APInames=APInames,
                             API_predicates=API_predicates,
                             max_workers=len(sele_APIs))
    result_parsed = parse_KG(result)
        # Step 7: Ranking the results. This ranking method is based on the number of unique
        # primary infores. It can only be used to rank the results with one defined node.
    result_ranked_by_primary_infores1 = rank_by_primary_infores(result_parsed, input_node_id)   # input_node1_id is the curie id of the
    parsed_results = parse_results_for_neighborhood_finder(input_node_id, result, input_node_category, node2_categories)
    return input_node_id, result, parsed_results, result_ranked_by_primary_infores1


