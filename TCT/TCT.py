import requests
import json
from dataclasses import dataclass as _dataclass
import pandas as pd
import  seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import openai
from . import name_resolver

# plt.switch_backend('module://ipykernel.pylab.backend_inline')

from .visualization import (
    HeatmapConfig as HeatmapConfig,
    plot_heatmap as plot_heatmap,
    plot_heatmap_ui as plot_heatmap_ui,
    plot_path_bar as plot_path_bar,
    visulization_one_hop_ranking as visulization_one_hop_ranking,
    visulization_one_hop_ranking_input_as_list as visulization_one_hop_ranking_input_as_list,
    plot_graph_by_predicates as plot_graph_by_predicates,
    plot_graph_by_infores as plot_graph_by_infores,
    plot_graph_by_API as plot_graph_by_API,
    visulize_path as visulize_path,
)

__all__ = [
    'TCT_help',
    'list_functions',
    'get_Translator_APIs',
    'get_SmartAPI_Translator_KP_info',
    'list_Translator_APIs',
    'load_translator_resources',
    'Neiborhood_finder',
    'Path_finder',
    'format_query_json',
    'select_API',
    'select_concept',
    'sele_predicates_API',
    'parse_KG',
    'rank_by_primary_infores',
    'rank_by_primary_infores_input_as_list',
    'ID_convert_to_preferred_name_nodeNormalizer',
    'visulization_one_hop_ranking',
    'visulization_one_hop_ranking_input_as_list',
    'plot_heatmap',
    'plot_heatmap_ui',
    'plot_graph_by_predicates',
    'plot_graph_by_infores',
    'plot_graph_by_API',
    'visulize_path',
    'get_curie',
    'merge_ranking_by_number_of_infores',
    'merge_by_ranking_index',
    'get_pair_annotation',
    'parse_pair_annotation',
    'ask_chatGPT',
    'ask_chatGPT4',
    'query_chatGPT',
    'query_chatGPT4',
    'load_json_template',
    'extract_json',
    'TRAPI_json_validation',
    'HeatmapConfig',
    'ChatGPTConfig',
    'format_id',
    'get_Translator_API_URL',
    'get_similar_category',
    'get_similar_predicate',
]


def _resolve_resources(resources, *, APInames=None, metaKG=None, API_predicates=None):
    """Resolve legacy (APInames, metaKG, API_predicates) kwargs into a TranslatorResources."""
    from .translator_resources import TranslatorResources

    if resources is not None and isinstance(resources, TranslatorResources):
        return resources
    if APInames is not None:
        import warnings

        warnings.warn(
            "Passing APInames/metaKG/API_predicates as separate arguments is deprecated. "
            "Use resources=TranslatorResources(...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return TranslatorResources(
            api_names=APInames,
            meta_kg=metaKG,
            api_predicates=API_predicates or {},
        )
    if resources is not None:
        raise TypeError(
            "Expected TranslatorResources for 'resources' parameter. "
            "Use keyword arguments: APInames=..., metaKG=..., API_predicates=..."
        )
    raise TypeError(
        "Either 'resources' or 'APInames'+'metaKG'+'API_predicates' must be provided."
    )


def TCT_help(func):
    print(func.__doc__)

# list all functions in TCT
def list_functions():
    import inspect
    functions = []
    for name, obj in inspect.getmembers(__import__(__name__)):
        if inspect.isfunction(obj):
            functions.append(name)
    return functions

# used. Jan 5, 2024
def get_Translator_APIs():
    '''
    Get a list of Translator APIs from the smart-api.info and return the detailed information for each API in a data frame and the list of API names.

    Examples
    --------
    >>> Translator_KP_info,APInames= TCT.get_SmartAPI_Translator_KP_info()
    '''
    Translator_APIs = []
    #Translator_apps_url = "https://smart-api.info/api/query?q=tags.name:translator&fields=info,_meta,tags&meta=1&size=500"
    Translator_apps_url = "https://dev.smart-api.info/api/query?q=tags.name:translator&fields=info,_meta,tags&meta=1&size=500"
    Translator_apps = requests.get(Translator_apps_url).json()['hits']
    for app in Translator_apps:
        Translator_APIs.append(app['info']['title'])
    return Translator_APIs

# used May 30, 2025
# used May 30, 2025
"""This is the root URL for the resource."""
URL = 'https://smart-api.info/api/query?q=tags.name:translator'

def get_SmartAPI_Translator_KP_info():
    """
    Get the SmartAPI Translator KP info from the smart-api.info API.
    Returns a DataFrame with the SmartAPI Translator KP info.

    Examples
    --------
    >>> Translator_KP_info,APInames = get_SmartAPI_Translator_KP_info()
    """
    from . import translator_kpinfo
    return translator_kpinfo.get_translator_kp_info()

# used Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def list_Translator_APIs():
    APInames = {
            'Sri-name-resolver':'https://name-lookup.ci.transltr.io/query/', #https://smart-api.info/ui/9995fed757acd034ef099dbb483c4c82
            #'Monarch API':'https://api-v3.monarchinitiative.org/query/' #https://smart-api.info/ui/d22b657426375a5295e7da8a303b9893
            #Complex Portal Web Service : #https://smart-api.info/ui/326eb1e437303bee27d3cef29227125d
            'Sri-answer-appraiser(Trapi v1.5.0)':'https://answerappraiser.renci.org/get_appraisal/', #https://smart-api.info/ui/6dcc5454fe4e0095090d8a956781c438
            #LitVar API : dca415f2d792976af9d642b7e73f7a41
            #CTD API : 0212611d1c670f9107baf00b77f0889a
            #EBI Proteins API : 43af91b3d7cae43591083bff9d75c6dd
            #Ontology Lookup Service API : 1c056ffc7ed0dd1229e71c4752239465
            'Cqs(Trapi v1.5.0)':'https://cqs-dev.apps.renci.org/query/', #https://smart-api.info/ui/c359a127dc8824d90cef436d3dce71d4
            'Workflow-runner(Trapi v1.5.0)':'https://translator-workflow-runner.renci.org/query/', #https://smart-api.info/ui/6a3507ad6f709844d1b2b89691898a93
            'Automat-monarchinitiative(Trapi v1.5.0)':'https://automat.ci.transltr.io/monarch-kg/query/',#https://smart-api.info/ui/6b88f83127513bd350e6962218ea84f4
            #QuickGO API : 1f277e1563fcfd124bfae2cc3c4bcdec
            #RaMP API v1.0.1 : ac9c2ad11c5c442a1a1271223468ced1 # need to check carefully.
            'Connections Hypothesis Provider API':'https://chp-api.transltr.io/query/', #https://smart-api.info/ui/412af63e15b73e5a30778aac84ce313f
            'Automat-genome-alliance(Trapi v1.5.0)' :'https://automat.ci.transltr.io/genome-alliance/query/', #https://smart-api.info/ui/b4c868db33b95b4890faeeefd5800552
            'mediKanren' : 'https://medikanren-trapi.transltr.io/query/', #https://smart-api.info/ui/c563a58be4aacb68d10ba0ceb6b52255
            'Automat-hgnc(Trapi v1.5.0)':'https://automat.transltr.io/hgnc/query/', #'https://smart-api.info/ui/8671309d2b94e413a4c1f9a9f82e4660'
            'Automat-hmdb(Trapi v1.5.0)':'https://automat.transltr.io/hmdb/query/' ,# 0a1c0f46f4950b82b1aa7dad27aad10a
            'Automat-gwas-catalog(Trapi v1.5.0)' :'https://automat.transltr.io/gwas-catalog/query/', #349fed5531c094c33f10c071efe9d0de
            'Automat-gtopdb(Trapi v1.5.0)': 'https://automat.transltr.io/gtopdb/query/',# 759df287a21c30cd514df323be02a84b
            'Autonomous Relay System (ARS) TRAPI' : 'https://ars-prod.transltr.io/ars/api/submit/', #4c12efd48ced755ac4b72b1922202ec2
            'Automat-robokop(Trapi v1.5.0)' : 'https://automat.transltr.io/robokopkg/query/',# 4f9c8853b721ef1f14ecee6d92fc19b5
            'Automat-binding-db(Trapi v1.5.0)': 'https://automat.transltr.io/binding-db/query/', #a9d6ee341d8ea4c7d3ae9ed0941cb274
            'Automat-ehr-may-treat-kp(Trapi v1.5.0)' : 'https://automat.renci.org/ehr-may-treat-kp/query/',#eb4e66886fe5c178ae41977cea2c6307
            #Automat-gtex(Trapi v1.5.0) : eef72049e4e01c020b7799f711e0e65b,
            #Automat-pharos(Trapi v1.5.0) : 1f057c53d42694686369f0e542f965c6
            #Automat-reactome(Trapi v1.5.0) : 61b41c5d9b90eb8ad16e037f9a87d593
            #Sri-node-normalizer(Trapi v1.5.0) : 1c2eb8d02b4796c6a657c3363c0657dc
            #Automat-human-goa(Trapi v1.5.0) : cb7a43d444cb3dcbe8e3c78d314334cf
            #Automat-cam-kp(Trapi v1.5.0) : 7ab0209ea8590341d8e5d0166cac3d2f
            #Automat-viral-proteome(Trapi v1.5.0) : 2aca41fc6c3dc426ec6583d42603be02
            #Aragorn(Trapi v1.5.0) : 1dad992a6ce8f680e59a5ea09d90670d
            #Automat-drug-central(Trapi v1.5.0) : 673b9fc76973dfa5fe3ed151fdbfc807
            #Automat-ubergraph(Trapi v1.5.0) : dde0552a37fc136526216148ff7594a0
            #Automat-string-db(Trapi v1.5.0) : 7984a621a28c109c5c09f65fed0e7ea7
            #Automat-hetionet(Trapi v1.5.0) : a5fe24f987331b58191e67598118f369
            #Automat-ctd(Trapi v1.5.0) : f82c01b15c46e024212c1a3271aaef0b
            #Automat-intact(Trapi v1.5.0) : b4023595664163e0aec5e825da150e16
            #Automat-ehr-clinical-connections-kp(Trapi v1.5.0) : 6f4dd91bc56fce4f597bc44153cf418e
            #Automat-icees-kg(Trapi v1.5.0) : c64d583402f21cc85810d33befe49c86
            #Automat-panther(Trapi v1.5.0) : 3f78d3fb8a7a577fbc7cc0a913ac3fc5
            #Biolink Lookup : 02f84c50043e94970316568439b7b384
            'COHD TRAPI' : 'https://cohd-api.transltr.io/api/query/', ##d4290b6b5741e6da6cc6a6f42e0cfdb5
            #'Text Mined Cooccurrence API' : "https://cooccurence.ci.transltr.io/query/", #aa9c668df9d217409891cc7afb7ac039
            #'Text Mined Cooccurrence API' : "https//cooccurrence.transltr.io/query", #71fa2e0f0f1fe1ec67f4ddb719db5ef3
            #BioThings Rhea API : 03283cc2b21c077be6794e1704b1d230
            #SmartAPI API : 27a5b60716c3a401f2c021a5b718c5b1
            #MyDisease.info API : 671b45c0301c8624abbd26ae78449ca2
            #MyVariant.info API : 09c8782d9f4027712e65b95424adba79
            #BioThings UBERON API : ec6d76016ef40f284359d17fbf78df20
            #OpenPredict API : 025600054bd8d6fb14ee66ee9d4a9830
            #MyGene.info API : 59dce17363dce279d389100834e43648
            #Answer-coalesce(Trapi v1.5.0) : fe8bb783ff710ab4e176f38c5f7777af
            #BioThings HPO API : a5b0ec6bfde5008984d4b6cde402d61f
            #Drug Approvals KP - TRAPI 1.5.0 : edc04feaf16c12424737988ce2e90d60
            #Gene-List Network Enrichment Analysis : 5c8740542b4444d4f85c2e23c670b952
            #MolePro : 1901bab8d33bb70b124f400ec1cfdba3
            #Multiomics KP - TRAPI 1.5.0 : 1b6de23ed3c4e0713b20794477ba1e39
            #Microbiome KP - TRAPI 1.5.0 : a8be4ea3fe8fa80a952ead0b3c5e4bc1
            #BioThings GO Biological Process API : cc857d5b7c8b7609b5bbb38ff990bfff
            #imProving Agent for TRAPI 1.5 : 415c3b1a85ead4ceb58caf00dee9b24e
            #Clinical Trials KP - TRAPI 1.5.0 : e51073371d7049b9643e1edbdd61bcbd
            #BioThings EBIgene2phenotype API : 1f47552dabd67351d4c625adb0a10d00
            #BioThings RARe-SOURCE API : b772ebfbfa536bba37764d7fddb11d6f
            #PharmGKB REST API : bde72db681ec0b8f9eeb67bb6b8dd72c
            #BioThings DDInter API : 00fb85fc776279163199e6c50f6ddfc6
            #MyChem.info API : 8f08d1446e0bb9c2b323713ce83e2bd3
            #BioThings BindingDB API : 38e9e5169a72aee3659c9ddba956790d
            #BioThings PFOCR API : edeb26858bd27d0322af93e7a9e08761
            #BioThings MGIgene2phenotype API : 77ed27f111262d0289ed4f4071faa619
            #BioThings FooDB API : f1b8f64c316a01d1722f0fb842499fe5
            #Genetics Data Provider for NCATS Biomedical Translator Reasoners : db981dff8d93dcb0cfab5dbee8afbb40
            #BioThings GO Molecular Function API : 34bad236d77bea0a0ee6c6cba5be54a6
            #BioThings BioPlanet Pathway-Disease API : 55a223c6c6e0291dbd05f2faf27d16f4
            #BioThings DISEASES API : a7f784626a426d054885a5f33f17d3f8
            #BioThings BioPlanet Pathway-Gene API : b99c6dd64abcefe87dcd0a51c249ee6d
            #BioThings GO Cellular Component API : f339b28426e7bf72028f60feefcd7465
            #SPOKE KP for TRAPI 1.5 : 7f70cdfaeb801501da08dacc294e8b9f
            #BioThings IDISK API : 32f36164fabed5d3abe6c2fd899c9418
            #BioThings FoodData Central API : 895ec14a3650ec7ad85959a2d1554e2f
            #BioThings AGR API : 68f12100e74342ae0dd5013d5f453194
            #Translator Annotation Service : 5a4c41bf2076b469a0e9cfcf2f2b8f29
            #BioThings InnateDB API : e9eb40ff7ad712e4e6f4f04b964b5966
            #BioThings repoDB API : 1138c3297e8e403b6ac10cff5609b319
            #BioThings GTRx API : 316eab811fd9ef1097df98bcaa9f7361
            #BioThings Explorer (BTE) TRAPI : dc91716f44207d2e1287c727f281d339
            #RTX KG2 - TRAPI 1.5.0 : a6b575139cfd429b0a87f825a625d036
            #BioThings SuppKG API : b48c34df08d16311e3bca06b135b828d
            #Knowledge Collaboratory API : 8601da411b8681dbbc32239ceb0f1a55
            ##Service Provider TRAPI : 36f82f05705c317bac17ddae3a0ea2f0
            #Multiomics EHR Risk KP API : d86a24f6027ffe778f84ba10a7a1861a
            #Multiomics Wellness KP API : 02af7d098ab304e80d6f4806c3527027
            #BioThings DGIdb API : e3edd325c76f2992a111b43a907a4870
            #BioThings SEMMEDDB API : 1d288b3a3caf75d541ffaae3aab386c8
            'Multiomics BigGIM-DrugResponse KP API' : 'https://biothings.ci.transltr.io/biggim_drugresponse_kg/query/', #adf20dd6ff23dfe18e8e012bde686e31
            #Biothings Therapeutic Target Database API : e481efd21f8e8c1deac05662439c2294
            #Text Mining Targeted Association API : 978fe380a147a8641caf72320862697b
           'ARAX Translator Reasoner - TRAPI 1.5.0' : 'https://arax.transltr.io/api/arax/v1.4/query/', # 03e63fbd5ed251bce08cb5801b6b169b

        'Automat-ctd(Trapi v1.4.0)':"https://automat.transltr.io/ctd/1.4/query",
        #'Automat-sri-reference-kg(Trapi v1.4.0)':"",
        #'Autonomous Relay System (ARS) TRAPI':"",
        #'BioLink API':"",
        #'BioThings AGR API':"",
        #'BioThings BioPlanet Pathway-Gene API':"",
        #'BioThings DDInter API':"",
        'BioThings Explorer (BTE) TRAPI':"https://bte.transltr.io/v1/query",
        #'BioThings FooDB API':"",
        #'BioThings FoodData Central API':"",
        #'BioThings GO Biological Process API':"",
        #'BioThings InnateDB API':"", # not in TRAPI standard
        #'BioThings RARe-SOURCE API':"",
        #'BioThings repoDB API':"",
        #'Biolink Lookup':"",
        'Biothings Therapeutic Target Database API':"https://biothings.ncats.io/ttd/query",
        #'COHD TRAPI':"https://cohd-api.transltr.io/api/query",
        #'Complex Portal Web Service':"",
        #'Curated Query Service':"",
        #'EBI Proteins API':"",
        #'Gene-List Network Enrichment Analysis':"",
        #'Knowledge Collaboratory API':"",
        #'LitVar API':"",
        #'RaMP API v1.0.1':"",
        #'SmartAPI API':"",
        #'Sri-answer-appraiser(Trapi v1.4.0)':"",
        #'Sri-name-resolver':"",
        #'Sri-node-normalizer(Trapi v1.3.0)':"",
        #'Sri-node-normalizer(Trapi v1.4.0)':"",
        #'Translator Annotation Service':"",
        #'Workflow-runner(Trapi v1.4.0)':"https://translator-workflow-runner.transltr.io/query",
        #'imProving Agent for TRAPI 1.4':"",
        #'mediKanren':'https://medikanren-trapi.transltr.io/query', #ARA
        #"BigGIM_BMG":"http://127.0.0.1:8000/find_path_by_predicate",
        "Aragorn(Trapi v1.4.0)":"https://aragorn.transltr.io/aragorn/query",
        #"ARAX Translator Reasoner - TRAPI 1.4.0":"https://arax.transltr.io/api/arax/v1.4/asyncquery",
        "ARAX Translator Reasoner - TRAPI 1.4.0":"https://arax.transltr.io/api/arax/v1.4/query",
        "RTX KG2 - TRAPI 1.4.0":"https://arax.ncats.io/api/rtxkg2/v1.4/query",
        "SPOKE KP for TRAPI 1.4":"https://spokekp.transltr.io/api/v1.4/query",
        # Duplicate removed - "Multiomics BigGIM-DrugResponse KP API":"https://bte.transltr.io/v1/smartapi/adf20dd6ff23dfe18e8e012bde686e31/query",
        "Multiomics ClinicalTrials KP":"https://api.bte.ncats.io/v1/smartapi/d86a24f6027ffe778f84ba10a7a1861a/query",
        "Multiomics Wellness KP API":"https://api.bte.ncats.io/v1/smartapi/02af7d098ab304e80d6f4806c3527027/query",
        "Multiomics EHR Risk KP API":"https://api.bte.ncats.io/v1/smartapi/d86a24f6027ffe778f84ba10a7a1861a/query",
        "Biothings Explorer (BTE)":"https://bte.transltr.io/v1/query",
        "Service Provider TRAPI":"https://api.bte.ncats.io/v1/smartapi/978fe380a147a8641caf72320862697b/query",
        "Explanatory-agent":"https://explanatory-agent-creative.azurewebsites.net/ARA/v1.3/asyncquery", #403 error
        "MolePro":"https://translator.broadinstitute.org/molepro/trapi/v1.4/query",
        "Genetics KP":"https://genetics-kp.transltr.io/genetics_provider/trapi/v1.4/query",
        "medikanren-unsecret":"https://medikanren-trapi.transltr.io/query",
        "Text Mined Cooccurrence API":"https://api.bte.ncats.io/v1/smartapi/978fe380a147a8641caf72320862697b/query",
        "OpenPredict API":"https://openpredict.transltr.io/query",
        "Agrkb(Trapi v1.4.0)":"https://automat.transltr.io/genome-alliance/1.4/query",
        "Automat-biolink(Trapi v1.4.0)": "https://automat.renci.org/biolink/1.4/query",
        "Automat-cam-kp(Trapi v1.4.0)": "https://automat.ci.transltr.io/cam-kp/1.4/query?limit=100",
        #"Automat-ctd(Trapi v1.4.0)": "https://automat.renci.org/drugcentral/1.4/query",
        "Automat-drug-central(Trapi v1.4.0)": "https://automat.ci.renci.org/drugcentral/1.4/query",
        "Automat-gtex(Trapi v1.4.0)":"https://automat.renci.org/gtex/1.4/query",
        "Automat-gtopdb(Trapi v1.4.0)": "https://automat.renci.org/gtopdb/1.4/query",
        "Automat-gwas-catalog(Trapi v1.4.0)": "https://automat.renci.org/gwas-catalog/1.4/query",
        "Automat-hetio(Trapi v1.4.0)": "https://automat.ci.transltr.io/hetio/1.4/query",
        "Automat-hgnc(Trapi v1.4.0)": "https://automat.renci.org/hgnc/1.4/query",
        "Automat-hmdb(Trapi v1.4.0)": "https://automat.renci.org/hmdb/1.4/query",
        "Automat-human-goa(Trapi v1.4.0)": "https://automat.renci.org/human-goa/1.4/query",
        "Automat-icees-kg(Trapi v1.4.0)": "https://automat.renci.org/icees-kg/1.4/query",
        "Automat-intact(Trapi v1.4.0)": "https://automat.renci.org/intact/1.4/query",
        "Automat-panther(Trapi v1.4.0)": "https://automat.renci.org/panther/1.4/query",
        "Automat-pharos(Trapi v1.4.0)": "https://automat.renci.org/pharos/1.4/query",
        "Automat-robokop(Trapi v1.4.0)": "https://ars-prod.transltr.io/ara-robokop/api/runquery", #doesn't work
        "Automat-sri-reference-kp(Trapi v1.4.0)": "https://automat.ci.transltr.io/sri-reference-kp/1.4/query", #doesn't work
        "Automat-string-db(Trapi v1.4.0)": "https://automat.ci.transltr.io/string-db/1.4/query",
        "Automat-ubergraph(Trapi v1.4.0)": "https://automat.ci.transltr.io/ubergraph/1.4/query",
        "Automat-ubergraph-nonredundant(Trapi v1.4.0)": "https://automat.ci.transltr.io/ubergraph-nonredundant/1.4/query",
        "Automat-viral-proteome(Trapi v1.4.0)": "https://automat.ci.transltr.io/viral-proteome/1.4/query",
        "CTD API":"https://automat.ci.transltr.io/ctd/1.4/query",
        # Duplicate removed - "Connections Hypothesis Provider API":"https://chp-api.transltr.io/query", #no knowledge_graph is defined in the response
        "MyGene.info API":"https://api.bte.ncats.io/v1/smartapi/59dce17363dce279d389100834e43648/query", #check with chunlei
        "MyDisease.info API":"https://api.bte.ncats.io/v1/smartapi/671b45c0301c8624abbd26ae78449ca2/query", #check with chunlei
        "MyChem.info API":"https://api.bte.ncats.io/v1/8f08d1446e0bb9c2b323713ce83e2bd3/query", #check with chunlei
        "MyVariant.info API":"https://api.bte.ncats.io/v1/59dce17363dce279d389100834e43648/query", #check with chunlei
        "Ontology Lookup Service API":"https://api.bte.ncats.io/v1/1c056ffc7ed0dd1229e71c4752239465/query", #check with chunlei
        "PharmGKB REST API":"https://api.bte.ncats.io/v1/bde72db681ec0b8f9eeb67bb6b8dd72c/query", #need to check with chunlei/Andrew
        "QuickGO API":"https://api.bte.ncats.io/v1/1f277e1563fcfd124bfae2cc3c4bcdec/query",#pathways
        #"RaMP API v1.0.1":"",
        "Text Mining Targeted Association API":"https://api.bte.ncats.io/v1/smartapi/978fe380a147a8641caf72320862697b/query",
        "BioThings BindingDB API":"https://api.bte.ncats.io/v1/smartapi/38e9e5169a72aee3659c9ddba956790d/query",
        "BioThings BioPlanet Pathway-Disease API":"https://api.bte.ncats.io/v1/smartapi/55a223c6c6e0291dbd05f2faf27d16f4/query",
        "BioThings DDinter API":"https://api.bte.ncats.io/v1/smartapi/00fb85fc776279163199e6c50f6ddfc6/query",
        "BioThings DGIdb API":"https://api.bte.ncats.io/v1/smartapi/e3edd325c76f2992a111b43a907a4870/query",
        "BioThings DISEASES API":"https://api.bte.ncats.io/v1/smartapi/a7f784626a426d054885a5f33f17d3f8/query",
        "BioThings EBIgene2phenotype API":"https://api.bte.ncats.io/v1/smartapi/1f47552dabd67351d4c625adb0a10d00/query",
        "BioThings Biological Process API":"https://api.bte.ncats.io/v1/smartapi/cc857d5b7c8b7609b5bbb38ff990bfff/query",
        "BioThings GO Cellular Component API":"https://api.bte.ncats.io/v1/smartapi/f339b28426e7bf72028f60feefcd7465/query",
        "BioThings GO Molecular Function API":"https://api.bte.ncats.io/v1/smartapi/34bad236d77bea0a0ee6c6cba5be54a6/query",
        "BioThings GTRx API":"https://api.bte.ncats.io/v1/smartapi/316eab811fd9ef1097df98bcaa9f7361/query",
        "BioThings HPO API": "https://api.bte.ncats.io/v1/smartapi/d7d1cc9bbe04ad9936076ca5aea904fe/query",
        "BioThings IDISK API":"https://api.bte.ncats.io/v1/smartapi/32f36164fabed5d3abe6c2fd899c9418/query",
        "BioThings MGIgene2phenotype API":"https://api.bte.ncats.io/v1/smartapi/77ed27f111262d0289ed4f4071faa619/query",
        "BioThings PFOCR API":"https://api.bte.ncats.io/v1/smartapi/edeb26858bd27d0322af93e7a9e08761/query",
        "Biothings RARe-SOURCE API":"https://api.bte.ncats.io/v1/smartapi/b772ebfbfa536bba37764d7fddb11d6f/query",
        "BioThings Rhea API":"https://api.bte.ncats.io/v1/smartapi/03283cc2b21c077be6794e1704b1d230/query",
        "BioThings SEMMEDDB API":"https://api.bte.ncats.io/v1/smartapi/1d288b3a3caf75d541ffaae3aab386c8/query",
        "BioThings SuppKG API":"https://api.bte.ncats.io/v1/smartapi/b48c34df08d16311e3bca06b135b828d/query",
        "BioThings UBERON API":"https://api.bte.ncats.io/v1/smartapi/ec6d76016ef40f284359d17fbf78df20/query",
    }
    return(APInames)






# used. Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def select_API(sub_list,obj_list, metaKG):
    '''
    selects the APIs that can connect the given subject and object categories in the meta knowledge graph.

    sub_list = ["biolink:Gene", "biolink:Protein"]
    obj_list = ["biolink:Gene", "biolink:Disease"]

    ---------
    Example:
    >>> sub_list = ["biolink:Gene", "biolink:Protein"]
    >>> obj_list = ["biolink:Gene", "biolink:Disease"]
    >>>
    >>> Translator_KP_info,APInames= translator_kpinfo.get_translator_kp_info()
    >>> print(len(Translator_KP_info))
    >>> metaKG = translator_metakg.get_KP_metadata(APInames)
    >>> print(metaKG.shape)
    >>> APInames,metaKG = translator_metakg.add_plover_API(APInames, metaKG)
    >>> selected_apis = select_API(sub_list, obj_list, metaKG)
    >>> print(selected_apis)
    '''
    new_sub_list = sub_list
    new_obj_list = obj_list
    #for item in sub_list:
    #    new_sub_list.append(item.split(":")[1])
    #for item in obj_list:
    #    new_obj_list.append(item.split(":")[1])

    #metaKG = pd.read_csv("KP_metadata.csv")
    df1 = metaKG.loc[(metaKG['Subject'].isin(new_sub_list)) & (metaKG['Object'].isin(new_obj_list))]
    df2 = metaKG.loc[(metaKG['Subject'].isin(new_obj_list)) & (metaKG['Object'].isin(new_sub_list))]
    df = pd.concat([df1,df2])
    return(list(set(df['API'].values)))



# used. Dec 5, 2023  (Example_query_one_hop_with_category.ipynb)
def select_concept(sub_list,obj_list,metaKG):
    '''
    Selects the predicates connecting the given subject and object categories in the meta knowledge graph.
    '''
    #result_df = pd.read_csv("KP_metadata.csv")
    df1 = metaKG.loc[(metaKG['Subject'].isin(sub_list)) & (metaKG['Object'].isin(obj_list))]
    df2 = metaKG.loc[(metaKG['Subject'].isin(obj_list)) & (metaKG['Object'].isin(sub_list))]
    df = pd.concat([df1,df2])
    return(set(list(df['Predicate'])))
def sele_predicates_API(input_node1_category,input_node2_category,metaKG, APInames):
    '''
    Selects predicates, APIs, and API URLs for the given input node categories.

    -----------
    Example:
    >>> sele_predicates, sele_APIs, API_URLs = sele_predicates_API(input_node1_category,input_node2_category,metaKG, APInames)

    '''
    sele_predicates = list(set(select_concept(sub_list=input_node1_category,
                                                 obj_list=input_node2_category,
                                                 metaKG=metaKG)))
    sele_APIs = select_API(sub_list=input_node1_category,
                           obj_list=input_node2_category,
                           metaKG=metaKG)

    API_URLs = get_Translator_API_URL(sele_APIs, APInames)
    if len(sele_predicates) == 0:
        print("No predicates found for the given categories.")
    if len(sele_APIs) == 0:
        print("No APIs found for the given categories.")
    if len(API_URLs) == 0:
        print("No API URLs found for the given categories.")

    return sele_predicates, sele_APIs, API_URLs
# used. Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def get_Translator_API_URL(API_sele, APInames):
    API_URL = []
    #API_URL = {}
    for name in API_sele:
        if name in APInames.keys():
            API_URL.append(APInames[name])
            #API_URL[name] = APInames[name]
        else:
            print(name + " : API name not found")
    return API_URL

# select APIs based on the predicates. Dec 10, 2023
def filter_APIs(sele_predicates, metaKG):
    if sele_predicates == []:
        sele_API_URL = list(metaKG['KG_category'].unique())
    else:
        sele_API_URL = list(metaKG.loc[metaKG['KG_category'].isin(sele_predicates)]['URL'].unique())
    return sele_API_URL

def select_predicates_inKP(sub_list,obj_list,KPname,metaKG):
    '''sub_list = ["biolink:Gene", "biolink:Protein"]
      obj_list = ["biolink:Gene", "biolink:Disease"]
      KPname = "" # it should be one of the names in APInames
    '''

    new_sub_list = []
    new_obj_list = []
    for item in sub_list:
        new_sub_list.append(item.split(":")[1])
    for item in obj_list:
        new_obj_list.append(item.split(":")[1])

    #result_df = pd.read_csv("KP_metadata.csv")
    df1 = metaKG.loc[(metaKG['Subject'].isin(new_sub_list)) & (metaKG['Object'].isin(new_obj_list)) & (metaKG['API']==KPname)]
    df2 = metaKG.loc[(metaKG['Subject'].isin(new_obj_list)) & (metaKG['Object'].isin(new_sub_list)) & (metaKG['API']==KPname)]
    df = pd.concat([df1,df2])
    temp_set = (set(list(df['KG_category'])))
    final_set = []
    for concept in temp_set:
        #final_set.append("biolink:"+concept.split("-")[1])
        final_set.append(concept)
    return(final_set)


#def Generate_Gene_id_map():
#    id_file = open("../metaData/Homo_sapiens.gene_info", "r")
#    Gene_id_map = {}
#    for line in id_file:
#        line = line.strip()
#        Gene_id_map["NCBIGene:"+line.split("\t")[1]] = line.split("\t")[2]
#    id_file.close()
#    return(Gene_id_map)

# Used. Jan 5, 2024
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
    from . import node_normalizer
    return node_normalizer.ID_convert_to_preferred_name_nodeNormalizer(id_list)


def _convert_ids_to_names(id_list):
    """Return preferred names for CURIEs as a list, falling back to original IDs."""
    name_map = ID_convert_to_preferred_name_nodeNormalizer(id_list)
    return [name_map.get(curie, curie) for curie in id_list]




# used. Dec 5, 2023  (Example_query_one_hop_with_category.ipynb)
def Gene_id_converter(id_list, API_url):
    id_list_new = []
    for id in id_list:
        if id.startswith("NCBIGene:"):
            id = id.replace("NCBIGene:", "NCBIGene")
            id_list_new.append(id)
    query_json = {
                    "message": {
                        "query_graph": {
                        "nodes": {
                            "n0": {
                            "categories": ["Gene"],
                            "ids": id_list_new
                            },
                            "n1": {
                            "categories": [
                                "string"
                            ],
                            "ids": [
                                "string"
                            ]
                            }
                        },
                        "edges": {
                            "e1": {
                            "predicates": [
                                "string"
                            ]
                            }
                        }
                        }
                    }
                    }

    response = requests.post(API_url, json=query_json)
    result = {}

    if response.status_code == 200:
        result = response.json()

    return(result)


# used. Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def format_query_json(subject_ids, object_ids, subject_categories, object_categories, predicates):
    '''
    Example input:
    subject_ids = ["NCBIGene:3845"]
    object_ids = []
    subject_categories = ["biolink:Gene"]
    object_categories = ["biolink:Gene"]
    predicates = ["biolink:positively_correlated_with", "biolink:physically_interacts_with"]

    '''
    #edited Dec 5, 2023
    query_json_temp = {
        "message": {
            "query_graph": {

                "edges": {
                    "e00": {
                    #"e1": {
                        "subject": "n01",
                        "object": "n00",
                        "predicates": predicates
                        }
                    },
                "nodes": {
                    "n00": {
                        "ids":subject_ids, # required
                        #"categories":[] # optional, if not provided, it will be empty
                        },
                    "n01": {
                        #"ids":[],
                        "categories":[] # required
                        }}
                }
            }
        }

    if len(subject_ids) > 0:
        #query_json_temp["message"]["query_graph"]["nodes"]["n0"]["ids"] = subject_ids
        query_json_temp["message"]["query_graph"]["nodes"]["n00"]["ids"] = subject_ids

    #if len(object_ids) > 0:
        #query_json_temp["message"]["query_graph"]["nodes"]["n1"]["ids"] = object_ids
        #query_json_temp["message"]["query_graph"]["nodes"]["n00"]["ids"] = object_ids

    #if len(subject_categories) > 0:
    #    query_json_temp["message"]["query_graph"]["nodes"]["n01"]["categories"] = subject_categories

    if len(object_categories) > 0:
        #query_json_temp["message"]["query_graph"]["nodes"]["n1"]["categories"] = object_categories
        query_json_temp["message"]["query_graph"]["nodes"]["n01"]["categories"] = object_categories

    if len(predicates) > 0:
        query_json_temp["message"]["query_graph"]["edges"]["e00"]["predicates"] = predicates

    return(query_json_temp)


def Neighborhood_finder_mcp(input_node, node2_categories):
    """
    This function is used to find the neighborhood connections of a given input node with the specified categories. The categories defined must be a predefined  biolink category.

    --------------
    Parameters:
    input_node (str): The input node, can be a gene name, protein name, or any other identifier.
    node2_categories (list): A list of intermediate categories to be used in the neighborhood finding process.
    
    --------------
    Returns:
    result: the ranked results of the query for the input node.

    --------------
    Example:
    >>> result = Neighborhood_finder_mcp('Ovarian cancer',
                                        node2_categories = ['biolink:SmallMolecule', 'biolink:Drug', 'biolink:ChemicalEntity'])
    --------------

    """
    from . import translator_query
    from .translator_resources import TranslatorResources

    resources = TranslatorResources.load()

    # Step 1: Resolve the input node to get its curie id and categories
    input_node_info = name_resolver.lookup(input_node)
    input_node_id = input_node_info.curie
    print(input_node_id)

    # BUG: `input_node_category` is undefined; should be a parameter of this function.
    if len(input_node_category) == 0:
        input_node_category = input_node_info.types
    else:
        input_node_category = list(set(input_node_category).intersection(set(input_node_info.types)))
        if len(input_node_category) == 0:
            input_node_category = input_node_info.types

    # Step 2: Select predicates and APIs based on the intermediate categories
    sele_predicates, sele_APIs, API_URLs = sele_predicates_API(input_node_category,
                                                                node2_categories,
                                                                resources.meta_kg, resources.api_names)

    # Step 3: Format the query JSON for the input node
    query_json = format_query_json([input_node_id], [],
                                   [input_node_category],
                                   node2_categories,
                                   sele_predicates)

    # Step 4: Query the APIs in parallel
    result = translator_query.parallel_api_query(query_json=query_json,
                             select_APIs=sele_APIs,
                             resources=resources,
                             max_workers=len(sele_APIs))
    result_parsed = parse_KG(result)
        # Step 7: Ranking the results. This ranking method is based on the number of unique
        # primary infores. It can only be used to rank the results with one defined node.
    result_ranked_by_primary_infores1 = rank_by_primary_infores(result_parsed, input_node_id)   # input_node1_id is the curie id of the
    ranked_result = visulization_one_hop_ranking(result_ranked_by_primary_infores1, result_parsed,
                                num_of_nodes = 50, input_query = input_node_id,
                                fontsize = 5)

    return ranked_result

def Neiborhood_finder(input_node, node2_categories, resources=None, input_node_category=[],
                      *, APInames=None, metaKG=None, API_predicates=None):
    """
    This function is used to find the neighborhood of a given input node with intermediate categories.

    --------------
    Parameters:
    input_node (str): The input node - should be a CURIE id.
    node2_categories (list): A list of intermediate categories to be used in the neighborhood finding process.
    resources (TranslatorResources): Container with ``api_names``, ``meta_kg``, and ``api_predicates``.
    input_node_category (list): Optional. A list of categories for the input node. If empty, it will be derived from the input node's types.

    --------------
    Returns:
    NeighborhoodResult with input_node_id, knowledge_graph, parsed, and ranked fields.

    --------------
    Example:
    >>> nb_result = Neiborhood_finder('MONDO:0008170',
                                      node2_categories=['biolink:SmallMolecule', 'biolink:Drug', 'biolink:ChemicalEntity'],
                                      resources=resources)
    --------------

    """
    resources = _resolve_resources(resources, APInames=APInames, metaKG=metaKG, API_predicates=API_predicates)
    from . import node_normalizer
    from . import translator_query

    input_node_id = input_node
    # Step 1: Resolve the input node to get its curie id and categories
    input_node_info = node_normalizer.get_normalized_nodes(input_node_id)
    print(input_node_id)

    if len(input_node_category) == 0:
        input_node_category = input_node_info.types
    else:
        input_node_category = list(set(input_node_category).intersection(set(input_node_info.types)))
        if len(input_node_category) == 0:
            input_node_category = input_node_info.types

    # Step 2: Select predicates and APIs based on the intermediate categories
    sele_predicates, sele_APIs, API_URLs = sele_predicates_API(input_node_category,
                                                                node2_categories,
                                                                resources.meta_kg, resources.api_names)

    # Step 3: Format the query JSON for the input node
    query_json = format_query_json([input_node_id], [],
                                   [input_node_category],
                                   node2_categories,
                                   sele_predicates)

    # Step 4: Query the APIs in parallel
    result = translator_query.parallel_api_query(query_json=query_json,
                             select_APIs=sele_APIs,
                             resources=resources,
                             max_workers=len(sele_APIs))
    result_parsed = result.parse()
        # Step 7: Ranking the results. This ranking method is based on the number of unique
        # primary infores. It can only be used to rank the results with one defined node.
    result_ranked_by_primary_infores1 = result_parsed.rank(input_node_id)
    from .results import NeighborhoodResult
    return NeighborhoodResult(
        input_node_id=input_node_id,
        knowledge_graph=result,
        parsed=result_parsed,
        ranked=result_ranked_by_primary_infores1,
    )

def Path_finder(input_node1, input_node2, intermediate_categories, resources=None,
                input_node1_category=[], input_node2_category=[],
                *, APInames=None, metaKG=None, API_predicates=None):
    """
    This function is used to find paths between two input nodes with intermediate categories.

    --------------
    Parameters:
    input_node1 (str): The first input node - should be a CURIE id.
    input_node2 (str): The second input node - should be a CURIE id.
    intermediate_categories (list): A list of intermediate categories to be used in the path finding process.
    resources (TranslatorResources): Container with ``api_names``, ``meta_kg``, and ``api_predicates``.
    input_node1_category (list): Optional. A list of categories for the first input node.
    input_node2_category (list): Optional. A list of categories for the second input node.

    --------------
    Returns:
    PathResult with paths, node1_id, node2_id, knowledge_graph1/2, parsed1/2, ranked1/2 fields.

    --------------
    Example:
    >>> path_result = Path_finder('NCBIGene:7477', 'NCBIGene:4869', ['biolink:Gene', 'biolink:Protein'], resources=resources)
    --------------

    """
    resources = _resolve_resources(resources, APInames=APInames, metaKG=metaKG, API_predicates=API_predicates)
    from . import node_normalizer
    from . import translator_query
    input_node1_id = input_node1
    input_node2_id = input_node2
    print(input_node1_id)
    normalized_node_dict = node_normalizer.get_normalized_nodes([input_node1_id, input_node2_id])
    input_node1_info = normalized_node_dict[input_node1]
    input_node1_list = [input_node1_id]
    if len(input_node1_category) == 0:
        input_node1_category = input_node1_info.types
    else:
        input_node1_category = list(set(input_node1_category).intersection(set(input_node1_info.types)))
        if len(input_node1_category) == 0:
            input_node1_category = input_node1_info.types

    input_node2_info = normalized_node_dict[input_node2_id]
    print(input_node2_id)
    input_node2_list = [input_node2_id]

    if len(input_node2_category) == 0:
        input_node2_category = input_node2_info.types
    else:
        input_node2_category = list(set(input_node2_category).intersection(set(input_node2_info.types)))
        if len(input_node2_category) == 0:
            input_node2_category = input_node2_info.types


    # Step 5: Select predicates and APIs based on the intermediate categories
    sele_predicates1, sele_APIs1, API_URLs1 = sele_predicates_API(input_node1_category,
                                                                intermediate_categories,
                                                                resources.meta_kg, resources.api_names)
    sele_predicates2, sele_APIs2, API_URLs2 = sele_predicates_API(input_node2_category,
                                                                intermediate_categories,
                                                                resources.meta_kg, resources.api_names)

    query_json1 = format_query_json(input_node1_list,  # a list of identifiers for input node1
                                    [],  # id list for the intermediate node, it can be empty list if only want to query node1
                                    input_node1_category,  # a list of categories of input node1
                                    intermediate_categories,  # a list of categories of the intermediate node
                                    sele_predicates1) # a list of predicates

    query_json2 = format_query_json(input_node2_list,  # a list of identifiers for input node2
                                    [],  # id list for the intermediate node, it can be empty list if only want to query node2
                                    input_node2_category,  # a list of categories of input node2
                                    intermediate_categories,  # a list of categories of the intermediate node
                                    sele_predicates2) # a list of predicates

    result1 = translator_query.parallel_api_query(query_json=query_json1,
                             select_APIs=sele_APIs1,
                             resources=resources,
                             max_workers=len(sele_APIs1))
    result2 = translator_query.parallel_api_query(query_json=query_json2,
                                select_APIs=sele_APIs2,
                                resources=resources,
                                max_workers=len(sele_APIs2))

    result_parsed1 = result1.parse()
    result_ranked_by_primary_infores1 = result_parsed1.rank(input_node1_id)

    result_parsed2 = result2.parse()
    result_ranked_by_primary_infores2 = result_parsed2.rank(input_node2_id)

    possible_paths = len(set(result_ranked_by_primary_infores1['output_node']).intersection(set(result_ranked_by_primary_infores2['output_node'])))
    print("Number of possible paths: ", possible_paths)

    paths = merge_ranking_by_number_of_infores(result_ranked_by_primary_infores1, result_ranked_by_primary_infores2,
                                            top_n = 30,
                                            fontsize=10,
                                            title_fontsize=12,)

    from .results import PathResult
    return PathResult(
        paths=paths,
        node1_id=input_node1_id,
        node2_id=input_node2_id,
        knowledge_graph1=result1,
        knowledge_graph2=result2,
        parsed1=result_parsed1,
        parsed2=result_parsed2,
        ranked1=result_ranked_by_primary_infores1,
        ranked2=result_ranked_by_primary_infores2,
    )

# used. Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)


# used. Dec 5, 2023    (Example_query_one_hop_with_category.ipynb)
def parse_KG(result):
    '''
    Parse a knowledge graph result into consolidated entries grouped by subject-object pair.

    Accepts both raw edge dicts and KnowledgeGraph instances.
    '''
    from .results import KnowledgeGraph as _KnowledgeGraph
    if isinstance(result, _KnowledgeGraph):
        return result.parse()
    return _KnowledgeGraph(edges=result).parse()


# parse network results. Dec 10, 2023
def parse_network_result(result, input_node1_list):
    dic_nodes = {}
    for i in result:
        subject = result[i]['subject']
        object = result[i]['object']
        # predicate = result[i]['predicate']  # Unused variable
        # sources = result[i]['sources']  # Unused variable

        if subject == object:
            continue

        if subject in dic_nodes:
            dic_nodes[subject].append(object)
        else:
            dic_nodes[subject] = [object]

        if object in dic_nodes:
            dic_nodes[object].append(subject)
        else:
            dic_nodes[object] = [subject]



    dic_remain_nodes = {}

    dic_with_input_nodes = {}

    for i in dic_nodes:
        if i in input_node1_list:
            dic_remain_nodes[i] = dic_nodes[i]
        else:
            continue

    for i in dic_remain_nodes:
        for j in dic_nodes[i]:
            if j in dic_with_input_nodes:
                dic_with_input_nodes[j].append(i)
            else:
                dic_with_input_nodes[j] = [i]

    for i in dic_with_input_nodes:
        dic_with_input_nodes[i] = list(set(dic_with_input_nodes[i]))




    for i in dic_with_input_nodes:
        if len(set(dic_with_input_nodes[i])) > 1: #
            #print(i, set(dic_with_input_nodes[i]))
            if i not in dic_remain_nodes:
                dic_remain_nodes[i] = dic_with_input_nodes[i]
        else:
            continue

    dic_remain_nodes_final = {}
    for i in dic_remain_nodes:
        dic_remain_nodes_final[i] = set(dic_remain_nodes[i]).intersection(set(dic_remain_nodes.keys()))


    subject_nodes = []
    object_nodes = []

    for i in dic_remain_nodes_final:
        for j in dic_remain_nodes_final[i]:
            subject_nodes.append(i)
            object_nodes.append(j)

    result_df = pd.DataFrame({'Subject':subject_nodes, 'Object':object_nodes})
    #result_df.to_csv('result_df.csv', index=False)
    return result_df

def rank_by_primary_infores_input_as_list(result_parsed, input_nodes):
    ''' Editd Dec 5, 2023'''
    rank_df = pd.DataFrame()
    output_nodes = []
    input_nodes_list = []
    Num_of_primary_infores = []
    type_of_nodes   = []
    unique_predicates = []
    for i in result_parsed:
        curr_predict = result_parsed[i]['predicate']
        subject = result_parsed[i]['subject']
        object = result_parsed[i]['object']

        if subject in input_nodes:
            input_nodes_list.append(subject)
            output_nodes.append(object)
            type_of_nodes.append('object')
            Num_of_primary_infores.append(len(set(result_parsed[i]['primary_knowledge_source'])))
            unique_predicates.append(curr_predict)


        elif object in input_nodes:
            input_nodes_list.append(object)
            output_nodes.append(subject)
            type_of_nodes.append('subject')
            unique_predicates.append(curr_predict)

            Num_of_primary_infores.append(len(set(result_parsed[i]['primary_knowledge_source'])))

    new_colnames = _convert_ids_to_names(output_nodes)

    rank_df['output_node'] = output_nodes
    rank_df['Name'] = new_colnames
    rank_df['Num_of_primary_infores'] = Num_of_primary_infores
    rank_df['type_of_nodes'] = type_of_nodes
    rank_df['unique_predicates'] = unique_predicates

    rank_df['input_node'] = input_nodes_list

    rank_df_ranked = rank_df.sort_values(by=['Num_of_primary_infores'], ascending=False)
    return(rank_df_ranked)



# parse results to a dictionary. Dec 5, 2023
# used. Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def rank_by_primary_infores(result_parsed, input_node):
    '''Rank parsed knowledge graph entries by number of unique primary infores.

    Accepts both raw parsed dicts and ParsedKnowledgeGraph instances.
    '''
    from .results import ParsedKnowledgeGraph as _ParsedKnowledgeGraph
    if isinstance(result_parsed, _ParsedKnowledgeGraph):
        return result_parsed.rank(input_node)
    return _ParsedKnowledgeGraph(entries=result_parsed).rank(input_node)



# used. Dec 5, 2023 (Example_query_rank_the_path.ipynb)
def merge_by_ranking_index(result_ranked_by_primary_infores,
                           result_ranked_by_primary_infores2,
                           top_n = 20,
                           title_fontsize = 12,
                           fontsize = 12,
                           ):


    dic_rank1 = {}
    for i in range(0, result_ranked_by_primary_infores.shape[0]):
        dic_rank1[result_ranked_by_primary_infores['output_node'][i]] = 1 - i / result_ranked_by_primary_infores.shape[0]

    dic_rank2 = {}
    for i in range(0, result_ranked_by_primary_infores2.shape[0]):
        dic_rank2[result_ranked_by_primary_infores2['output_node'][i]] = 1 - i / result_ranked_by_primary_infores2.shape[0]

    merged_nodes = set(dic_rank1.keys()).intersection(set(dic_rank2.keys()))
    dic_merged_rank = {}

    for node in merged_nodes:
        dic_merged_rank[node] = dic_rank1[node] * dic_rank2[node]

    result_ranked = pd.DataFrame.from_dict(dic_merged_rank, orient='index', columns=['score'])
    result_ranked = result_ranked.sort_values(by=['score'], ascending=False)
    result_ranked = result_ranked.reset_index()
    result_ranked.columns = ['output_node', 'score']
    result_xy_sorted = result_ranked
    result_xy_sorted.index = result_ranked['output_node']

    new_colnames = _convert_ids_to_names(result_xy_sorted.index.to_list())

    result_xy_sorted.index = new_colnames
    result_xy_sorted = result_xy_sorted.sort_values(by=['score'], ascending=False)

    sns.set(style="whitegrid")
    plt.figure(figsize=(5,5), dpi = 300)
    ax = sns.barplot(x=result_xy_sorted.iloc[0:top_n].index, y=result_xy_sorted.iloc[0:top_n]['score'], color='grey')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90, ha="center", fontsize=fontsize)
    ax.set_ylabel("Ranking score")
    ax.title.set_size(title_fontsize)
    plt.tight_layout()
    #plt.show()

    return result_xy_sorted



def merge_ranking_by_number_of_infores(result_ranked_by_primary_infores,
                                       result_ranked_by_primary_infores1,
                                       top_n = 30,
                                       fontsize = 12,
                                       title_fontsize = 12,
                                       output_png = "NE_heatmap.png"
                                       ):
    overlapped = (set(result_ranked_by_primary_infores1['output_node']).intersection(set(result_ranked_by_primary_infores['output_node'])))
    x = result_ranked_by_primary_infores.loc[result_ranked_by_primary_infores['output_node'].isin(overlapped)]
    y = result_ranked_by_primary_infores1.loc[result_ranked_by_primary_infores1['output_node'].isin(overlapped)]
    dic_x = {}
    for i in range(x.shape[0]):
        dic_x[x.iloc[i]['output_node']] = x.iloc[i]['Num_of_primary_infores']/np.max(x['Num_of_primary_infores'])

    dic_y = {}
    for i in range(y.shape[0]):
        dic_y[y.iloc[i]['output_node']] = y.iloc[i]['Num_of_primary_infores']/np.max(y['Num_of_primary_infores'])

    predicts_list1 = []
    predicts_list2 = []
    dic_xy = {}
    for i in overlapped:
        #print(result_ranked_by_primary_infores[result_ranked_by_primary_infores['output_node'] == i]['unique_predicates'])
        dic_xy[i] = dic_x[i] * dic_y[i]
        predicts_list1.append('; '.join(list(set(result_ranked_by_primary_infores[result_ranked_by_primary_infores['output_node'] == i]['unique_predicates'].values[0]))))
        predicts_list2.append('; '.join(list(result_ranked_by_primary_infores1[result_ranked_by_primary_infores1['output_node'] == i]['unique_predicates'].values[0])))

    result_xy = pd.DataFrame.from_dict(dic_xy, orient='index', columns=['score'])
    result_xy['output_node'] = result_xy.index
    # convert the output_node to preferred name



    #result_xy["output_node_name"] = new_colnames
    result_xy['predictes1'] = predicts_list1
    result_xy['predictes2'] = predicts_list2

    result_xy_sorted = result_xy.sort_values(by=['score'], ascending=False)

    new_colnames = _convert_ids_to_names(result_xy_sorted.index.to_list())

    result_xy_sorted.index = new_colnames
    result_xy_sorted['output_node_name'] = new_colnames
    x = result_xy_sorted.iloc[0:top_n].index
    y = result_xy_sorted.iloc[0:top_n]['score']

    plot_path_bar(x,y,fontsize, title_fontsize, output_png=output_png)

    return result_xy_sorted

# Sri-name-resolver  Used Dec 5, 2023 (Example_query_one_hop_with_category.ipynb)
def get_curie(name):
    response = requests.get("https://name-lookup.transltr.io/lookup", params={
        'string': name,
        'autocomplete': False
    })
    if response.status_code == 200:
        result = response.json()
        if len(result) != 0:
            return(result[0]['curie'])
        else:
            return(name)
    else:
        return(name)

# annotate gene pairs or a list of genes. Feb 25, 2024
def get_pair_annotation(result, input_node_list):
    pairs_found = {}
    for i in result.keys():

        if result[i]['subject'] in input_node_list and result[i]['object'] in input_node_list and result[i]['subject'] != result[i]['object']:
            pairs_found[i] = result[i]
    return pairs_found


def parse_pair_annotation(pairs_found, input_node_list):
    edge_list = []
    dic_names = ID_convert_to_preferred_name_nodeNormalizer(input_node_list)

    for i in pairs_found.keys():
        primary_source = ''
        for source in pairs_found[i]['sources']:
            if source['resource_role'] == 'primary_knowledge_source':
                primary_source = source['resource_id']
                break
        edge_list.append([pairs_found[i]['subject'],dic_names[pairs_found[i]['subject']],  pairs_found[i]['predicate'], pairs_found[i]['object'], dic_names[pairs_found[i]['object']], primary_source ])
    return edge_list

# to be removed
def query_KP_all(subject_ids, object_ids, subject_categories, object_categories, predicates, API_list,metaKG, APInames):

    #APInames = API_list
    if len(API_list) == 0:
        API_list = select_API(subject_categories,object_categories,metaKG)
    else:
        API_list = list(APInames.keys())

    result_dict = {}
    result_concept = {}
    # Query individual KP

    # Needs parallel query


    for API_sele in API_list:
        print(API_sele)
        if len(predicates)==0:
            predicates_used = select_predicates_inKP(subject_categories,object_categories,API_sele,metaKG)
        else:
            predicates_used = predicates

        query_json = format_query_json(subject_ids, object_ids, subject_categories, object_categories, predicates_used)

        print(query_json)
        try:
            # kg_output = query_KP(APInames[API_sele],query_json)  # query_KP function not defined
            kg_output = None  # Placeholder - function not available

        except Exception:
            print("Connection Error")
            kg_output = None

        if kg_output is not None:
            # if kg_output is  a dictionary

            if isinstance(kg_output, dict) and 'nodes' in kg_output.keys():
                if len(kg_output['nodes']) >0:

                    print("Found: " + str(len(kg_output['edges'].keys())) + " nodes in " + API_sele)
                    print(predicates_used)
                    result_concept[API_sele] = predicates_used
                    result_dict[API_sele] = kg_output
    return(result_dict, result_concept)

# to be removed
def parse_result_old( API_keys_sele, API_keys_Not_include, predicates_forAnalysis,result_dic):
    Temp_APIkey = []
    Temp_subject_key = []
    Temp_object_key = []
    Temp_predicate_key = []
    Temp_infores_key = []
    API_keys_forAnalysis = []

    ALL_APIs_in_result = list(result_dic.keys())
    print(ALL_APIs_in_result)

    if len(API_keys_sele) == 0:
        API_keys_forAnalysis = ALL_APIs_in_result
    else:
        API_keys_forAnalysis = list(set(ALL_APIs_in_result).intersection(set(API_keys_sele)))

    if len(API_keys_Not_include) != 0:
        API_keys_forAnalysis = list(set(API_keys_forAnalysis) - set(API_keys_Not_include))


    print(API_keys_forAnalysis)

    for API_key in API_keys_forAnalysis:
        cur_API_outputKeys = list(result_dic[API_key]['edges'].keys())
        for i in range(0, len(cur_API_outputKeys)):
            curr_key = i
            curr_graph = (result_dic[API_key]['edges'][cur_API_outputKeys[curr_key]])
            predicate = (curr_graph['predicate'])
            if predicate != "biolink:subclass_of":
                infores = (curr_graph['sources'][0]['resource_id'])
                subject = (curr_graph['subject'])

                if subject.startswith("CL:"):
                    subject = "CL" + subject.split(":")[1]

                object = (curr_graph['object'])
                if object.startswith("CL:"):
                    object = "CL" + object.split(":")[1]

                #exclude subclass_of

                Temp_APIkey.append(API_key)
                Temp_subject_key.append(subject)
                Temp_object_key.append(object)
                Temp_predicate_key.append(predicate)
                Temp_infores_key.append(infores)

            #Temp_APIkey.append(API_key)
            #Temp_subject_key.append(subject)
            #Temp_object_key.append(object)
            #Temp_predicate_key.append(predicate)
            #Temp_infores_key.append(infores)

    Temp_result_df = pd.DataFrame({'API': Temp_APIkey,
                                   'Subject': Temp_subject_key,
                                   "Object":Temp_object_key,
                                   "Predicate":Temp_predicate_key,
                                   "Infores":Temp_infores_key})

    Temp_result_df.drop_duplicates(inplace=True)
    Temp_result_df = Temp_result_df.loc[Temp_result_df['API'].isin(API_keys_forAnalysis)]

    if len(predicates_forAnalysis) != 0:
        Temp_result_df = Temp_result_df.loc[Temp_result_df['Predicate'].isin(predicates_forAnalysis)]
    return(Temp_result_df)

# to be removed
def ranking_result_by_predicates_object(Temp_result_df):
    object_val_list = Temp_result_df['Object'].value_counts().index.tolist()
    object_val_value = Temp_result_df['Object'].value_counts().values.tolist()


    dic_rank = {}
    for i in range(0,len(object_val_list)):
        dic_rank[object_val_list[i]] = object_val_value[i]


    sorted_dic = sorted(dic_rank.items(), key=lambda x: x[1], reverse=True)
    return(sorted_dic)

# to be removed
def ranking_result_by_predicates_subject(Temp_result_df):
    subject_val_list = Temp_result_df['Subject'].value_counts().index.tolist()
    subject_val_list = Temp_result_df['Subject'].value_counts().values.tolist()

    dic_rank = {}
    for i in range(0,len(subject_val_list)):
        dic_rank[subject_val_list[i]] = subject_val_list[i]


    sorted_dic = sorted(dic_rank.items(), key=lambda x: x[1], reverse=True)
    return(sorted_dic)


# to be removed
def get_ranking_by_predicates(sorted_dic, Temp_result_df, Top):
    #item_ranking = []
    dic_ranking = {}

    if Top > len(sorted_dic):
        Top = len(sorted_dic)

    for i in range(1,Top):
        #item_ranking.append(sorted_dic[i][0])
        sele_result = sorted_dic[i][0]
        dic_ranking[sorted_dic[i][0]] = list(set(list(pd.concat([Temp_result_df.loc[Temp_result_df['Object'].isin([sele_result])], Temp_result_df.loc[Temp_result_df['Subject'].isin([sele_result])]], axis=0)['Predicate'])))

    return(dic_ranking)

# to be removed
def get_ranking_by_infores(sorted_dic, Temp_result_df, Top):
    #item_ranking = []
    dic_ranking = {}

    if Top > len(sorted_dic):
        Top = len(sorted_dic)

    for i in range(1,Top):
        #item_ranking.append(sorted_dic[i][0])
        sele_result = sorted_dic[i][0]
        dic_ranking[sorted_dic[i][0]] = list(set(list(pd.concat([Temp_result_df.loc[Temp_result_df['Object'].isin([sele_result])], Temp_result_df.loc[Temp_result_df['Subject'].isin([sele_result])]], axis=0)['Infores'])))

    return(dic_ranking)

# to be removed
def get_ranking_by_kp(sorted_dic, Temp_result_df, Top):
    #item_ranking = []
    dic_ranking = {}

    if Top > len(sorted_dic):
        Top = len(sorted_dic)

    for i in range(1,Top):
        #item_ranking.append(sorted_dic[i][0])
        sele_result = sorted_dic[i][0]
        dic_ranking[sorted_dic[i][0]] = list(set(list(pd.concat([Temp_result_df.loc[Temp_result_df['Object'].isin([sele_result])], Temp_result_df.loc[Temp_result_df['Subject'].isin([sele_result])]], axis=0)['API'])))

    return(dic_ranking)

# to be revised
def connecting_two_dots_two_hops(sorted_dic1, sorted_dic):
    intermediate = []
    normalized_rank = []

    rank1 = 0
    for i in sorted_dic1:
        gene1 = i[0]

        rank1 = rank1 + 1
        rank2 = 0
        for j in sorted_dic:
            gene2 = j[0]
            rank2 = rank2 + 1
            if gene1 == gene2:
                normlized_rank1 = rank1/(len(sorted_dic1) -1)
                normlized_rank2 = rank2/(len(sorted_dic) -1)
                new_order = normlized_rank1 * normlized_rank2
                intermediate.append(gene2)
                normalized_rank.append(new_order)

    res_df = pd.DataFrame({"node":intermediate, "normalized_rank":normalized_rank})
    res_df.sort_values(by=['normalized_rank'], inplace=True, ascending=True)
    res_df.reset_index(inplace=True, drop=True)

    return(res_df)

# First definition of select_result_to_analysis removed - duplicate function

# need revision
def find_path_by_two_ends(subject1_ids,
                          subject1_categories,
                          predicates1,
                          object_categories,
                          subject2_ids,
                          subject2_categories,
                          predicates2,
                          API_list1,
                          API_list2,
                          API1_keys_forAnalysis,
                          API1_keys_NotforAnalysis,
                          API2_keys_forAnalysis,
                          API2_keys_NotforAnalysis,
                          metaKG,
                          APInames
                          ):

    result_dic_node1, result_concept_node1 = query_KP_all(subject1_ids, [], subject1_categories, object_categories, predicates1, API_list1, metaKG, APInames)
    result_dic_node2, result_concept_node2 = query_KP_all(subject2_ids, [], subject2_categories, object_categories, predicates2, API_list2, metaKG, APInames)


    # Temp_result_df1 = parse_result(API1_keys_forAnalysis,API1_keys_NotforAnalysis, result_concept_node1, result_dic_node1)  # parse_result function not defined
    Temp_result_df1 = None  # Placeholder - function not available
    sorted_dic1 = ranking_result_by_predicates_object(Temp_result_df1)

    dic_ranking1 = get_ranking_by_infores(sorted_dic1, Temp_result_df1, 20)

    # Temp_result_df2 = parse_result(API2_keys_forAnalysis,API2_keys_NotforAnalysis, result_concept_node2, result_dic_node2)  # parse_result function not defined
    Temp_result_df2 = None  # Placeholder - function not available
    sorted_dic2 = ranking_result_by_predicates_object(Temp_result_df2)

    dic_ranking2 = get_ranking_by_infores(sorted_dic2, Temp_result_df2, 20)

    connection_nodes_df = connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)

    # bind all results in to a dictionary
    result = {"connection_nodes_df":connection_nodes_df,
              "dic_ranking1":dic_ranking1,
              "dic_ranking2":dic_ranking2,
              "Temp_result_df1":Temp_result_df1,
              "Temp_result_df2":Temp_result_df2,
              "result_dic_node1":result_dic_node1,
              "result_dic_node2":result_dic_node2,
              "result_concept_node1":result_concept_node1,
              "result_concept_node2":result_concept_node2}

    #return(connection_nodes_df, dic_ranking1, dic_ranking2, Temp_result_df1, Temp_result_df2,result_dic_node1, result_dic_node2, result_concept_node1, result_concept_node2)
    return(result)


def select_result_to_analysis(sele_genes,Temp_result_df1, Temp_result_df2 ):

    print("selected_path: "+ ';'.join(sele_genes))
    for_plot = pd.concat([  Temp_result_df1.loc[Temp_result_df1['Object'].isin(sele_genes)],
                            Temp_result_df2.loc[Temp_result_df2['Object'].isin(sele_genes)]], axis=0)

    return(for_plot)



def load_json_template():
    query_json_temp = {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {
                        "ids":[],
                        "categories":["biolink:category"]
                    },
                    "n1": {
                        "categories":["biolink:category"]
                }
                },
                "edges": {
                    "e1": {
                        "subject": "n0",
                        "object": "n1",
                        "predicates": ["biolink:predicates"]
                    }
                }
            }
        }
    }
    return(query_json_temp)

def extract_json(txt):
    import json
    lft = txt.find('{')
    while lft != -1:
        rgt = txt.find('}', lft+1)
        while rgt != -1:
            substr = txt[lft:rgt+1]
            try:
                jsn = json.loads(substr)
                return jsn
            except Exception:
                rgt = txt.find('}', rgt+1)
        lft = txt.find('{', lft+1)
    return None


def TRAPI_json_validation(query_json_cur_clean, ALL_predicates, ALL_categories):
    if 'message' not in query_json_cur_clean.keys():
        print('message is missing')
    else:
        if 'query_graph' not in query_json_cur_clean['message'].keys():
            print('query_graph is missing')
        else:
            if 'edges' not in query_json_cur_clean['message']['query_graph'].keys():
                print('edges is missing')
            else:
                if 'e1' not in query_json_cur_clean['message']['query_graph']['edges'].keys():
                    print('e1 is missing')
                else:
                    if 'predicates' not in query_json_cur_clean['message']['query_graph']['edges']['e1'].keys():
                        print('predicates is missing')

                    else:
                        if len(set(query_json_cur_clean['message']['query_graph']['edges']['e1']['predicates']).intersection(set(ALL_predicates))) == 0:
                            print('predicates is not in the KG')
                        else:
                            print("Predicates ok!")

                if 'nodes' not in query_json_cur_clean['message']['query_graph'].keys():
                    print('nodes is missing')
                else:
                    if 'n0' not in query_json_cur_clean['message']['query_graph']['nodes'].keys():
                        print('n0 is missing')
                    else:
                        if 'categories' not in query_json_cur_clean['message']['query_graph']['nodes']['n0'].keys():
                            print('categories is missing')
                        else:
                            if len(set(query_json_cur_clean['message']['query_graph']['nodes']['n0']['categories']).intersection(set(ALL_categories))) == 0:
                                print('categories is not in the KG')
                            else:
                                print("node0 category OK!")

                    if 'n1' not in query_json_cur_clean['message']['query_graph']['nodes'].keys():
                        print('n1 is missing')
                    else:
                        if 'categories' not in query_json_cur_clean['message']['query_graph']['nodes']['n1'].keys():
                            print('categories is missing')
                        else:
                            if len(set(query_json_cur_clean['message']['query_graph']['nodes']['n1']['categories']).intersection(set(ALL_categories))) == 0:
                                print('categories is not in the KG')
                            else:
                                print("node1 category OK!")

    return()

def format_id(query_json_cur_clean):
    if 'ids' in query_json_cur_clean['message']['query_graph']['nodes']['n0'].keys():
        input_nodes = query_json_cur_clean['message']['query_graph']['nodes']['n0']['ids']
        input_node1_id = []
        if len(input_nodes) > 0:
            for i in input_nodes:
                input_node1_id.append(get_curie(i))
            print(input_node1_id)

        query_json_cur_clean['message']['query_graph']['nodes']['n0']['ids'] = input_node1_id

    if 'ids' in query_json_cur_clean['message']['query_graph']['nodes']['n1'].keys():
        input_nodes2 = query_json_cur_clean['message']['query_graph']['nodes']['n1']['ids']
        input_node2_id = []
        if len(input_nodes2) > 0:
            for i in input_nodes2:
                input_node2_id.append(get_curie(i))
            print(input_node2_id)
        query_json_cur_clean['message']['query_graph']['nodes']['n1']['ids'] = input_node2_id
    return(query_json_cur_clean)

@_dataclass
class ChatGPTConfig:
    """Configuration for OpenAI ChatGPT API calls."""
    max_tokens: int = 1000
    temperature: float = 0.3


def query_chatGPT(customized_input, model="gpt-3.5-turbo", config=None):
    if config is None:
        config = ChatGPTConfig()
    message = [{"role": "user", "content": customized_input}]

    response = openai.chat.completions.create(
        model=model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        messages=message,
    )

    return response.choices[0].message.content

def query_chatGPT4(customized_input):
    return query_chatGPT(customized_input, "gpt-4")


def ask_chatGPT(prompt_text):
    response = query_chatGPT(prompt_text)
    return response


def ask_chatGPT4(prompt_text):
    response = query_chatGPT4(prompt_text)
    return response

def find_similar_predicates(query_json_cur_clean, ALL_predicates):
    current_predicates = query_json_cur_clean['message']['query_graph']['edges']['e1']['predicates']
    output = ask_chatGPT4("The predicates in the KG are: " + ','.join(ALL_predicates) + ". The predicates in the current query are: " + ','.join(current_predicates) + ". What predicates are similar to the predicates in the current query?")
    return(output)

def find_similar_category(query_json_cur_clean, ALL_categories):
    current_predicates1 = query_json_cur_clean['message']['query_graph']['nodes']['n0']['categories']
    current_predicates2 = query_json_cur_clean['message']['query_graph']['nodes']['n1']['categories']
    output = ask_chatGPT4("The categories in the KG are: " + ','.join(ALL_categories) + ". The category in the current query are: " + ','.join(current_predicates1 + current_predicates2) + ". What categories are similar to the categories in the current query?")
    return(output)

def load_translator_resources():
    """
    Load the necessary resources for the Translator.

    Returns
    -------
    TranslatorResources
        Container with ``api_names``, ``meta_kg``, and ``api_predicates``.
    """
    from .translator_resources import TranslatorResources
    return TranslatorResources.load()




def get_similar_category(query_json_cur_clean, KG_category):
    similar_category_text = find_similar_category(query_json_cur_clean, KG_category)
    words = similar_category_text.split(' ')
    similar_category = []
    for word in words:
        if word.startswith('biolink:') :
            potential_similar_category = word.strip(',').strip(')')
            if potential_similar_category in KG_category:
                similar_category.append(potential_similar_category)

    for category in query_json_cur_clean['message']['query_graph']['nodes']['n0']['categories']:
        if category in KG_category:
            similar_category.append(category)

    for category in query_json_cur_clean['message']['query_graph']['nodes']['n1']['categories']:
        if category in KG_category:
            similar_category.append(category)

    similar_category = similar_category + KG_category

    return similar_category

def get_similar_predicate(query_json_cur_clean, All_predicates):
    similar_predicate_text = find_similar_predicates(query_json_cur_clean, All_predicates)
    similar_predicate_text
    lines = similar_predicate_text.split('\n')
    words = []
    for line in lines:
        cur_words = line.split(' ')
        words = words + cur_words
    similar_predicate = []
    for word in words:
        if word.startswith('biolink:') :
            similar_predicate.append(word)

    for predicate in query_json_cur_clean['message']['query_graph']['edges']['e1']['predicates']:
        similar_predicate.append(predicate)

    similar_predicate = list(set(similar_predicate))

    similar_predicate
    return similar_predicate
