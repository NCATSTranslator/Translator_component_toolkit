"""Shared fixtures for all TCT test files."""

import pytest
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd


@pytest.fixture(autouse=True, scope="session")
def _set_matplotlib_backend():
    """Use non-interactive Agg backend so plotting works in CI without a display."""
    matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def plt_close_after():
    """Close all matplotlib figures after each test to prevent memory leaks."""
    yield
    plt.close("all")


@pytest.fixture()
def sample_kg_result():
    """A minimal TRAPI knowledge_graph dict with 3+ edges, mixed directions,
    sources with primary_knowledge_source/aggregator_knowledge_source roles,
    covering both new-key and existing-key branches in parse_KG()."""
    return {
        "edge1": {
            "subject": "NCBIGene:3845",
            "object": "CHEBI:15377",
            "predicate": "biolink:interacts_with",
            "sources": [
                {"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"},
                {"resource_id": "infores:agg1", "resource_role": "aggregator_knowledge_source"},
            ],
            "attributes": [],
        },
        "edge2": {
            "subject": "NCBIGene:3845",
            "object": "CHEBI:15377",
            "predicate": "biolink:related_to",
            "sources": [
                {"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"},
            ],
            "attributes": [],
        },
        "edge3": {
            "subject": "CHEBI:15377",
            "object": "NCBIGene:3845",
            "predicate": "biolink:affects",
            "sources": [
                {"resource_id": "infores:kp3", "resource_role": "primary_knowledge_source"},
                {"resource_id": "infores:agg2", "resource_role": "aggregator_knowledge_source"},
            ],
            "attributes": [],
        },
        "edge4": {
            "subject": "NCBIGene:3845",
            "object": "MONDO:0005148",
            "predicate": "biolink:gene_associated_with_condition",
            "sources": [
                {"resource_id": "infores:kp4", "resource_role": "primary_knowledge_source"},
            ],
            "attributes": [],
        },
    }


@pytest.fixture()
def sample_metakg():
    """A small MetaKG DataFrame for testing selection/filtering functions."""
    return pd.DataFrame({
        "API": ["API_A", "API_A", "API_B", "API_B", "API_C"],
        "Predicate": [
            "biolink:interacts_with",
            "biolink:related_to",
            "biolink:interacts_with",
            "biolink:treats",
            "biolink:affects",
        ],
        "Subject": [
            "biolink:Gene",
            "biolink:Gene",
            "biolink:SmallMolecule",
            "biolink:SmallMolecule",
            "biolink:Disease",
        ],
        "Object": [
            "biolink:SmallMolecule",
            "biolink:Disease",
            "biolink:Gene",
            "biolink:Disease",
            "biolink:Gene",
        ],
        "URL": [
            "https://api-a.example.com/query",
            "https://api-a.example.com/query",
            "https://api-b.example.com/query",
            "https://api-b.example.com/query",
            "https://api-c.example.com/query",
        ],
    })


@pytest.fixture()
def sample_apinames():
    """Dict mapping API names to URLs, consistent with sample_metakg."""
    return {
        "API_A": "https://api-a.example.com/query",
        "API_B": "https://api-b.example.com/query",
        "API_C": "https://api-c.example.com/query",
    }


@pytest.fixture()
def sample_api_predicates():
    """Dict mapping API names to predicate lists."""
    return {
        "API_A": ["biolink:interacts_with", "biolink:related_to"],
        "API_B": ["biolink:interacts_with", "biolink:treats"],
        "API_C": ["biolink:affects"],
    }


@pytest.fixture()
def sample_resources(sample_apinames, sample_metakg, sample_api_predicates):
    """A TranslatorResources instance built from the sample fixtures."""
    from TCT.translator_resources import TranslatorResources
    return TranslatorResources(api_names=sample_apinames, meta_kg=sample_metakg, api_predicates=sample_api_predicates)
