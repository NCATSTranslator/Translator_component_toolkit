"""
This is a wrapper around the Name Resolver API.

API docs: https://name-lookup.ci.transltr.io/docs
"""
# reviewed by yjzhang, 2026-08-19
import urllib.parse

import requests

from .translator_node import TranslatorNode

URL = 'https://name-lookup.ci.transltr.io/'
"""This is the root URL for the API."""

def status() -> str:
    """
    Returns the status of the Name Resolver API.
    """
    response = requests.get(URL + 'status')
    response.raise_for_status()
    return response.json()


def lookup(query: str, return_top_response:bool=True, return_synonyms:bool=False,  limit:int=10, **kwargs) -> TranslatorNode | list[TranslatorNode]:
    """
    A wrapper around the `lookup` api endpoint. Given a query string, this returns a TranslatorNode object or a list of TranslatorNode objects corresponding to the given name.

    Parameters
    ----------
    query : str
        Query string
    return_top_response : bool
        If true, this returns only the top response. If false, this returns a list of all responses. Default: True
    return_synonyms : bool
        If true, the resulting TranslatorNode objects contain a list of synonyms. If false, they do not include synonyms. Default: False
    only_taxa : str
        The taxonomic restriction for the query. Default: 'NCBITaxon:9606'
    limit : int
        The number of results to return.
    **kwargs
        Other arguments to `lookup`. Some possible arguments: 
        `limit=20` would limit the results to 20. 
        `autocomplete=True` indicates that the query string can be incomplete. 
        `biolink_type="biolink:Disease"` indicates that all returned results should be diseases. 
        `only_taxa='NCBITaxon:9606` indicates that only Homo sapiens results should be returned.
        For more examples, see [this](https://name-lookup.ci.transltr.io/docs#/lookup/lookup_curies_get_lookup_get).

    Returns
    -------
    TranslatorNode object if return_top_response is True, list of TranslatorNode objects if return_top_response is False

    Examples
    --------
    >>> lookup('AML')
    TranslatorNode(curie='MONDO:0018874', label='acute myeloid leukemia', types=['biolink:Disease', 'biolink:DiseaseOrPhenotypicFeature', 'biolink:BiologicalEntity', 'biolink:ThingWithTaxon', 'biolink:NamedThing', 'biolink:Entity'], synonyms=None, curie_synonyms=None)
    >>> lookup('IFNG', only_taxa='NCBITaxon:9606') # It provides the human gene for IFNG
    TranslatorNode(curie='NCBIGene:3458', label='IFNG', types=['biolink:Gene', 'biolink:GeneOrGeneProduct', 'biolink:GenomicEntity', 'biolink:ChemicalEntityOrGeneOrGeneProduct', 'biolink:PhysicalEssence', 'biolink:OntologyClass', 'biolink:BiologicalEntity', 'biolink:ThingWithTaxon', 'biolink:NamedThing', 'biolink:Entity', 'biolink:PhysicalEssenceOrOccurrent', 'biolink:MacromolecularMachineMixin', 'biolink:Protein', 'biolink:GeneProductMixin', 'biolink:Polypeptide', 'biolink:ChemicalEntityOrProteinOrPolypeptide'], synonyms=None, curie_synonyms=None, attributes=None, taxa=['NCBITaxon:9606'])
    >>> lookup('AML', return_top_response=False, biolink_type="biolink:Disease")
    """
    path = urllib.parse.urljoin(URL, 'lookup')
    # set autocomplete to be false by default
    if 'autocomplete' not in kwargs:
        kwargs['autocomplete'] = False
    response = requests.get(path, params={'string': query, 'limit': limit, **kwargs})
    if response.status_code == 200:
        result = response.json()
        if len(result) == 0:
            raise LookupError('No matching CURIE found for the given string ' + query)
        else:
            if return_top_response:
                return TranslatorNode.from_dict(result[0], return_synonyms)
            else:
                all_nodes = []
                for node in result:
                    n = TranslatorNode.from_dict(node, return_synonyms)
                    all_nodes.append(n)
                return all_nodes
    else:
        raise requests.RequestException('Response from server had error, code ' + str(response.status_code) + ' ' + str(response))


def synonyms(query: str|list, **kwargs) -> dict[str, TranslatorNode]:
    """
    A wrapper around the `synonyms` api endpoint. Given a CURIE or a list of CURIEs, this returns a dict of CURIE id : TranslatorNode for all synonyms for the given query.

    Parameters
    ----------
    query : str|list
        Query CURIE or list of CURIEs
    **kwargs
        Other arguments to `synonyms`

    Returns
    -------
    Dict of CURIE id : TranslatorNode
    """
    path = urllib.parse.urljoin(URL, 'synonyms')
    # set autocomplete to be false by default
    response = requests.get(path, params={'preferred_curies': query, **kwargs})
    if response.status_code == 200:
        result = response.json()
        if len(result) == 0:
            raise LookupError('No matching CURIE found for the given string ' + str(query))
        else:
            all_nodes = {}
            for k, node in result.items():
                if not node:
                    # If node is empty or None.
                    all_nodes[k] = None
                else:
                    all_nodes[k] = TranslatorNode.from_dict(node, return_synonyms=True)
            return all_nodes
    else:
        raise requests.RequestException('Response from server had error, code ' + str(response.status_code) + ' ' + str(response))


def chunk_list(data:list, size:int) -> list:
    #Extra method to help chunk large files and avoid 504 error.
    chunks = []
    for i in range(0, len(data), size):
        chunks.append(data[i: i+size])
    return chunks


def batch_lookup(strings:list[str], size: int=25, return_top_response:bool=True, return_synonyms:bool=False, **kwargs) -> dict[str, TranslatorNode|list[TranslatorNode]]:
    """
    A wrapper around the `bulk-lookup` api endpoint. Given a list of query strings, this returns a TranslatorNode object or a list of TranslatorNode objects corresponding to the given name.

    Parameters
    ----------
    strings : list[str]
        List of query strings.
    size : int
        Desired chunking size, default is 25.
    return_top_response : bool
        If true, this returns only the top response per string. If false, this returns a list of all responses per string. Default: True
    return_synonyms : bool
        If true, the resulting TranslatorNode objects contain a list of synonyms. If false, they do not include synonyms. Default: False
    **kwargs
        Other arguments to `bulk-lookup`.  Some possible arguments: `autocomplete=True` indicates that the query string can be incomplete. `biolink_types=["biolink:Disease", "biolink:Gene"]` indicates that all returned results should be diseases or genes. `only_taxa='NCBITaxon:9606` indicates that only Homo sapiens results should be returned.

    Returns
    -------
    Dict of string : TranslatorNode object if return_top_response is True, list of TranslatorNode objects if return_top_response is False

    Examples
    --------
    >>> batch_lookup(['AML', 'CML'])
    {'AML': TranslatorNode(curie='MONDO:0018874', label='acute myeloid leukemia',...),
     'CML': TranslatorNode(curie='MONDO:0010809', label='familial chronic myelocytic leukemia-like syndrome',...)}
    """
    path = urllib.parse.urljoin(URL, 'bulk-lookup')
    curies = {}
    chunks = chunk_list(strings, size)
    for chunk in chunks:
        payload = {
            "strings": chunk,
            **kwargs
        }
        response = requests.post(path, json = payload)
        if response.status_code == 200:
            result = response.json()
            if(len(result) == 0):
                raise LookupError('No matching CURIE found for the given strings ' + str(strings))
            else:
                for s in chunk:
                    nodes = result.get(s, [])
                    translator_nodes = []
                    for node in nodes:
                        n = TranslatorNode.from_dict(node, return_synonyms)
                        translator_nodes.append(n)
                    if return_top_response:
                        if translator_nodes:
                            curies[s] = translator_nodes[0]
                        else:
                            curies[s] = None
                    else:
                        curies[s] = translator_nodes
        else:
            raise requests.RequestException('Response from server had error, code ' + str(response.status_code) + ' ' + str(response))
    return curies


def batch_synonyms(strings:list[str], size:int=50, **kwargs) -> dict[str, TranslatorNode]:
    """
    A wrapper around the `synonyms` API endpoint, using POST. Given a list of CURIEs, this returns a dict of CURIE:TranslatorNode, where each TranslatorNode contains all synonyms for the given CURIE.

    Parameters
    ----------
    strings : list[str]
        List of CURIEs.
    size : int
        Desired chunking size, default is 50.

    Returns
    -------
    Dict of CURIE : TranslatorNode
    """
    chunks = chunk_list(strings, size)
    path = urllib.parse.urljoin(URL, 'synonyms')
    curies = {}
    for chunk in chunks:
        # set autocomplete to be false by default
        response = requests.post(path, json={'preferred_curies': chunk, **kwargs})
        if response.status_code == 200:
            result = response.json()
            if len(result) == 0:
                raise LookupError('No matching CURIE found for the given CURIEs ' + str(chunks))
            else:
                for k, node in result.items():
                    if not node:
                        # If node is empty or None.
                        curies[k] = None
                    else:
                        curies[k] = TranslatorNode.from_dict(node, return_synonyms=True)
        else:
            raise requests.RequestException('Response from server had error, code ' + str(response.status_code) + ' ' + str(response))
    return curies


