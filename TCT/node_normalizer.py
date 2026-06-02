"""
This is a wrapper around the Node Normalizer API.

API docs: https://nodenorm.transltr.io/docs
"""
import urllib.parse

import requests

from .translator_node import TranslatorNode


URL = 'https://nodenorm.ci.transltr.io/'

def status():
    """
    Returns the status of the Node Normalizer API.
    """
    response = requests.get(f'{URL}status')
    response.raise_for_status()
    return response.json()

def get_normalized_nodes(query: str | list[str],
        return_equivalent_identifiers:bool=False,
        mode:str='get',
        **kwargs) -> dict[str, TranslatorNode]|TranslatorNode:
    """
    A wrapper around the `get_normalized_nodes` api endpoint. Given a CURIE or a list of CURIEs, this returns either a single TranslatorNode or a dict of CURIE ids to TranslatorNodes.

    Parameters
    ----------
    query : str
        Query CURIE
    return_equivalent_identifiers : bool
        Whether or not to return a list of equivalent identifiers along with the TranslatorNode. Default: False
    mode: str
        'get' or 'post'. Default: 'get'
    **kwargs
        Other arguments to `get_normalized_nodes` (e.g. `conflate` for gene-protein conflation, `drug_chemical_conflate` for drug-chemical conflation - see https://nodenorm.transltr.io/docs#/default/get_normalized_node_handler_get_normalized_nodes_get)

    Returns
    -------
    If query is a single CURIE, returns a single TranslatorNode.

    If query is a list of CURIEs, a dict of CURIE id to TranslatorNode for every node in the query.

    Examples
    --------
    >>> get_normalized_nodes('MESH:D014867', return_equivalent_identifiers=False)
    TranslatorNode(curie='CHEBI:15377', label='Water', types=['biolink:SmallMolecule', 'biolink:MolecularEntity', 'biolink:ChemicalEntity', 'biolink:PhysicalEssence', 'biolink:ChemicalOrDrugOrTreatment', 'biolink:ChemicalEntityOrGeneOrGeneProduct', 'biolink:ChemicalEntityOrProteinOrPolypeptide', 'biolink:NamedThing', 'biolink:PhysicalEssenceOrOccurrent'], synonyms=None, curie_synonyms=None)
    """
    # default parameters: true for gene-protein conflation, false for drug-chemical conflation
    path = urllib.parse.urljoin(URL, 'get_normalized_nodes')
    # TODO: batch the query?
    if mode == 'post':
        if isinstance(query, str):
            # CURIEs sent to POST must be a list. If a single CURIE is given, we wrap it.
            json_query = [query]
        else:
            json_query = query
        if len(json_query) == 0:
            return {}
        response = requests.post(path, json={'curies': json_query, **kwargs})
    else:
        response = requests.get(path, params={'curie': query, **kwargs})
    if response.status_code == 200:
        result = response.json()
        normalized_dict = {}
        for k, node in result.items():
            if node is None:
                # No match found for CURIE `k`.
                normalized_dict[k] = None
                continue

            n = TranslatorNode(node['id']['identifier'])
            if 'label' in node['id']:
                n.label = node['id']['label']
            if 'type' in node:
                n.types = node['type']
            if return_equivalent_identifiers and 'equivalent_identifiers' in node:
                synonyms = []
                curie_synonyms = []
                for eq in node['equivalent_identifiers']:
                    if 'label' in eq:
                        synonyms.append(eq['label'])
                    else:
                        synonyms.append(None)
                    curie_synonyms.append(eq['identifier'])
                n.synonyms = synonyms
                n.curie_synonyms = curie_synonyms
            normalized_dict[k] = n
        if isinstance(query, str):
            return normalized_dict[query]
        return normalized_dict
    else:
        raise requests.RequestException('Response from server had error, code ' + str(response.status_code))


def get_preferred_names(id_list:list[str], batch_limit=500, **kwargs) -> dict[str, str]:
    """
    Converts a list of CURIEs to their preferred names using NodeNorm. This calls get_normalized_nodes.

    Parameters
    ----------
    query : list
        Query CURIE
    batch_limit: int
        Limit for how many IDs to use in one query. Default: 500
    **kwargs
        Other arguments to `get_normalized_nodes` (e.g. `conflate` for gene-protein conflation, `drug_chemical_conflate` for drug-chemical conflation - see https://nodenorm.transltr.io/docs#/default/get_normalized_node_handler_get_normalized_nodes_get)

    Returns
    -------
    Returns a dict mapping CURIE ids to preferred names.
    """
    name_map = {}
    unmapped_ids = []
    for index in range(0, len(id_list), batch_limit):
        id_sublist = id_list[index:index + batch_limit]
        normalized_nodes = get_normalized_nodes(id_sublist, mode='post', **kwargs)
        if isinstance(normalized_nodes, TranslatorNode):
            normalized_nodes = {normalized_nodes.curie: normalized_nodes}
        for curie in id_sublist:
            if curie not in normalized_nodes or normalized_nodes[curie] is None:
                unmapped_ids.append(curie)
                name_map[curie] = curie
            else:
                label = normalized_nodes[curie].label
                if label is None:
                    print(curie + ": no preferred name")
                    label = curie
                name_map[curie] = label
    if len(unmapped_ids) > 0:
        print("NodeNorm does not know about these identifiers: " + ",".join(unmapped_ids))
    return name_map


def ID_convert_to_preferred_name_nodeNormalizer(id_list):
    '''
    Convert a list of CURIEs to their preferred names using NodeNorm.
    Arg:
        id_list: list of CURIEs to be converted
    Returns:
        dic_id_map: dictionary mapping CURIEs to their preferred names
    Example:
        dic_id_map = ID_convert_to_preferred_name_nodeNormalizer(["NCBIGene:1234", "NCBIGene:5678"])
    '''
    dic_id_map = {}
    unrecoglized_ids = []
    recoglized_ids = []
    # To convert a CURIE to a preferred name, you don't need NameLookup at all -- NodeNorm can
    # do this by itself!
    NODENORM_BASE_URL = "https://nodenorm.transltr.io"  # Adjust this if you need NodeNorm TEST, CI or DEV.
    NODENORM_BATCH_LIMIT = 900                          # Adjust this if you start getting errors from NodeNorm.
    NODENORM_GENE_PROTEIN_CONFLATION = True             # Change to False if you don't want gene/protein conflation.
    NODENORM_DRUG_CHEMICAL_CONFLATION = False           # Change to True if you want drug/chemical conflation.

    # split id_list into batches of at most NODENORM_BATCH_LIMIT entries
    for index in range(0, len(id_list), NODENORM_BATCH_LIMIT):
        id_sublist = id_list[index:index + NODENORM_BATCH_LIMIT]

        # print(f"id_sublist: {id_sublist}")

        # Query NodeNorm with https://nodenorm.transltr.io/docs#/default/get_normalized_node_handler_get_normalized_nodes_get
        response = requests.post(NODENORM_BASE_URL + '/get_normalized_nodes', json={
            "curies": id_sublist,
            "description": False,   # Change to True if you want descriptions from any identifiers we know about.
            "conflate": NODENORM_GENE_PROTEIN_CONFLATION,
            "drug_chemical_conflate": NODENORM_DRUG_CHEMICAL_CONFLATION,
        })
        if not response.ok:
            raise RuntimeError("Error: NodeNorm request failed with status code " + str(response.status_code))

        results = response.json()
        for curie in id_sublist:
            if curie in results and results[curie]:
                identifier = results[curie].get('id', {})
                if 'identifier' in identifier and identifier['identifier'] != curie:
                    recoglized_ids.append(curie)
                    #print(f"NodeNorm normalized {curie} to {identifier['identifier']} " +
                    #      f"with gene-protein conflation {NODENORM_GENE_PROTEIN_CONFLATION} and " +
                    #      f"with drug-chemical conflation {NODENORM_DRUG_CHEMICAL_CONFLATION}.")
                label = identifier.get('label')
                dic_id_map[curie] = label
                if not label:
                    print(curie + ": no preferred name")
                    dic_id_map[curie] = curie
            else:
                unrecoglized_ids.append(curie)

                dic_id_map[curie] = curie
    if len(unrecoglized_ids) > 0:
        print("NodeNorm does not know about these identifiers: " + ",".join(unrecoglized_ids))

    return dic_id_map
