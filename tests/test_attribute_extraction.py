"""Tests for TCT.attribute_extraction — rich metadata extraction from TRAPI attributes."""

from TCT.attribute_extraction import (
    _collect,
    extract_confidence_scores,
    extract_publications,
    extract_rich_edge_attributes,
    extract_supporting_text,
)


# ---------------------------------------------------------------------------
# _collect tests
# ---------------------------------------------------------------------------


class TestCollect:
    def test_collect_list(self):
        target = []
        _collect(target, ["a", "b"])
        assert target == ["a", "b"]

    def test_collect_scalar(self):
        target = []
        _collect(target, "x")
        assert target == ["x"]

    def test_collect_none(self):
        target = ["existing"]
        _collect(target, None)
        assert target == ["existing"]


# ---------------------------------------------------------------------------
# extract_publications tests
# ---------------------------------------------------------------------------


class TestExtractPublications:
    def test_top_level_list(self):
        attrs = [{"attribute_type_id": "biolink:publications", "value": ["PMID:1", "PMID:2"]}]
        assert extract_publications(attrs) == ["PMID:1", "PMID:2"]

    def test_top_level_scalar(self):
        attrs = [{"attribute_type_id": "biolink:publications", "value": "PMID:1"}]
        assert extract_publications(attrs) == ["PMID:1"]

    def test_nested_in_study_result(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_supporting_study_result",
                "value": "study",
                "attributes": [
                    {"attribute_type_id": "biolink:publications", "value": ["PMID:99"]},
                ],
            }
        ]
        assert extract_publications(attrs) == ["PMID:99"]

    def test_both_top_and_nested(self):
        attrs = [
            {"attribute_type_id": "biolink:publications", "value": "PMID:1"},
            {
                "attribute_type_id": "biolink:has_supporting_study_result",
                "value": "study",
                "attributes": [
                    {"attribute_type_id": "biolink:publications", "value": "PMID:2"},
                ],
            },
        ]
        result = extract_publications(attrs)
        assert "PMID:1" in result
        assert "PMID:2" in result

    def test_empty_attributes(self):
        assert extract_publications([]) == []

    def test_no_publication_attributes(self):
        attrs = [{"attribute_type_id": "biolink:some_other_type", "value": "foo"}]
        assert extract_publications(attrs) == []

    def test_bare_int_pmid_normalized(self):
        attrs = [{"attribute_type_id": "biolink:publications", "value": 12345}]
        assert extract_publications(attrs) == ["PMID:12345"]

    def test_bare_digit_string_pmid_normalized(self):
        attrs = [{"attribute_type_id": "biolink:publications", "value": ["12345", "PMID:1"]}]
        assert extract_publications(attrs) == ["PMID:12345", "PMID:1"]

    def test_non_pmid_values_unchanged(self):
        attrs = [{"attribute_type_id": "biolink:publications",
                  "value": ["PMC123", "http://example.com/x"]}]
        assert extract_publications(attrs) == ["PMC123", "http://example.com/x"]


# ---------------------------------------------------------------------------
# extract_supporting_text tests
# ---------------------------------------------------------------------------


class TestExtractSupportingText:
    def test_modern_supporting_text(self):
        attrs = [{"attribute_type_id": "biolink:supporting_text", "value": "Some text."}]
        assert extract_supporting_text(attrs) == ["Some text."]

    def test_legacy_sentences(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_evidence",
                "original_attribute_name": "sentences",
                "value": "Legacy text.",
            }
        ]
        assert extract_supporting_text(attrs) == ["Legacy text."]

    def test_nested_in_study_result(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_supporting_study_result",
                "value": "study",
                "attributes": [
                    {"attribute_type_id": "biolink:supporting_text", "value": "Nested text."},
                ],
            }
        ]
        assert extract_supporting_text(attrs) == ["Nested text."]

    def test_empty(self):
        assert extract_supporting_text([]) == []


# ---------------------------------------------------------------------------
# extract_confidence_scores tests
# ---------------------------------------------------------------------------


class TestExtractConfidenceScores:
    def test_tmkp_score(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_confidence_level",
                "original_attribute_name": "tmkp_confidence_score",
                "value": 0.87,
            }
        ]
        scores = extract_confidence_scores(attrs)
        assert scores == {"tmkp_confidence_score": 0.87}

    def test_extraction_confidence(self):
        attrs = [
            {
                "attribute_type_id": "biolink:extraction_confidence_score",
                "value": 0.95,
            }
        ]
        scores = extract_confidence_scores(attrs)
        assert scores == {"extraction_confidence_score": 0.95}

    def test_combined_score(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_confidence_level",
                "original_attribute_name": "Combined_score",
                "value": 900,
            }
        ]
        scores = extract_confidence_scores(attrs)
        assert scores == {"Combined_score": 900.0}

    def test_nested_score(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_supporting_study_result",
                "value": "study",
                "attributes": [
                    {
                        "attribute_type_id": "biolink:extraction_confidence_score",
                        "value": 0.5,
                    },
                ],
            }
        ]
        scores = extract_confidence_scores(attrs)
        assert scores == {"extraction_confidence_score": 0.5}

    def test_empty(self):
        assert extract_confidence_scores([]) == {}

    def test_multiple_score_types(self):
        attrs = [
            {
                "attribute_type_id": "biolink:has_confidence_level",
                "original_attribute_name": "tmkp_confidence_score",
                "value": 0.8,
            },
            {
                "attribute_type_id": "biolink:has_confidence_level",
                "original_attribute_name": "Combined_score",
                "value": 700,
            },
        ]
        scores = extract_confidence_scores(attrs)
        assert scores["tmkp_confidence_score"] == 0.8
        assert scores["Combined_score"] == 700.0


# ---------------------------------------------------------------------------
# extract_rich_edge_attributes tests
# ---------------------------------------------------------------------------


class TestExtractRichEdgeAttributes:
    def test_returns_all_three_keys(self):
        result = extract_rich_edge_attributes([])
        assert set(result.keys()) == {"publications", "supporting_text", "confidence_scores"}

    def test_mixed_attributes(self):
        attrs = [
            {"attribute_type_id": "biolink:publications", "value": ["PMID:1"]},
            {"attribute_type_id": "biolink:supporting_text", "value": "text"},
            {
                "attribute_type_id": "biolink:has_confidence_level",
                "original_attribute_name": "tmkp_confidence_score",
                "value": 0.9,
            },
        ]
        result = extract_rich_edge_attributes(attrs)
        assert result["publications"] == ["PMID:1"]
        assert result["supporting_text"] == ["text"]
        assert result["confidence_scores"]["tmkp_confidence_score"] == 0.9

    def test_max_depth_guard(self):
        """Deeply nested attributes don't cause infinite recursion."""
        # Build nesting 10 levels deep (exceeds _MAX_DEPTH of 5)
        inner = {"attribute_type_id": "biolink:publications", "value": "PMID:deep"}
        for _ in range(10):
            inner = {
                "attribute_type_id": "biolink:has_supporting_study_result",
                "value": "study",
                "attributes": [inner],
            }
        result = extract_rich_edge_attributes([inner])
        # Should not crash; publications beyond depth 5 won't be found
        assert isinstance(result["publications"], list)
