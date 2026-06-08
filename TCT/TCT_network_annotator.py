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
