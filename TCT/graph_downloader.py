# Download graphs to local caches...

import os
from pathlib import Path
import tarfile
import tempfile

import requests
from zstandard import ZstdDecompressor

GRAPHS = {
        'signor': {
            'download': 'https://kgx-storage.rtx.ai/releases/signor/latest/signor.tar.zst',
            'metadata': 'https://kgx-storage.rtx.ai/releases/signor/latest/graph-metadata.json'
        },
}

CACHE_DIR = Path.home() / '.cache' / 'TCT'

os.makedirs(CACHE_DIR, exist_ok=True)

def download_graph(graph_name: str):
    graph_path = CACHE_DIR / graph_name
    download_path = GRAPHS[graph_name]['download']
    save_path = graph_path / (graph_name + '.tar.zst')
    request = requests.get(download_path, stream=True)
    with open(save_path, 'wb') as f:
        for chunk in request.iter_content(chunk_size=16*1024):
            f.write(chunk)
    # Extract file with zstandard
    dctx = ZstdDecompressor()
    # source: https://gist.github.com/scivision/ad241e9cf0474e267240e196d7545eca
    with tempfile.TemporaryFile(suffix=".tar") as ofh:
        with save_path.open("rb") as ifh:
            dctx.copy_stream(ifh, ofh)
        ofh.seek(0)
        with tarfile.open(fileobj=ofh) as z:
            z.extractall(graph_path)

def load_graph(graph_name: str, output='igraph'):
    """
    Loads a Translator graph into igraph.

    Params
    ------
    graph_name : str
        The name of the graph - it should be in graph_downloader.GRAPHS. 
    """
    if graph_name not in GRAPHS.keys():
        raise ValueError('graph_name not found')
    graph_path = CACHE_DIR / graph_name
    metadata_path = graph_path / 'graph-metadata.json'
    nodes_path = graph_path / 'nodes.jsonl'
    edges_path = graph_path / 'edges.jsonl'
    os.makedirs(graph_path, exist_ok=True)
    # download metadata and main download
    if not os.path.exists(metadata_path) or not os.path.exists(nodes_path) or not os.path.exists(edges_path):
        # Download the .tar.zst file
        download_graph(graph_name)
    # load graph
    from . import kg_loader
    nodes, edges, node_types, edge_types = kg_loader.import_kg2_jsonl(nodes_path, edges_path)
    if output == 'igraph':
        return kg_loader.load_kg2_igraph_from_data(nodes, edges, node_types, edge_types)
    #else:
        # TODO: not implemented yet
    #    return kg_loader.load_kg2_networkx_from_data(nodes, edges, node_types, edge_types)
