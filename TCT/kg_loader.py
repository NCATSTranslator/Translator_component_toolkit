# Import graph from kg2 csv dump, tsv dump, or jsonl dump.

import csv
import gzip
import json
import os

from scipy import sparse, io

# TODO: multiple edges between two nodes?
def import_kg2_csv(node_filename, edge_filename, edges_to_include=None, remove_unused_nodes=False, verbose=True, reindex_edges=True, use_node_types=True, use_edge_types=True, use_edge_properties=False):
    """
    Args:
        csv_filename: name of csv file (could be csv or tsv, or csv.gz or tsv.gz)
        edges_to_include: set of edge types
        remove_unused_nodes: True if nodes with no in- or out-edges are to be removed.
        reindex_edges: whether or not to use indices or original IDs in the edge list.

    Returns:
        nodes: list of (_id, _name, _labels_id) where _labels_id corresponds to a key in node_types
        edges: dict of (node1, node2): _type_id where node1 and node2 index into nodes, and _type_id corresponds to a key in edge_types
        node_types: dict of int: str (_labels)
        edge_types: dict of int: str (_type)
    """
    nodes = []
    n_nodes = 0
    # mapping of _id to index in nodes
    node_index = {}
    # node_types is a map of string (
    node_types = {}
    edges = {}
    # edge_types is a map of string (_type) to node
    edge_types = {}
    # sets of nodes that have in-edges or out-edges (to use when deciding whether to remove nodes)
    node_has_edge = set()
    csv.field_size_limit(99999999)
    if node_filename.endswith('.gz'):
        # handle gzip
        f = gzip.open(node_filename, 'rt')
    else:
        f = open(node_filename)
    delimiter = ','
    if 'tsv' in node_filename:
        delimiter = '\t'
    dr = csv.DictReader(f, dialect='unix', delimiter=delimiter)
    for i, row in enumerate(dr):
        if verbose and i % 100000 == 0:
            print(i, 'nodes: ', len(node_index), 'edges: ', len(edges))
        # if this is a node
        row_name = ''
        row_identifier = row['id']
        if 'name' not in row:
            row_name = row_identifier
        else:
            row_name = row['name']
        row_source = row['category']
        row_label = row['category']
        if use_node_types:
            if row_label in node_types:
                nodes.append((row['id'], row_name, node_types[row_label], row_identifier, row_source))
            else:
                nodes.append((row['id'], row_name, len(node_types) + 1, row_identifier, row_source))
                node_types[row_label] = len(node_types) + 1
        else:
            nodes.append((row['id'], row_name, True, row_identifier, row_source))
        node_index[row['id']] = n_nodes 
        n_nodes += 1
    if edge_filename.endswith('.gz'):
        # handle gzip
        f = gzip.open(edge_filename, 'rt')
    else:
        f = open(edge_filename)
    delimiter = ','
    if 'tsv' in edge_filename:
        delimiter = '\t'
    dr = csv.DictReader(f, dialect='unix', delimiter=delimiter)
    for i, row in enumerate(dr):
        # if this row is an edge
            edge_type = row['predicate']
            if edges_to_include is None or edge_type in edges_to_include:
                node1 = row['subject']
                node2 = row['object']
                node_has_edge.add(node1)
                node_has_edge.add(node2)
                if use_edge_types:
                    if edge_type in edge_types:
                        edges[(node1, node2)] = edge_types[edge_type]
                    else:
                        edges[(node1, node2)] = len(edge_types) + 1
                        edge_types[edge_type] = len(edge_types) + 1
                else:
                    edges[(node1, node2)] = True
                if use_edge_properties:
                    if 'properties' in row:
                        edge_properties = row['properties']
                    else:
                        edge_properties = {}
                    if 'primary_knowledge_source' in row:
                        edge_properties['primary_knowledge_source'] = row['primary_knowledge_source']
                    edge_properties['id'] = int(row['id'])
                    edges[(node1, node2)] = edge_properties
    if remove_unused_nodes:
        # remove all nodes that don't have edges
        to_remove = set(node_index.keys()).difference(node_has_edge)
        nodes = [n for n in nodes if n[0] not in to_remove]
        # rebuild node_index
        node_index = {n[0]: i for i, n in enumerate(nodes)}
    # convert edge indices
    if reindex_edges:
        new_edges = {}
        for k, e in edges.items():
            node1, node2 = k
            node1 = node_index[node1]
            node2 = node_index[node2]
            new_edges[(node1, node2)] = e
        edges = new_edges
    node_types = {v: k for k, v in node_types.items()}
    edge_types = {v: k for k, v in edge_types.items()}
    return nodes, edges, node_types, edge_types


def import_kg2_jsonl(node_filename, edge_filename, edges_to_include=None, remove_unused_nodes=True, use_edge_types=True, use_node_types=True, verbose=True, reindex_edges=True, use_edge_properties=False):
    """
    Imports a jsonl file that contains nodes and edges.

    Args:
        node_filename: name of jsonl file containing nodes, or both nodes and edges.
        edge_filename: name of jsonl file containing edges. Can be None if all nodes and edges are in node_filename.
        edges_to_include: set of edge types
        remove_unused_nodes: True if nodes with no in- or out-edges are to be removed.
        reindex_edges: whether or not to use indices or original IDs in the edge list.

    Returns:
        nodes: list of (_id, _name, _labels_id) where _labels_id corresponds to a key in node_types
        edges: dict of (node1, node2): _type_id where node1 and node2 index into nodes, and _type_id corresponds to a key in edge_types
        node_types: dict of int: str (_labels)
        edge_types: dict of int: str (_type)
    """
    nodes = []
    n_nodes = 0
    # mapping of _id to index in nodes
    node_index = {}
    # node_types is a map of string (
    node_types = {}
    edges = {}
    # edge_types is a map of string (_type) to node
    edge_types = {}
    # sets of nodes that have in-edges or out-edges (to use when deciding whether to remove nodes)
    node_has_edge = set()
    if str(node_filename).endswith('.gz'):
        # handle gzip
        f = gzip.open(node_filename, 'rt')
    else:
        f = open(node_filename)
    line = f.readline()
    i = 0
    using_edge_file = False
    while line:
        row = json.loads(line)
        if verbose and i % 100000 == 0:
            print(i, 'nodes: ', len(node_index), 'edges: ', len(edges))
            print(row)
        # if this is a node
        if 'id' in row and 'category' in row and 'subject' not in row and 'object' not in row:
            row_name = ''
            row_identifier = row['id']
            if 'name' not in row:
                row_name = row_identifier
            else:
                row_name = row['name']
            row_source = row['category']
            # arbitrarily pick the first category...
            row_label = row['category'][0]
            #print('row_label:', row_label)
            if use_node_types:
                if row_label in node_types:
                    nodes.append((row['id'], row_name, node_types[row_label], row_identifier, row_source))
                else:
                    nodes.append((row['id'], row_name, len(node_types) + 1, row_identifier, row_source))
                    node_types[row_label] = len(node_types) + 1
            else:
                nodes.append((row['id'], row_name, True, row_identifier, row_source))
            node_index[row['id']] = n_nodes 
            n_nodes += 1
        # if this row is an edge
        else:
            edge_type = row['predicate']
            if edges_to_include is None or edge_type in edges_to_include:
                node1 = row['subject']
                node2 = row['object']
                node_has_edge.add(node1)
                node_has_edge.add(node2)
                if use_edge_types:
                    if edge_type in edge_types:
                        edges[(node1, node2)] = edge_types[edge_type]
                    else:
                        edges[(node1, node2)] = len(edge_types) + 1
                        edge_types[edge_type] = len(edge_types) + 1
                else:
                    edges[(node1, node2)] = True
                if use_edge_properties:
                    if 'properties' in row:
                        edge_properties = row['properties']
                    else:
                        edge_properties = {}
                    if 'primary_knowledge_source' in row:
                        edge_properties['primary_knowledge_source'] = row['primary_knowledge_source']
                    edge_properties['id'] = int(row['id'])
                    edges[(node1, node2)] = edge_properties
        line = f.readline()
        if not line and not using_edge_file and edge_filename is not None:
            f.close()
            print('Opening edge file', edge_filename)
            if str(edge_filename).endswith('.gz'):
                # handle gzip
                f = gzip.open(edge_filename, 'rt')
            else:
                f = open(edge_filename)
            line = f.readline()
            using_edge_file = True
        i += 1
    if remove_unused_nodes:
        # remove all nodes that don't have edges
        to_remove = set(node_index.keys()).difference(node_has_edge)
        nodes = [n for n in nodes if n[0] not in to_remove]
        # rebuild node_index
        node_index = {n[0]: i for i, n in enumerate(nodes)}
    # convert edge indices
    if reindex_edges:
        new_edges = {}
        for k, e in edges.items():
            node1, node2 = k
            node1 = node_index[node1]
            node2 = node_index[node2]
            new_edges[(node1, node2)] = e
        edges = new_edges
    node_types = {v: k for k, v in node_types.items()}
    edge_types = {v: k for k, v in edge_types.items()}
    return nodes, edges, node_types, edge_types




def to_sparse(nodes, edges):
    """
    Returns a DOK matrix from the edges...
    """
    n_nodes = len(nodes)
    edge_matrix = sparse.dok_array((n_nodes, n_nodes), dtype=int)
    for k, v in sorted(edges.items()):
        n1, n2 = k
        edge_matrix[n1, n2] = v
    return edge_matrix


def load_kg2(filename='kg2.csv', edges_to_include=None, remove_unused_nodes=False, mtx_filename='spoke.mtx', **kwargs):
    if filename.endswith('.csv') or filename.endswith('.csv.gz') or filename.endswith('.tsv') or filename.endswith('.tsv.gz'):
        nodes, edges, node_types, edge_types = import_kg2_csv(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, **kwargs)
    elif filename.endswith('.json') or filename.endswith('.json.gz') or filename.endswith('.jsonl') or filename.endswith('.jsonl.gz'):
        nodes, edges, node_types, edge_types = import_kg2_jsonl(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, **kwargs)
    else:
        raise Exception('Filename should be a csv, tsv, json, or jsonl.')
    if not os.path.exists(mtx_filename):
        edge_matrix = to_sparse(nodes, edges)
        io.mmwrite(mtx_filename, edge_matrix)
    else:
        edge_matrix = io.mmread(mtx_filename)
    return nodes, edges, node_types, edge_types, edge_matrix


def load_kg2_igraph_from_data(nodes, edges, node_types, edge_types, remove_unused_nodes=True, directed=False, verbose=False, low_memory=False, **kwargs):
    """
    Uses the output of import_kg2_csv or import_kg2_jsonl
    """
    import igraph as ig
    if low_memory:
        edge_list = ({'s': str(v[0]), 't': str(v[1])} for v in edges.keys())
        del edges
    else:
        if 'use_edge_properties' in kwargs and kwargs['use_edge_properties'] == True:
            # igraph doesn't allow lists as edge properties, so we are converting them to a string.
            for v, e in edges.items():
                for key, value in e.copy().items():
                    if isinstance(value, list) or isinstance(value, dict):
                        e[key] = str(value)
            edge_list = ({'source': str(v[0]), 'target': str(v[1]), **e} for v, e in edges.items())
        else:
            edge_list = ({'source': str(v[0]), 'target': str(v[1]), 'type': edge_types[e]} for v, e in edges.items())
    if verbose:
        print('creating node list')
    # set node attributes
    # convert the node id to a string, bc
    if low_memory:
        node_list = ({
             'name': str(n[0]),
             'feature_name':  n[1],
             'category': node_types[n[2]],
             'identifier': n[3],
            } for n in nodes)
        del nodes
    else:
        node_list = ({
                'name': str(n[0]),
                'feature_name':  n[1],
                'category': node_types[n[2]],
                'identifier': n[3],
                'source': n[4],
        } for n in nodes)
    if verbose:
        print('calling igraph.Graph.DictList')
    if low_memory:
        graph = ig.Graph.DictList(node_list, edge_list, directed=directed,
                edge_foreign_keys=('s', 't'),
                iterative=False)
    else:
        graph = ig.Graph.DictList(node_list, edge_list, directed=directed,
                edge_foreign_keys=('source', 'target'),
                iterative=False)
    return graph


def load_kg2_networkx(filename='spoke.csv', edges_to_include=None, remove_unused_nodes=True, directed=False, **kwargs):
    import networkx as nx
    if filename.endswith('.csv') or filename.endswith('.csv.gz') or filename.endswith('.tsv') or filename.endswith('.tsv.gz'):
        nodes, edges, node_types, edge_types = import_kg2_csv(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, reindex_edges=False, **kwargs)
    elif filename.endswith('.json') or filename.endswith('.json.gz') or filename.endswith('.jsonl') or filename.endswith('.jsonl.gz'):
        nodes, edges, node_types, edge_types = import_kg2_jsonl(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, reindex_edges=False, **kwargs)
    else:
        raise Exception('Filename should be a csv, tsv, json, or jsonl.')
    edge_list = edges.keys()
    if directed:
        graph = nx.from_edgelist(edge_list, nx.DiGraph)
    else:
        graph = nx.from_edgelist(edge_list)
    # set node attributes
    node_attributes = {}
    # TODO: get all IDs, not just names
    for n in nodes:
        node_attributes[n[0]] = {
                'name':  n[1],
                'category': node_types[n[2]],
                'identifier': n[3],
                'source': n[4],
        }
    nx.set_node_attributes(graph, node_attributes)
    # set edge attributes
    edge_attributes = {k: {'type': edge_types[v]} for k, v in edges.items()}
    nx.set_edge_attributes(graph, edge_attributes)
    return graph


def load_kg2_igraph(filename='graph.jsonl.gz', edges_to_include=None, remove_unused_nodes=True, directed=False, verbose=False, low_memory=False, **kwargs):
    """
    Imports the file as an igraph. The file can be a json/jsonl export from neo4j, and it can be gzipped. The spoke IDs are converted to strings because igraph is very slow if the ids are ints.
    """
    if low_memory:
        kwargs['use_edge_properties'] = False
    if filename.endswith('.csv') or filename.endswith('.csv.gz') or filename.endswith('.tsv') or filename.endswith('.tsv.gz'):
        nodes, edges, node_types, edge_types = import_kg2_csv(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, reindex_edges=False, **kwargs)
    elif filename.endswith('.json') or filename.endswith('.json.gz') or filename.endswith('.jsonl') or filename.endswith('.jsonl.gz'):
        nodes, edges, node_types, edge_types = import_kg2_jsonl(filename, None, edges_to_include=edges_to_include, remove_unused_nodes=remove_unused_nodes, reindex_edges=False, **kwargs)
    else:
        raise Exception('Filename should be a csv, tsv, json, or jsonl.')
    if verbose:
        print('Done loading data, creating edge list')
    return load_kg2_igraph_from_data(nodes, edges, node_types, edge_types, remove_unused_nodes, directed, verbose, low_memory, **kwargs)
    # use igraph.graph.DictList


def symmetrize_matrix(matrix):
    """
    Symmetrizes an adjacency matrix.

    Warning: this completely destroys any meaning applied to node values. Nonzero = edge exists, zero = edge doesn't exist.
    """
    lower_triangle = sparse.tril(matrix)
    upper_triangle = sparse.triu(matrix)
    return lower_triangle + lower_triangle.T + upper_triangle + upper_triangle.T

