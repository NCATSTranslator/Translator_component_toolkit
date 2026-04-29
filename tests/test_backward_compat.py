"""Tests for backward-compatibility adapters.

Ensures old-style tuple unpacking and legacy keyword arguments continue to work
with deprecation warnings.
"""

import warnings

import pandas as pd
import pytest

from TCT.results import (
    KnowledgeGraph,
    NeighborhoodResult,
    ParsedKnowledgeGraph,
    PathResult,
)
from TCT.translator_resources import TranslatorResources


# ---------------------------------------------------------------------------
# NeighborhoodResult tuple unpacking (Adapter 1)
# ---------------------------------------------------------------------------


class TestNeighborhoodResultUnpacking:
    def test_tuple_unpack_emits_deprecation_warning(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        ranked = pd.DataFrame({"col": [1]})
        result = NeighborhoodResult(
            input_node_id="NCBIGene:3845",
            knowledge_graph=kg,
            parsed=parsed,
            ranked=ranked,
        )

        with pytest.warns(DeprecationWarning, match="Unpacking NeighborhoodResult"):
            a, b, c, d = result

        assert a == "NCBIGene:3845"
        assert isinstance(b, KnowledgeGraph)
        assert isinstance(c, ParsedKnowledgeGraph)
        assert isinstance(d, pd.DataFrame)

    def test_len_returns_4(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = NeighborhoodResult(
            input_node_id="id",
            knowledge_graph=kg,
            parsed=parsed,
            ranked=pd.DataFrame(),
        )
        assert len(result) == 4


# ---------------------------------------------------------------------------
# PathResult tuple unpacking (Adapter 2)
# ---------------------------------------------------------------------------


class TestPathResultUnpacking:
    def test_tuple_unpack_emits_deprecation_warning(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = PathResult(
            paths=pd.DataFrame(),
            node1_id="n1",
            node2_id="n2",
            knowledge_graph1=kg,
            knowledge_graph2=kg,
            parsed1=parsed,
            parsed2=parsed,
            ranked1=pd.DataFrame(),
            ranked2=pd.DataFrame(),
        )

        with pytest.warns(DeprecationWarning, match="Unpacking PathResult"):
            p, id1, id2, kg1, kg2, p1, p2, r1, r2 = result

        assert isinstance(p, pd.DataFrame)
        assert id1 == "n1"
        assert id2 == "n2"
        assert isinstance(kg1, KnowledgeGraph)
        assert isinstance(kg2, KnowledgeGraph)
        assert isinstance(p1, ParsedKnowledgeGraph)
        assert isinstance(p2, ParsedKnowledgeGraph)
        assert isinstance(r1, pd.DataFrame)
        assert isinstance(r2, pd.DataFrame)

    def test_len_returns_9(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = PathResult(
            paths=pd.DataFrame(),
            node1_id="n1",
            node2_id="n2",
            knowledge_graph1=kg,
            knowledge_graph2=kg,
            parsed1=parsed,
            parsed2=parsed,
            ranked1=pd.DataFrame(),
            ranked2=pd.DataFrame(),
        )
        assert len(result) == 9


# ---------------------------------------------------------------------------
# TranslatorResources tuple unpacking (Adapter 3)
# ---------------------------------------------------------------------------


class TestTranslatorResourcesUnpacking:
    def test_tuple_unpack_emits_deprecation_warning(self):
        res = TranslatorResources(
            api_names={"API1": "url"},
            meta_kg=pd.DataFrame({"API": ["API1"]}),
            api_predicates={"API1": ["biolink:related_to"]},
        )

        with pytest.warns(DeprecationWarning, match="Unpacking TranslatorResources"):
            names, kg, preds = res

        assert names == {"API1": "url"}
        assert isinstance(kg, pd.DataFrame)
        assert preds == {"API1": ["biolink:related_to"]}

    def test_len_returns_3(self):
        res = TranslatorResources(
            api_names={}, meta_kg=pd.DataFrame(), api_predicates={}
        )
        assert len(res) == 3


# ---------------------------------------------------------------------------
# KnowledgeGraph __eq__ and __bool__ (Adapter 10)
# ---------------------------------------------------------------------------


class TestKnowledgeGraphDictCompat:
    def test_eq_with_dict(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        assert kg == sample_kg_result
        assert not (kg == {})

    def test_eq_with_kg(self, sample_kg_result):
        kg1 = KnowledgeGraph(edges=sample_kg_result)
        kg2 = KnowledgeGraph(edges=sample_kg_result)
        assert kg1 == kg2

    def test_eq_not_implemented_for_other_types(self):
        kg = KnowledgeGraph(edges={})
        assert kg.__eq__("string") is NotImplemented

    def test_bool_empty(self):
        assert not KnowledgeGraph(edges={})

    def test_bool_non_empty(self, sample_kg_result):
        assert KnowledgeGraph(edges=sample_kg_result)


class TestParsedKnowledgeGraphDictCompat:
    def test_eq_with_dict(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        assert parsed == parsed.entries
        assert not (parsed == {})

    def test_eq_with_pkg(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed1 = kg.parse()
        parsed2 = kg.parse()
        assert parsed1 == parsed2

    def test_eq_not_implemented_for_other_types(self):
        pkg = ParsedKnowledgeGraph(entries={})
        assert pkg.__eq__(42) is NotImplemented

    def test_bool_empty(self):
        assert not ParsedKnowledgeGraph(entries={})

    def test_bool_non_empty(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        assert kg.parse()


# ---------------------------------------------------------------------------
# Legacy kwargs for Neiborhood_finder / Path_finder (Adapters 5-6)
# ---------------------------------------------------------------------------


class TestLegacyKwargsResolveResources:
    def test_resolve_resources_with_resources_obj(self):
        from TCT.TCT import _resolve_resources

        res = TranslatorResources(
            api_names={"A": "url"}, meta_kg=pd.DataFrame(), api_predicates={}
        )
        assert _resolve_resources(res) is res

    def test_resolve_resources_with_legacy_kwargs(self):
        from TCT.TCT import _resolve_resources

        with pytest.warns(DeprecationWarning, match="APInames/metaKG/API_predicates"):
            result = _resolve_resources(
                None,
                APInames={"A": "url"},
                metaKG=pd.DataFrame(),
                API_predicates={"A": ["p"]},
            )
        assert isinstance(result, TranslatorResources)
        assert result.api_names == {"A": "url"}

    def test_resolve_resources_bad_type_raises(self):
        from TCT.TCT import _resolve_resources

        with pytest.raises(TypeError, match="Expected TranslatorResources"):
            _resolve_resources("not-a-resource")

    def test_resolve_resources_none_raises(self):
        from TCT.TCT import _resolve_resources

        with pytest.raises(TypeError, match="Either 'resources'"):
            _resolve_resources(None)


# ---------------------------------------------------------------------------
# Legacy kwargs for query_KP / parallel_api_query (Adapters 7-8)
# ---------------------------------------------------------------------------


class TestLegacyQueryKwargsResolveResources:
    def test_resolve_query_resources_with_resources_obj(self):
        from TCT.translator_query import _resolve_query_resources

        res = TranslatorResources(
            api_names={"A": "url"}, meta_kg=pd.DataFrame(), api_predicates={}
        )
        assert _resolve_query_resources(res) is res

    def test_resolve_query_resources_with_legacy_kwargs(self):
        from TCT.translator_query import _resolve_query_resources

        with pytest.warns(DeprecationWarning, match="APInames/metaKG/API_predicates"):
            result = _resolve_query_resources(
                None, APInames={"A": "url"}, API_predicates={"A": ["p"]}
            )
        assert isinstance(result, TranslatorResources)
        assert result.api_names == {"A": "url"}

    def test_resolve_query_resources_bad_type_raises(self):
        from TCT.translator_query import _resolve_query_resources

        with pytest.raises(TypeError, match="Expected TranslatorResources"):
            _resolve_query_resources("bad")

    def test_resolve_query_resources_none_raises(self):
        from TCT.translator_query import _resolve_query_resources

        with pytest.raises(TypeError, match="Either 'resources'"):
            _resolve_query_resources(None)


# ---------------------------------------------------------------------------
# TCT_Visualization shim (Adapter 9)
# ---------------------------------------------------------------------------


class TestTCTVisualizationShim:
    def test_import_emits_deprecation_warning(self):
        import importlib
        import sys

        # Remove from cache to force re-import
        mod_name = "TCT.TCT_Visualization"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            importlib.import_module(mod_name)

        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert any("TCT.TCT_Visualization is deprecated" in str(x.message) for x in dep_warnings)
