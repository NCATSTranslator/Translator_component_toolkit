"""Tests for the TranslatorResources container class."""

import pytest
import pandas as pd

from TCT.translator_resources import TranslatorResources


class TestTranslatorResources:
    """Unit tests for TranslatorResources dataclass."""

    def test_basic_construction(self):
        """TranslatorResources can be constructed with required fields."""
        api_names = {"API1": "https://example.com/query"}
        meta_kg = pd.DataFrame({"API": ["API1"], "Predicate": ["biolink:related_to"],
                                "Subject": ["biolink:Gene"], "Object": ["biolink:Disease"],
                                "URL": ["https://example.com/query"]})
        res = TranslatorResources(api_names=api_names, meta_kg=meta_kg)
        assert res.api_names == api_names
        assert res.meta_kg.shape == (1, 5)
        assert res.api_predicates == {}

    def test_construction_with_predicates(self):
        """TranslatorResources accepts optional api_predicates."""
        api_names = {"API1": "https://example.com/query"}
        meta_kg = pd.DataFrame({"API": ["API1"], "Predicate": ["biolink:related_to"],
                                "Subject": ["biolink:Gene"], "Object": ["biolink:Disease"],
                                "URL": ["https://example.com/query"]})
        predicates = {"API1": ["biolink:related_to"]}
        res = TranslatorResources(api_names=api_names, meta_kg=meta_kg, api_predicates=predicates)
        assert res.api_predicates == predicates

    def test_from_tuple(self):
        """from_tuple() creates an instance from a (api_names, meta_kg, api_predicates) tuple."""
        api_names = {"API1": "https://example.com/query"}
        meta_kg = pd.DataFrame({"API": ["API1"]})
        predicates = {"API1": ["biolink:related_to"]}
        triplet = (api_names, meta_kg, predicates)
        res = TranslatorResources.from_tuple(triplet)
        assert res.api_names == api_names
        assert res.api_predicates == predicates

    def test_as_tuple(self):
        """as_tuple() returns the (api_names, meta_kg, api_predicates) tuple."""
        api_names = {"API1": "https://example.com/query"}
        meta_kg = pd.DataFrame({"API": ["API1"]})
        predicates = {"API1": ["biolink:related_to"]}
        res = TranslatorResources(api_names=api_names, meta_kg=meta_kg, api_predicates=predicates)
        t = res.as_tuple()
        assert t[0] is api_names
        assert t[1] is meta_kg
        assert t[2] is predicates

    def test_roundtrip_tuple(self):
        """from_tuple(x.as_tuple()) preserves data."""
        api_names = {"API1": "https://example.com/query"}
        meta_kg = pd.DataFrame({"API": ["API1"]})
        predicates = {"API1": ["biolink:related_to"]}
        original = TranslatorResources(api_names=api_names, meta_kg=meta_kg, api_predicates=predicates)
        roundtripped = TranslatorResources.from_tuple(original.as_tuple())
        assert roundtripped.api_names == original.api_names
        assert roundtripped.api_predicates == original.api_predicates

    def test_default_api_predicates_not_shared(self):
        """Each instance gets its own default dict for api_predicates."""
        res1 = TranslatorResources(api_names={}, meta_kg=pd.DataFrame())
        res2 = TranslatorResources(api_names={}, meta_kg=pd.DataFrame())
        res1.api_predicates["test"] = ["value"]
        assert "test" not in res2.api_predicates

    def test_import_from_tct(self):
        """TranslatorResources is importable from the top-level TCT package."""
        import TCT
        assert hasattr(TCT, "TranslatorResources")
        assert TCT.TranslatorResources is TranslatorResources

    @pytest.mark.network
    def test_load_from_live_apis(self):
        """load() fetches resources from live Translator APIs."""
        res = TranslatorResources.load()
        assert isinstance(res.api_names, dict) and len(res.api_names) > 0
        assert isinstance(res.meta_kg, pd.DataFrame) and res.meta_kg.shape[0] > 0
        assert isinstance(res.api_predicates, dict) and len(res.api_predicates) > 0

    def test_filter_scopes_to_specified_apis(self):
        """filter() returns a new TranslatorResources with only the specified APIs."""
        api_names = {
            "API_A": "https://a.example.com/query",
            "API_B": "https://b.example.com/query",
            "API_C": "https://c.example.com/query",
        }
        meta_kg = pd.DataFrame({
            "API": ["API_A", "API_B", "API_C"],
            "Predicate": ["biolink:related_to", "biolink:treats", "biolink:affects"],
            "Subject": ["biolink:Gene", "biolink:Drug", "biolink:Disease"],
            "Object": ["biolink:Disease", "biolink:Disease", "biolink:Gene"],
            "URL": ["https://a.example.com/query", "https://b.example.com/query", "https://c.example.com/query"],
        })
        predicates = {
            "API_A": ["biolink:related_to"],
            "API_B": ["biolink:treats"],
            "API_C": ["biolink:affects"],
        }
        res = TranslatorResources(api_names=api_names, meta_kg=meta_kg, api_predicates=predicates)
        filtered = res.filter(["API_A", "API_C"])

        assert set(filtered.api_names.keys()) == {"API_A", "API_C"}
        assert set(filtered.meta_kg["API"]) == {"API_A", "API_C"}
        assert set(filtered.api_predicates.keys()) == {"API_A", "API_C"}

    def test_filter_ignores_unknown_apis(self):
        """filter() silently ignores API names not present in the resources."""
        res = TranslatorResources(
            api_names={"API_A": "https://a.example.com/query"},
            meta_kg=pd.DataFrame({"API": ["API_A"], "Predicate": ["biolink:related_to"],
                                  "Subject": ["biolink:Gene"], "Object": ["biolink:Disease"],
                                  "URL": ["https://a.example.com/query"]}),
            api_predicates={"API_A": ["biolink:related_to"]},
        )
        filtered = res.filter(["API_A", "NONEXISTENT"])
        assert set(filtered.api_names.keys()) == {"API_A"}

    def test_filter_returns_new_instance(self):
        """filter() does not mutate the original resources."""
        res = TranslatorResources(
            api_names={"API_A": "https://a.example.com/query", "API_B": "https://b.example.com/query"},
            meta_kg=pd.DataFrame({"API": ["API_A", "API_B"], "Predicate": ["biolink:related_to", "biolink:treats"],
                                  "Subject": ["biolink:Gene", "biolink:Drug"], "Object": ["biolink:Disease", "biolink:Disease"],
                                  "URL": ["https://a.example.com/query", "https://b.example.com/query"]}),
            api_predicates={"API_A": ["biolink:related_to"], "API_B": ["biolink:treats"]},
        )
        filtered = res.filter(["API_A"])
        assert len(res.api_names) == 2  # original unchanged
        assert len(filtered.api_names) == 1

    def test_rebuild_predicates(self):
        """rebuild_predicates() reconstructs api_predicates from meta_kg."""
        meta_kg = pd.DataFrame({
            "API": ["API_A", "API_A", "API_B"],
            "Predicate": ["biolink:related_to", "biolink:treats", "biolink:affects"],
            "Subject": ["biolink:Gene", "biolink:Drug", "biolink:Disease"],
            "Object": ["biolink:Disease", "biolink:Disease", "biolink:Gene"],
            "URL": ["https://a.example.com/query", "https://a.example.com/query", "https://b.example.com/query"],
        })
        res = TranslatorResources(api_names={"API_A": "url", "API_B": "url"}, meta_kg=meta_kg, api_predicates={})
        res.rebuild_predicates()
        assert set(res.api_predicates.keys()) == {"API_A", "API_B"}
        assert set(res.api_predicates["API_A"]) == {"biolink:related_to", "biolink:treats"}
        assert res.api_predicates["API_B"] == ["biolink:affects"]
