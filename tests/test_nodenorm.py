import pytest
import TCT

# Some example queries for these tests.
EXAMPLE_QUERIES = [
    {
        "query": "MESH:D003924",
        "curie": "MONDO:0005148",
        "label": "type 2 diabetes mellitus",
        "biolink_type": "biolink:Disease",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
    {
        "query": "UMLS:C0004096",
        "curie": "MONDO:0004979",
        "label_with_geneprotein_conflation": "Asthma",
        "label": "asthma",
        "biolink_type": "biolink:Disease",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
    {
        "query": "UNII:S6002H6J9F",
        "curie": "CHEBI:32635",
        "curie_without_conflation": "CHEBI:32635",
        "label": "paracetamol sulfate",
        "biolink_type": "biolink:SmallMolecule",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
    {
        "query": "DRUGBANK:DB00083",
        "curie": "UMLS:C0006050",
        "label_with_geneprotein_conflation": "Botulinum toxin type A",
        "label": "Dysport",
        "biolink_type": "biolink:Protein",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
    {
        "query": "PR:P11532",
        "curie": "UniProtKB:P11532",
        "label": "DMD_HUMAN Dystrophin (sprot)",
        "label_with_geneprotein_conflation": "DMD",
        "biolink_type": "biolink:Protein",
        "drug_chemical_conflate": True,
        "conflate": False,
    },
    {
        "query": "PR:P11532",
        "curie": "NCBIGene:1756",
        "label": "DMD",
        "biolink_type": "biolink:Gene",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
    {
        "query": "CHEBI:33813",
        "curie": "CHEBI:33813",
        "label": "((18)O)water",
        "biolink_type": "biolink:SmallMolecule",
        "drug_chemical_conflate": False,
        "conflate": True,
    },
    {
        "query": "CHEBI:33813",
        "curie": "CHEBI:15377",
        "label": "Water",
        "biolink_type": "biolink:SmallMolecule",
        "drug_chemical_conflate": True,
        "conflate": True,
    },
]


def test_nodenorm_status():
    """
    Test that NodeNorm can return status information.
    """
    status = TCT.node_normalizer.status()

    assert status["status"] == "running"
    assert isinstance(status, dict)
    assert status != {}


def test_nodenorm_invalid():
    """
    Test that NodeNorm can handle invalid queries.
    """
    assert TCT.node_normalizer.get_normalized_nodes("") is None
    assert TCT.node_normalizer.get_normalized_nodes("MONDO:0000000") is None
    assert TCT.node_normalizer.get_normalized_nodes(["", "MONDO:0000000"]) == {
        "": None,
        "MONDO:0000000": None,
    }


@pytest.mark.parametrize("example_normalization", EXAMPLE_QUERIES)
def test_nodenorm_normalization(example_normalization):
    """
    Test some NodeNorm normalization with expected results.
    """

    result = TCT.node_normalizer.get_normalized_nodes(
        example_normalization["query"],
        return_equivalent_identifiers=True,
        mode="post",
        conflate=example_normalization["conflate"],
        drug_chemical_conflate=example_normalization["drug_chemical_conflate"],
    )
    assert result is not None
    assert result.curie != ""
    assert result.label is not None
    assert result.types != []
    assert all(node_type.startswith("biolink:") for node_type in result.types)


def test_nodenorm_to_preferred_names():
    """
    Test that NodeNorm can return preferred names for normalized nodes.
    """

    queries = list(map(lambda example: example["query"], EXAMPLE_QUERIES))

    # Test ID_convert_to_preferred_name_nodeNormalizer: note that this always has GeneProtein conflation
    # turned on but DrugChemical conflation turned off.
    result = TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(queries)

    for curie in result:
        label = EXAMPLE_QUERIES[queries.index(curie)]["label"]
        # Because ID_convert_to_preferred_name_nodeNormalizer has GeneProtein conflation always turned on,
        # we sometimes need to use an alternate label.
        if "label_with_geneprotein_conflation" in EXAMPLE_QUERIES[queries.index(curie)]:
            label = EXAMPLE_QUERIES[queries.index(curie)][
                "label_with_geneprotein_conflation"
            ]
        assert result[curie] == label

    result = TCT.node_normalizer.get_preferred_names(
        queries, drug_chemical_conflate=True, conflate=True
    )
    # This means we can't search for anything that doesn't have both conflate == True and drug_chemical_conflate == True.
    filtered_expected_results = list(
        filter(
            lambda example: example["conflate"] and example["drug_chemical_conflate"],
            EXAMPLE_QUERIES,
        )
    )
    assert len(result) == len(filtered_expected_results)
    for filtered_expected_result in filtered_expected_results:
        query = filtered_expected_result["query"]
        assert isinstance(result[query], str)
        assert result[query] != ""
