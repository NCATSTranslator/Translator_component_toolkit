# reviewed by yjzhang, 2026-08-19
from collections import Counter

import pandas as pd
from typing import Any, Optional, Union

from . import translator_query
from .TCT import (
    CategoryList,
    FinderResult,
    NodeInput,
    TranslatorResources,
    _build_finder_result,
    _get_resources,
    _normalize_categories,
    _resolve_nodes,
    sele_predicates_API,
)
from .TCT_pathfinder import generate_score_results, build_query_graph

def parse_results_for_neighborhood_finder(start_node_id:str, results:dict,
        start_node_categories:list|None=None, end_node_categories:list|None=None,
        get_node_info:bool=True,
        scoring_method:str='infores') -> dict:
    """
    Converts the results of two TRAPI queries into the same general json format as the other pathfinder APIs.

    Params
    ------
    start_node_id : str
        A CURIE id
    results : dict
        Results of a TRAPI query (e.g. parallel_api_query)
    start_node_categories : list | None
        Categories for the starting node.
    end_node_categories : list | None
        Categories for the ending nodes of the query.
    get_node_info : bool
    scoring_method : str
        scoring_method is how the node scores are generated, and could be 'infores' or 'edges'. Default: 'infores'

    Returns
    -------
    A dict of the format `{'query_graph': ..., 'knowledge_graph': ..., 'results':, 'auxiliary_graphs':...}`
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
        if 'attributes' not in v:
            v['attributes'] = []
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
        if nodes_to_add:
            batch_limit = 1000
            all_normalized_nodes = {}
            for idx in range(0, len(nodes_to_add), batch_limit):
                batch = nodes_to_add[idx:idx + batch_limit]
                batch_result = get_normalized_nodes(batch, mode='post')
                all_normalized_nodes.update(batch_result)
            for node_id in nodes_to_add:
                nn = all_normalized_nodes.get(node_id)
                if nn is not None:
                    output['knowledge_graph']['nodes'][node_id] = {'name': nn.label, 'categories': nn.types}
    return output


def parse_results_for_neighborhood_finder_multiple_inputs(start_node_ids:list[str], results:dict,
        start_node_categories:list|None=None, end_node_categories:list|None=None,
        get_node_info:bool=True,
        scoring_method:str='infores') -> dict:
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
        if i1 in start_node_ids:
            intermediate_node_id = i2
            s_o = 'object'
        elif i2 in start_node_ids:
            intermediate_node_id = i1
            s_o = 'subject'
        else:
            continue
        if (i1 in start_node_ids or i2 in start_node_ids) and intermediate_node_id in node_edges:
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
        if 'attributes' not in v:
            v['attributes'] = []
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
        'query_graph': build_query_graph(start_node_ids, '', start_node_categories, end_node_categories),
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
            batch_limit = 1000
            all_normalized_nodes = {}
            for idx in range(0, len(nodes_to_add), batch_limit):
                batch = nodes_to_add[idx:idx + batch_limit]
                batch_result = get_normalized_nodes(batch, mode='post')
                all_normalized_nodes.update(batch_result)
            for node_id in nodes_to_add:
                nn = all_normalized_nodes.get(node_id)
                if nn is not None:
                    output['knowledge_graph']['nodes'][node_id] = {'name': nn.label, 'categories': nn.types}
    return output

def neighborhood_finder(
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
    node : str or list[str]
        Source node or nodes. Each value may be a CURIE or human-readable
        string. Human-readable strings are resolved with Name Resolver and then
        normalized with Node Normalizer.
    neighbor_categories : list[str]
        Desired neighbor categories. Values may be short names like ``"Drug"``
        or full Biolink names like ``"biolink:Drug"``.
    node_categories : list[str], optional
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

    predicates, apis, _ = sele_predicates_API(
        source_categories,
        neighbor_categories,
        resolved_resources.meta_kg,
        resolved_resources.api_names,
    )
    if predicates_subset is not None:
        predicates = list(set(predicates).intersection(predicates_subset))
    if len(predicates) == 0:
        predicates = ["biolink:related_to"]

    input_curies = [resolved_node.curie for resolved_node in resolved_nodes]
    query = translator_query.format_query_json(
        subject_ids=input_curies,
        object_ids=None,
        subject_categories=None,
        object_categories=neighbor_categories,
        predicates=predicates,
        attribute_constraints=attribute_constraints,
    )
    raw_edges = translator_query.parallel_api_query(
        query_json=query,
        select_APIs=apis,
        APInames=resolved_resources.api_names,
        API_predicates=resolved_resources.api_predicates,
        max_workers=max(1, len(apis)),
    )
    if isinstance(node, str):
        raw_output = parse_results_for_neighborhood_finder(
            input_curies[0],
            raw_edges,
            source_categories,
            neighbor_categories,
        )
        result_nodes = {"node": resolved_nodes[0]}
    else:
        raw_output = parse_results_for_neighborhood_finder_multiple_inputs(
            input_curies,
            raw_edges,
            source_categories,
            neighbor_categories,
        )
        result_nodes = {
            f"node_{index}": resolved_node
            for index, resolved_node in enumerate(resolved_nodes)
        }
    return _build_finder_result(raw_output, resolved_nodes=result_nodes)
