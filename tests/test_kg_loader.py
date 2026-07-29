"""Tests for TCT.kg_loader.

These exercise the file-parsing and graph-construction helpers with tiny
on-disk fixtures (CSV/TSV/JSONL, plain and gzipped). No network access.
"""

import gzip
import json

import pytest

from TCT import kg_loader


# ---------------------------------------------------------------------------
# Fixture file builders
# ---------------------------------------------------------------------------

def _write(path, text):
    path.write_text(text)
    return str(path)


def _write_gz(path, text):
    with gzip.open(path, "wt") as f:
        f.write(text)
    return str(path)


NODE_CSV = "id,name,category\nN1,Node One,biolink:Gene\nN2,Node Two,biolink:Drug\nN3,Node Three,biolink:Gene\n"
EDGE_CSV = (
    "subject,object,predicate,id,primary_knowledge_source\n"
    "N1,N2,biolink:related_to,1,infores:a\n"
    "N2,N3,biolink:affects,2,infores:b\n"
    "N1,N3,biolink:related_to,3,infores:a\n"
)

NODE_LINES = [
    {"id": "N1", "name": "Node One", "category": ["biolink:Gene"]},
    {"id": "N2", "name": "Node Two", "category": ["biolink:Drug"]},
    {"id": "N3", "name": "Node Three", "category": ["biolink:Gene"]},
]
EDGE_LINES = [
    {"subject": "N1", "object": "N2", "predicate": "biolink:related_to", "id": "1", "primary_knowledge_source": "infores:a"},
    {"subject": "N2", "object": "N3", "predicate": "biolink:affects", "id": "2"},
    {"subject": "N1", "object": "N3", "predicate": "biolink:related_to", "id": "3"},
]


def _jsonl(lines):
    return "".join(json.dumps(line) + "\n" for line in lines)


# ---------------------------------------------------------------------------
# import_kg2_csv
# ---------------------------------------------------------------------------

class TestImportKg2Csv:
    def test_basic_csv(self, tmp_path):
        node_f = _write(tmp_path / "nodes.csv", NODE_CSV)
        edge_f = _write(tmp_path / "edges.csv", EDGE_CSV)
        nodes, edges, node_types, edge_types = kg_loader.import_kg2_csv(node_f, edge_f, verbose=False)

        assert len(nodes) == 3
        # node tuple: (id, name, label_id, identifier, source)
        assert nodes[0][0] == "N1"
        assert nodes[0][1] == "Node One"
        # two distinct edge predicates
        assert set(edge_types.values()) == {"biolink:related_to", "biolink:affects"}
        # node_types maps int -> category string
        assert "biolink:Gene" in node_types.values()
        # edges reindexed to integer node indices by default
        assert all(isinstance(a, int) and isinstance(b, int) for (a, b) in edges)

    def test_tsv_delimiter(self, tmp_path):
        node_f = _write(tmp_path / "nodes.tsv", NODE_CSV.replace(",", "\t"))
        edge_f = _write(tmp_path / "edges.tsv", EDGE_CSV.replace(",", "\t"))
        nodes, edges, node_types, edge_types = kg_loader.import_kg2_csv(node_f, edge_f, verbose=False)
        assert len(nodes) == 3
        assert len(edges) == 3

    def test_gzip_inputs(self, tmp_path):
        node_f = _write_gz(tmp_path / "nodes.csv.gz", NODE_CSV)
        edge_f = _write_gz(tmp_path / "edges.csv.gz", EDGE_CSV)
        nodes, edges, _, _ = kg_loader.import_kg2_csv(node_f, edge_f, verbose=False)
        assert len(nodes) == 3
        assert len(edges) == 3

    def test_no_name_column(self, tmp_path):
        node_f = _write(tmp_path / "nodes.csv", "id,category\nN1,biolink:Gene\n")
        edge_f = _write(tmp_path / "edges.csv", "subject,object,predicate,id\nN1,N1,biolink:related_to,1\n")
        # verbose=True exercises the progress-print branch
        nodes, _, _, _ = kg_loader.import_kg2_csv(node_f, edge_f, verbose=True)
        # name falls back to the identifier
        assert nodes[0][1] == "N1"

    def test_flags_no_types_no_edge_types(self, tmp_path):
        node_f = _write(tmp_path / "nodes.csv", NODE_CSV)
        edge_f = _write(tmp_path / "edges.csv", EDGE_CSV)
        nodes, edges, node_types, edge_types = kg_loader.import_kg2_csv(
            node_f, edge_f, use_node_types=False, use_edge_types=False, verbose=False
        )
        # with use_node_types False, label slot is True and node_types empty
        assert node_types == {}
        assert edge_types == {}
        assert all(v is True for v in edges.values())

    def test_edge_properties_and_filter_and_remove_unused(self, tmp_path):
        node_f = _write(tmp_path / "nodes.csv", NODE_CSV)
        edge_f = _write(tmp_path / "edges.csv", EDGE_CSV)
        nodes, edges, _, _ = kg_loader.import_kg2_csv(
            node_f,
            edge_f,
            edges_to_include={"biolink:related_to"},
            remove_unused_nodes=True,
            use_edge_properties=True,
            reindex_edges=True,
            verbose=False,
        )
        # only related_to edges kept (2 of them)
        assert len(edges) == 2
        # edge property dicts carry primary_knowledge_source + int id
        sample = next(iter(edges.values()))
        assert sample["primary_knowledge_source"] == "infores:a"
        assert isinstance(sample["id"], int)


# ---------------------------------------------------------------------------
# import_kg2_jsonl
# ---------------------------------------------------------------------------

class TestImportKg2Jsonl:
    def test_two_file_mode(self, tmp_path):
        node_f = _write(tmp_path / "nodes.jsonl", _jsonl(NODE_LINES))
        edge_f = _write(tmp_path / "edges.jsonl", _jsonl(EDGE_LINES))
        nodes, edges, node_types, edge_types = kg_loader.import_kg2_jsonl(node_f, edge_f, verbose=False)
        assert len(nodes) == 3
        assert len(edges) == 3
        assert "biolink:related_to" in edge_types.values()

    def test_single_file_mode(self, tmp_path):
        combined = _write(tmp_path / "all.jsonl", _jsonl(NODE_LINES + EDGE_LINES))
        nodes, edges, _, _ = kg_loader.import_kg2_jsonl(combined, None, verbose=False)
        assert len(nodes) == 3
        assert len(edges) == 3

    def test_gzip_and_flags(self, tmp_path):
        node_f = _write_gz(tmp_path / "nodes.jsonl.gz", _jsonl(NODE_LINES))
        edge_f = _write_gz(tmp_path / "edges.jsonl.gz", _jsonl(EDGE_LINES))
        nodes, edges, node_types, edge_types = kg_loader.import_kg2_jsonl(
            node_f,
            edge_f,
            remove_unused_nodes=False,
            use_node_types=False,
            use_edge_types=False,
            reindex_edges=False,
            use_edge_properties=True,
            verbose=True,
        )
        assert node_types == {}
        # reindex_edges False keeps original string ids as edge keys
        assert all(isinstance(a, str) for (a, b) in edges)


# ---------------------------------------------------------------------------
# to_sparse / symmetrize_matrix
# ---------------------------------------------------------------------------

def test_to_sparse():
    nodes = ["N0", "N1", "N2"]
    edges = {(0, 1): 5, (1, 2): 7}
    mat = kg_loader.to_sparse(nodes, edges)
    assert mat.shape == (3, 3)
    assert mat[0, 1] == 5
    assert mat[1, 2] == 7
    assert mat[2, 0] == 0


def test_symmetrize_matrix():
    nodes = ["N0", "N1", "N2"]
    edges = {(0, 1): 1, (1, 2): 1}
    mat = kg_loader.to_sparse(nodes, edges).tocsr()
    sym = kg_loader.symmetrize_matrix(mat)
    dense = sym.toarray()
    assert dense[0, 1] == dense[1, 0]
    assert dense[1, 2] == dense[2, 1]


# ---------------------------------------------------------------------------
# graph constructors (igraph / networkx)
# ---------------------------------------------------------------------------

class TestGraphConstructors:
    def test_load_kg2_igraph_from_data_default(self, tmp_path):
        node_f = _write(tmp_path / "nodes.jsonl", _jsonl(NODE_LINES))
        edge_f = _write(tmp_path / "edges.jsonl", _jsonl(EDGE_LINES))
        data = kg_loader.import_kg2_jsonl(node_f, edge_f, reindex_edges=False, verbose=False)
        graph = kg_loader.load_kg2_igraph_from_data(*data)
        assert graph.vcount() == 3
        assert graph.ecount() == 3

    def test_load_kg2_igraph_from_data_low_memory(self, tmp_path):
        node_f = _write(tmp_path / "nodes.jsonl", _jsonl(NODE_LINES))
        edge_f = _write(tmp_path / "edges.jsonl", _jsonl(EDGE_LINES))
        data = kg_loader.import_kg2_jsonl(node_f, edge_f, reindex_edges=False, verbose=False)
        graph = kg_loader.load_kg2_igraph_from_data(*data, low_memory=True)
        assert graph.vcount() == 3

    def test_load_kg2_igraph_from_data_edge_properties(self, tmp_path):
        node_f = _write(tmp_path / "nodes.jsonl", _jsonl(NODE_LINES))
        edge_f = _write(tmp_path / "edges.jsonl", _jsonl(EDGE_LINES))
        data = kg_loader.import_kg2_jsonl(
            node_f, edge_f, reindex_edges=False, use_edge_properties=True, verbose=False
        )
        graph = kg_loader.load_kg2_igraph_from_data(*data, use_edge_properties=True)
        assert graph.ecount() == 3

    def test_load_kg2_networkx(self, tmp_path):
        combined = _write(tmp_path / "all.jsonl", _jsonl(NODE_LINES + EDGE_LINES))
        g_undirected = kg_loader.load_kg2_networkx(combined, verbose=False)
        assert g_undirected.number_of_nodes() == 3
        g_directed = kg_loader.load_kg2_networkx(combined, directed=True, verbose=False)
        assert g_directed.is_directed()

    def test_load_kg2_igraph_from_file(self, tmp_path):
        combined = _write(tmp_path / "all.jsonl", _jsonl(NODE_LINES + EDGE_LINES))
        graph = kg_loader.load_kg2_igraph(combined, verbose=True)
        assert graph.vcount() == 3

    def test_load_kg2_networkx_bad_extension(self, tmp_path):
        bad = _write(tmp_path / "graph.txt", "nope")
        with pytest.raises(Exception):
            kg_loader.load_kg2_networkx(bad)


# ---------------------------------------------------------------------------
# load_kg2 dispatch
# ---------------------------------------------------------------------------

def test_load_kg2_rejects_unknown_extension(tmp_path):
    bad = _write(tmp_path / "graph.txt", "nope")
    with pytest.raises(Exception):
        kg_loader.load_kg2(bad)


def test_load_kg2_jsonl_writes_mtx(tmp_path):
    combined = _write(tmp_path / "all.jsonl", _jsonl(NODE_LINES + EDGE_LINES))
    mtx = tmp_path / "out.mtx"
    nodes, edges, node_types, edge_types, mat = kg_loader.load_kg2(
        combined, mtx_filename=str(mtx), verbose=False
    )
    assert mtx.exists()
    # second call reads the existing mtx back
    _, _, _, _, mat2 = kg_loader.load_kg2(combined, mtx_filename=str(mtx), verbose=False)
    assert mat2.shape[0] == mat.shape[0]


def test_jsonl_node_without_name(tmp_path):
    lines = [{"id": "N1", "category": ["biolink:Gene"]}]  # no name key
    edges = [{"subject": "N1", "object": "N1", "predicate": "biolink:related_to", "id": "1"}]
    f = _write(tmp_path / "all.jsonl", _jsonl(lines + edges))
    nodes, _, _, _ = kg_loader.import_kg2_jsonl(f, None, remove_unused_nodes=False, verbose=False)
    assert nodes[0][1] == "N1"  # name falls back to identifier


def test_load_kg2_igraph_low_memory_and_bad_extension(tmp_path):
    combined = _write(tmp_path / "all.jsonl", _jsonl(NODE_LINES + EDGE_LINES))
    graph = kg_loader.load_kg2_igraph(combined, low_memory=True, verbose=False)
    assert graph.vcount() == 3
    with pytest.raises(Exception):
        kg_loader.load_kg2_igraph(_write(tmp_path / "g.txt", "nope"))


def test_igraph_from_data_list_valued_property(tmp_path):
    node_f = _write(tmp_path / "nodes.jsonl", _jsonl(NODE_LINES))
    edge_lines = [
        {"subject": "N1", "object": "N2", "predicate": "biolink:related_to", "id": "1",
         "properties": {"pubs": ["PMID:1", "PMID:2"]}},
    ]
    edge_f = _write(tmp_path / "edges.jsonl", _jsonl(edge_lines))
    data = kg_loader.import_kg2_jsonl(
        node_f, edge_f, reindex_edges=False, use_edge_properties=True, remove_unused_nodes=False, verbose=False
    )
    graph = kg_loader.load_kg2_igraph_from_data(*data, use_edge_properties=True)
    assert graph.ecount() == 1
