"""Extract structured metadata from TRAPI edge attributes."""

from __future__ import annotations

_MAX_DEPTH = 5


def _collect(target: list, value) -> None:
    """Append scalar or extend list into target."""
    if value is None:
        return
    if isinstance(value, list):
        target.extend(value)
    else:
        target.append(value)


def _iter_nested_attributes(attributes: list[dict], depth: int = 0):
    """Yield attributes, recursing into has_supporting_study_result."""
    for attr in attributes:
        yield attr
        if depth < _MAX_DEPTH and attr.get("attribute_type_id") == "biolink:has_supporting_study_result":
            nested = attr.get("attributes", [])
            if isinstance(nested, list):
                yield from _iter_nested_attributes(nested, depth + 1)


def extract_publications(attributes: list[dict]) -> list[str]:
    """Extract publication IDs from TRAPI attributes.

    Handles:
    - Top-level biolink:publications
    - Nested inside biolink:has_supporting_study_result
    - Both list and scalar values
    """
    pubs: list[str] = []
    for attr in _iter_nested_attributes(attributes):
        if attr.get("attribute_type_id") == "biolink:publications":
            _collect(pubs, attr.get("value"))
    return pubs


def extract_supporting_text(attributes: list[dict]) -> list[str]:
    """Extract supporting text from TRAPI attributes.

    Handles:
    - attribute_type_id == "biolink:supporting_text"
    - original_attribute_name == "sentences" (legacy)
    - Nested inside biolink:has_supporting_study_result
    """
    texts: list[str] = []
    for attr in _iter_nested_attributes(attributes):
        if attr.get("attribute_type_id") == "biolink:supporting_text":
            _collect(texts, attr.get("value"))
        elif attr.get("original_attribute_name") == "sentences":
            _collect(texts, attr.get("value"))
    return texts


def extract_confidence_scores(attributes: list[dict]) -> dict[str, float]:
    """Extract confidence scores from TRAPI attributes.

    Handles:
    - original_attribute_name == "tmkp_confidence_score"
    - attribute_type_id == "biolink:extraction_confidence_score"
    - original_attribute_name == "Combined_score" (STRING DB)
    - Nested inside biolink:has_supporting_study_result

    Returns dict mapping score type name to value (preserves provenance).
    """
    scores: dict[str, float] = {}
    for attr in _iter_nested_attributes(attributes):
        orig_name = attr.get("original_attribute_name", "")
        type_id = attr.get("attribute_type_id", "")
        value = attr.get("value")

        if orig_name == "tmkp_confidence_score" and value is not None:
            scores["tmkp_confidence_score"] = float(value)
        elif type_id == "biolink:extraction_confidence_score" and value is not None:
            scores["extraction_confidence_score"] = float(value)
        elif orig_name == "Combined_score" and value is not None:
            scores["Combined_score"] = float(value)
    return scores


def extract_rich_edge_attributes(attributes: list[dict]) -> dict:
    """Compose all extractors into a single call.

    Returns {"publications": [...], "supporting_text": [...], "confidence_scores": {...}}
    """
    return {
        "publications": extract_publications(attributes),
        "supporting_text": extract_supporting_text(attributes),
        "confidence_scores": extract_confidence_scores(attributes),
    }
