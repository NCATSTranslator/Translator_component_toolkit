import pytest
import TCT

# Some example queries for these tests.
EXAMPLE_QUERIES = [
    {
        'query': 'MESH:D003924',
        'curie': 'MONDO:0005148',
        'label': 'type 2 diabetes mellitus',
        'biolink_type': 'biolink:Disease',
        'drug_chemical_conflate': True,
        'conflate': True,
    },
    {
        'query': 'UMLS:C0004096',
        'curie': 'MONDO:0004979',
        'label_with_geneprotein_conflation': 'Asthma',
        'label': 'asthma',
        'biolink_type': 'biolink:Disease',
        'drug_chemical_conflate': True,
        'conflate': True,
    },
    {
        'query': 'UNII:S6002H6J9F',
        'curie': 'CHEBI:32635',
        'curie_without_conflation': 'CHEBI:32635',
        'label': 'paracetamol sulfate',
        'biolink_type': 'biolink:SmallMolecule',
        'drug_chemical_conflate': True,
        'conflate': True,
    },
    {
        'query': 'DRUGBANK:DB00083',
        'curie': 'UMLS:C0006050',
        'label': 'Dysport',
        'biolink_type': 'biolink:Protein',
        'drug_chemical_conflate': True,
        'conflate': True,
    },
    {
        'query': 'PR:P11532',
        'curie': 'UniProtKB:P11532',
        'label': 'DMD_HUMAN Dystrophin (sprot)',
        'label_with_geneprotein_conflation': 'DMD',
        'biolink_type': 'biolink:Protein',
        'drug_chemical_conflate': True,
        'conflate': False,
    },
    {
        'query': 'PR:P11532',
        'curie': 'NCBIGene:1756',
        'label': 'DMD',
        'biolink_type': 'biolink:Gene',
        'drug_chemical_conflate': True,
        'conflate': True,
    },
    {
        'query': 'CHEBI:33813',
        'curie': 'CHEBI:33813',
        'label': '((18)O)water',
        'biolink_type': 'biolink:SmallMolecule',
        'drug_chemical_conflate': False,
        'conflate': True,
    },
    {
        'query': 'CHEBI:33813',
        'curie': 'CHEBI:15377',
        'label': 'Water',
        'biolink_type': 'biolink:SmallMolecule',
        'drug_chemical_conflate': True,
        'conflate': True,
    }
]

def test_nodenorm_status():
    """
    Test that NodeNorm can return status information.
    """
    status = TCT.node_normalizer.status()

    assert status['status'] == 'running'
    assert status['babel_version'] != ''
    assert status['babel_version_url'] != ''
    assert status['databases']['eq_id_to_id_db']['count'] > 650_000_000


def test_nodenorm_invalid():
    """
    Test that NodeNorm can handle invalid queries.
    """
    assert TCT.node_normalizer.get_normalized_nodes('') is None
    assert TCT.node_normalizer.get_normalized_nodes('MONDO:0000000') is None
    assert TCT.node_normalizer.get_normalized_nodes(['', 'MONDO:0000000']) == {
        '': None,
        'MONDO:0000000': None,
    }


@pytest.mark.parametrize("example_normalization", EXAMPLE_QUERIES)
def test_nodenorm_normalization(example_normalization):
    """
    Test some NodeNorm normalization with expected results.
    """

    result = TCT.node_normalizer.get_normalized_nodes(example_normalization['query'], return_equivalent_identifiers=True, mode='post', conflate=example_normalization['conflate'], drug_chemical_conflate=example_normalization['drug_chemical_conflate'])
    assert result.curie == example_normalization['curie']
    assert result.label == example_normalization['label']
    assert result.types[0] == example_normalization['biolink_type']

def test_nodenorm_to_preferred_names():
    """
    Test that NodeNorm can return preferred names for normalized nodes.
    """

    queries = list(map(lambda example: example['query'], EXAMPLE_QUERIES))

    # Test ID_convert_to_preferred_name_nodeNormalizer: note that this always has GeneProtein conflation
    # turned on but DrugChemical conflation turned off.
    result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(queries)

    for curie in result:
        label = EXAMPLE_QUERIES[queries.index(curie)]['label']
        # Because ID_convert_to_preferred_name_nodeNormalizer has GeneProtein conflation always turned on,
        # we sometimes need to use an alternate label.
        if 'label_with_geneprotein_conflation' in EXAMPLE_QUERIES[queries.index(curie)]:
            label = EXAMPLE_QUERIES[queries.index(curie)]['label_with_geneprotein_conflation']
        assert result[curie].lower() == label.lower()

    result = TCT.node_normalizer.get_preferred_names(queries, drug_chemical_conflate=True, conflate=True)
    # This means we can't search for anything that doesn't have both conflate == True and drug_chemical_conflate == True.
    filtered_expected_results = list(filter(lambda example: example['conflate'] and example['drug_chemical_conflate'], EXAMPLE_QUERIES))
    assert len(result) == len(filtered_expected_results)
    for filtered_expected_result in filtered_expected_results:
        query = filtered_expected_result['query']
        assert result[query] == filtered_expected_result['label']


class TestIDConvertInline:
    """Tests ported from the removed if __name__ == '__main__' block in TCT.py."""

    def test_empty_list_returns_empty_dict(self):
        result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer([])
        assert result == {}

    def test_single_curie(self):
        result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(
            ['UBERON:0000201']
        )
        assert 'UBERON:0000201' in result
        assert isinstance(result['UBERON:0000201'], str)
        assert len(result['UBERON:0000201']) > 0

    def test_two_curies(self):
        result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(
            ['MESH:D005183', 'UBERON:0000201']
        )
        assert len(result) == 2
        assert 'MESH:D005183' in result
        assert 'UBERON:0000201' in result

    def test_two_chemical_curies(self):
        result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(
            ['CHEBI:45863', 'PUBCHEM.COMPOUND:31703']
        )
        assert len(result) == 2
        assert 'CHEBI:45863' in result
        assert 'PUBCHEM.COMPOUND:31703' in result

    def test_get_curie_brca1(self):
        result = TCT.get_curie('BRCA1')
        assert result == 'NCBIGene:672'
