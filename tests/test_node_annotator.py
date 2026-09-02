import TCT
import pytest

CURIES_with_annotations = [
    {
        'curie': 'MONDO:0005148',
        'expected': {
            'query': 'MONDO:0005148',
            'disease_ontology.name': 'type 2 diabetes mellitus',
            'sections': ['disease_ontology', 'mondo', 'umls'],
        },
    },
    {
        'curie': 'CHEBI:231601',
        'expected': {
            'query': 'CHEBI:231601',
            'sections': ['chebi'],
        },
    },
    {
        'curie': 'CHEBI:15377',
        'expected': {
            'query': 'CHEBI:15377',
            'boxed_warning': True,
            'sections': ['aeolus', 'chebi', 'chembl', 'clinical_approval', 'clinical_trials', 'drugbank', 'ndc', 'pubchem', 'unichem', 'unii'],
            'chembl.availability_type': 2,
        },
    },
    {
        'curie': 'NCIT:C34373',
        'expected': {},
    },
    {
        'curie': 'MONDO:0004976',
        'expected': {
            'query': 'MONDO:0004976',
            'disease_ontology.name': 'amyotrophic lateral sclerosis',
            'sections': ['disease_ontology', 'mondo', 'umls'],
        },
    },
    {
        'curie': 'NCBIGene:1756',
        'expected': {
            'query': '1756',
            'taxid': 9606,
            'name': 'dystrophin',
            'symbol': 'DMD',
            'type_of_gene': 'protein-coding',
            'sections': ['go', 'interpro'],
        },
    },
    {
        'curie': 'UniProtKB:P00395',
        'expected': {
            'query': 'P00395',
            'symbol': 'MT-CO1',
            'taxid': 9606,
            'type_of_gene': 'protein-coding',
            'sections': ['go', 'interpro'],
            'name': 'cytochrome c oxidase subunit I',
        },
    }
]

def compare_result_with_expected(result, expected_result):
    """
    Compares the actual result with the expected result across multiple fields and
    verifies whether the actual result meets the expected outcome. This comparison
    is based on key-value pairs within the provided dictionaries, and specific
    checks include top-level, subsection, and field-level verification.

    :param result: The actual result to compare, structured as a dictionary.
    :param expected_result: The expected result to validate against, structured
        as a dictionary containing various fields and their expected values.
    :return: None
    """

    # If there is no expected result, assert that the result is empty so we can fill in the test.
    if expected_result == {}:
        assert result == {}

    # Check sections.
    if 'sections' in expected_result:
        for section in expected_result['sections']:
            assert section in result

    # Check some top-level fields.
    if 'query' in expected_result:
        assert result['query'] == expected_result['query']

    if 'name' in expected_result:
        assert result['name'] == expected_result['name']

    if 'taxid' in expected_result:
        assert result['taxid'] == expected_result['taxid']

    if 'type_of_gene' in expected_result:
        assert result['type_of_gene'] == expected_result['type_of_gene']

    if 'boxed_warning' in expected_result:
        assert result['boxed_warning'] == expected_result['boxed_warning']

    # Check some subsection fields.
    if 'disease_ontology.name' in expected_result:
        assert result['disease_ontology']['name'] == expected_result['disease_ontology.name']

    if 'chembl.availability_type' in expected_result:
        assert result['chembl']['availability_type'] == expected_result['chembl.availability_type']


def test_status():
    """ Test that the status function returns a success message. """
    result = TCT.node_annotator.status()
    assert result['success']


def test_lookup_curies():
    curies = list(map(lambda x: x['curie'], CURIES_with_annotations))
    results = TCT.node_annotator.lookup_curies(curies)
    assert len(results) == len(curies)
    for curie in curies:
        assert curie in results
        if isinstance(results[curie], list):
            raise RuntimeError(f"Multiple results found for CURIE '{curie}': {results[curie]}")

        actual_result = results[curie]
        expected_result = list(filter(lambda x: x['curie'] == curie, CURIES_with_annotations))[0]['expected']

        compare_result_with_expected(actual_result, expected_result)


@pytest.mark.parametrize("curie_with_annotations", CURIES_with_annotations)
def test_lookup_curie(curie_with_annotations):
    curie = curie_with_annotations['curie']
    result = TCT.node_annotator.lookup_curie(curie)
    if result == {} and curie_with_annotations['expected'] == {}:
        # We expected no annotations and got no annotations.
        pytest.skip(f"No annotations found for CURIE '{curie}'")

    # Did we get more than one result?
    if isinstance(result, list):
        raise RuntimeError(f"Multiple results found for CURIE '{curie}': {result}")

    # Compare the result with the expected annotations.
    compare_result_with_expected(result, curie_with_annotations['expected'])
