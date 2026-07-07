import json

from . import node_normalizer
from . import translator_query
from . import name_resolver
from . import TCT_neighborhood_finder


def network_annotator(gene_list, 
                      select_APIs, 
                      node2_categories, 
                      select_metaKG, 
                      API_predicates, 
                      output_file=None):
    """
    Filter multiple TRAPI neighborhood JSON files by gene list and merge
    them into a single TRAPI JSON.

    Parameters
    ----------
    gene_list : list
        Gene symbols to keep.
    output_file : str, optional
        Output merged JSON file.

    Returns
    -------
    dict
        Merged TRAPI JSON object.
    """
    import json
    result = {}
    TCT_neighborhood_finder_result = {}
    for gene in gene_list:
        input_identifiers = name_resolver.lookup(gene, only_taxa='NCBITaxon:9606', biolink_type='biolink:Gene').curie

        input_node_id, result[input_identifiers], result_parsed, result_ranked_by_primary_infores = TCT_neighborhood_finder.neighborhood_finder(input_identifiers,
                                                                                              node2_categories = node2_categories,
                                                                                            APInames = select_APIs,
                                                                                            metaKG = select_metaKG,
                                                                                            API_predicates = API_predicates)
       

    for input_identifiers in result.keys():
        TCT_neighborhood_finder_result[input_identifiers] = TCT_neighborhood_finder.parse_results_for_neighborhood_finder(input_identifiers, result[input_identifiers],
        start_node_categories='biolink:Gene', end_node_categories=None,
        get_node_info=True,
        scoring_method='infores')

    gene_set = set(gene_list)

    merged = {
        "query_graph": None,
        "knowledge_graph": {
            "nodes": {},
            "edges": {}
        },
        "results": []
    }

    for json_cur in TCT_neighborhood_finder_result.values():

        data = json_cur
        
        # Keep first query graph
        if merged["query_graph"] is None:
            merged["query_graph"] = data.get("query_graph", {})

        kg_nodes = data.get("knowledge_graph", {}).get("nodes", {})
        kg_edges = data.get("knowledge_graph", {}).get("edges", {})

        # --------------------------------------------------
        # Step 1: keep gene nodes in gene_list
        # --------------------------------------------------
        keep_node_ids = {
            node_id
            for node_id, node_info in kg_nodes.items()
            if node_info.get("name") in gene_set
        }

        # --------------------------------------------------
        # Step 2: keep edges connecting retained nodes
        # --------------------------------------------------
        keep_edge_ids = set()

        for edge_id, edge_info in kg_edges.items():

            subject = edge_info.get("subject")
            obj = edge_info.get("object")

            if subject in keep_node_ids and obj in keep_node_ids:
                keep_edge_ids.add(edge_id)

        # --------------------------------------------------
        # Step 3: build filtered node/edge dictionaries
        # --------------------------------------------------
        filtered_nodes = {
            node_id: kg_nodes[node_id]
            for node_id in keep_node_ids
        }

        filtered_edges = {
            edge_id: kg_edges[edge_id]
            for edge_id in keep_edge_ids
        }

        # --------------------------------------------------
        # Step 4: filter results
        # --------------------------------------------------
        filtered_results = []

        for result in data.get("results", []):

            keep_result = True

            # node bindings
            for bindings in result.get("node_bindings", {}).values():

                for binding in bindings:

                    if binding["id"] not in keep_node_ids:
                        keep_result = False
                        break

                if not keep_result:
                    break

            # edge bindings
            if keep_result:

                for analysis in result.get("analyses", []):

                    for bindings in analysis.get(
                        "edge_bindings", {}
                    ).values():

                        for binding in bindings:

                            if binding["id"] not in keep_edge_ids:
                                keep_result = False
                                break

                        if not keep_result:
                            break

                    if not keep_result:
                        break

            if keep_result:
                filtered_results.append(result)

        # --------------------------------------------------
        # Step 5: merge
        # --------------------------------------------------
        merged["knowledge_graph"]["nodes"].update(filtered_nodes)
        merged["knowledge_graph"]["edges"].update(filtered_edges)
        merged["results"].extend(filtered_results)

    # ------------------------------------------------------
    # Step 6: save merged file
    # ------------------------------------------------------
    if output_file:

        with open(output_file, "w") as f:
            json.dump(merged, f, indent=2)

    return merged


def get_connected_graph(result_parsed, input_identifiers):
    """
    This function is used to extract the connected graph from the returned graph based on neighborhood finder from multiple inputs. 
    It will only include the input nodes and the nodes that are connected to the input nodes with degree greater than 1. 


    Parameters
    ----------
    result_parsed (dict)
        The parsed results for results from TCT_neighborhood_finder.neighborhood_finder_multiple_inputs().
    input_identifiers (list)
        A list of input node identifiers, which are also input for TCT_neighborhood_finder.neighborhood_finder_multiple_inputs().

    Returns
    --------------
    result_parsed (dict)
        The connected graph extracted from the parsed results.

    --------------
    Example:
    >>>
    input_identifiers = ['NCBIGene:6774', 'NCBIGene:4170','NCBIGene:4792','NCBIGene:4288','NCBIGene:596','NCBIGene:581','NCBIGene:836','NCBIGene:6777','NCBIGene:4790','NCBIGene:545']

    result, result_parsed = TCT_neighborhood_finder.neighborhood_finder_multiple_inputs(input_identifiers,
                                                                                            node2_categories = ['biolink:Gene','biolink:Protein'],
                                                                                            APInames = APInames,
                                                                                            metaKG = metaKG,
                                                                                            API_predicates = API_predicates)   

    result = TCT_network_annotator.get_connected_graph(result_parsed, input_identifiers)
    import datetime
    import json
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    with open('./PathFinder_testing_results/'+'TCT_neighborhood_finder_result_'+'_'+timestamp+'.json', 'w') as f:
        json.dump(result, f)
    # visualize the result using the TCT visualization tool (https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/visulize_path_finder_results.html). 
    --------------

    """
        
    result_parsed_copy = result_parsed.copy()
    # count node degrees based on edge in the result_parsed['knowledge_graph']['edges'], if multiple nodes are connecting to the same node, then count the degree of that node as the number of nodes connecting to it. If there is only one node connecting to it, then count the degree of that node as 1. 

    result_parsed_copy = result_parsed.copy()
    # count node degrees based on edge in the result_parsed['knowledge_graph']['edges'], if multiple nodes are connecting to the same node, then count the degree of that node as the number of nodes connecting to it. If there is only one node connecting to it, then count the degree of that node as 1. 

    dic_connected_nodes = {}
    for key in result_parsed_copy['knowledge_graph']['edges']:

        edge = result_parsed_copy['knowledge_graph']['edges'][key]
        subject = edge['subject']
        object = edge['object']

        if subject not in dic_connected_nodes:
            dic_connected_nodes[subject] = set()
        if object not in dic_connected_nodes:
            dic_connected_nodes[object] = set()
        dic_connected_nodes[subject].add(object)
        dic_connected_nodes[object].add(subject)

    # count the degree of each node based on the dic_connected_nodes
    node_degrees = {}
    for node in dic_connected_nodes:
        node_degrees[node] = len(dic_connected_nodes[node])


    # select the nodes if the degree of the node is greater than 1 or the node is in the input_identifiers
    selected_nodes = []
    for node in node_degrees:
        if node_degrees[node] > 1 or node in input_identifiers:
            selected_nodes.append(node)

    # get the edges if the edge connects to the selected nodes
    selected_edges_id = []
    selected_edges = {}
    for key in result_parsed_copy['knowledge_graph']['edges']:
        edge = result_parsed_copy['knowledge_graph']['edges'][key]
        subject = edge['subject']
        object = edge['object']
        if subject in selected_nodes and object in selected_nodes:
            selected_edges_id.append(key)
            selected_edges[key] = edge

    #remove the result_parsed['auxiliary_graphs'] if the selected_edges_id is in the result_parsed['auxiliary_graphs']
    for key in list(result_parsed_copy['auxiliary_graphs'].keys()):
        current_auxiliary_graph = result_parsed_copy['auxiliary_graphs'][key]
        # if all current_auxiliary_graph was included  in selected_edges_id, then keep it, otherwise remove it
        if len(current_auxiliary_graph) == len(set(current_auxiliary_graph).intersection(set(selected_edges_id))):
            continue
        else:
            del result_parsed_copy['auxiliary_graphs'][key]

    # remove the edges in result_parsed_copy['knowledge_graph']['edges'] that are not in selected_edges_id
    for key in list(result_parsed_copy['knowledge_graph']['edges'].keys()):
        if key not in selected_edges_id:
            del result_parsed_copy['knowledge_graph']['edges'][key]

    # remove the nodes in result_parsed_copy['knowledge_graph']['nodes'] that are not in selected_nodes
    for key in list(result_parsed_copy['knowledge_graph']['nodes'].keys()):
        if key not in selected_nodes:
            del result_parsed_copy['knowledge_graph']['nodes'][key]
    
    return result_parsed_copy
