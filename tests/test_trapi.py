"""Tests for TCT.trapi module, focused on the predicate_query branch changes:
- build_query defaults to returning a dict (return_json=False)
- query() accepts a dict instead of a JSON string
"""

import json
import inspect

import pytest

from TCT.trapi import build_query, query


# Test data
EXAMPLE_QUERIES = [
    {
        'subject_ids': ['NCBIGene:3845'],
        'object_categories': ['biolink:Gene'],
        'predicates': ['biolink:physically_interacts_with'],
    },
    {
        'subject_ids': ['NCBIGene:3845'],
        'object_categories': ['biolink:Gene'],
        'predicates': [
            'biolink:positively_correlated_with',
            'biolink:physically_interacts_with',
        ],
    },
]


def test_build_query_returns_dict_by_default():
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'])
    assert isinstance(result, dict)


def test_build_query_default_is_explicitly_false():
    sig = inspect.signature(build_query)
    assert sig.parameters['return_json'].default is False


def test_build_query_returns_json_string_when_requested():
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=True)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_build_query_dict_and_json_are_equivalent():
    q = EXAMPLE_QUERIES[0]
    dict_result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=False)
    json_result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=True)
    assert dict_result == json.loads(json_result)


@pytest.mark.parametrize("example_query", EXAMPLE_QUERIES)
def test_build_query_structure(example_query):
    result = build_query(
        example_query['subject_ids'],
        example_query['object_categories'],
        example_query['predicates'],
    )
    assert 'message' in result
    qg = result['message']['query_graph']
    assert qg['edges']['e00']['predicates'] == example_query['predicates']
    assert qg['edges']['e00']['subject'] == 'n00'
    assert qg['edges']['e00']['object'] == 'n01'
    assert qg['nodes']['n00']['ids'] == example_query['subject_ids']
    assert qg['nodes']['n01']['categories'] == example_query['object_categories']


def test_query_signature_expects_dict():
    sig = inspect.signature(query)
    assert sig.parameters['query'].annotation is dict


def test_build_query_output_matches_query_input_type():
    """build_query's default output type should match what query() expects."""
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'])
    sig = inspect.signature(query)
    assert isinstance(result, sig.parameters['query'].annotation)
