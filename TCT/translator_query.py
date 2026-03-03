import requests
from copy import deepcopy
import pandas
from TCT import translator_metakg
from TCT import translator_kpinfo
from TCT.results import KnowledgeGraph
from TCT.translator_resources import TranslatorResources

def get_translator_API_predicates() -> TranslatorResources:
    '''
    Get the predicates supported by each API.

    Returns
    --------
    TranslatorResources
        A container with ``api_names``, ``meta_kg``, and ``api_predicates``.

    Examples
    --------
    >>> resources = get_translator_API_predicates()
    '''
    Translator_KP_info,APInames= translator_kpinfo.get_translator_kp_info()
    print(len(Translator_KP_info))
    # Step 2: Get metaKG and all predicates from Translator APIs through the SmartAPI system
    metaKG = translator_metakg.get_KP_metadata(APInames)
    print(metaKG.shape)
    # Add metaKG from Plover API based KG resources
    APInames,metaKG = translator_metakg.add_plover_API(APInames, metaKG)
    print(metaKG.shape)
    # Step 3: list metaKG information
    # All_predicates = list(set(metaKG['Predicate']))  # Unused variable
    # All_categories = list((set(list(set(metaKG['Subject']))+list(set(metaKG['Object'])))))  # Unused variable
    API_withMetaKG = list(set(metaKG['API']))

    # generate a dictionary of API and its predicates
    API_predicates = {}
    for api in API_withMetaKG:
        API_predicates[api] = list(set(metaKG[metaKG['API'] == api]['Predicate']))

    return TranslatorResources(api_names=APInames, meta_kg=metaKG, api_predicates=API_predicates)

def optimize_query_json(query_json, API_name_cur, API_predicates):
    '''
    Optimize the query JSON by removing predicates that are not supported by the selected APIs.

    Parameters
    ----------
    query_json1 : str
        a query in TRAPI 1.5.0 format
    API_name_cur : str
        the name of the API to query
    API_predicates : dict
        a dictionary of API names and their predicates

    Returns
    --------
    A modified query JSON with only the predicates supported by the selected APIs.
    
    Examples
    --------
    >>> 
    '''
    query_json_cur = query_json.copy()  # copy the query_json to avoid modifying the original query_json
    # Get the list of APIs that support the predicates in the query
    shared_predicates = list(set(API_predicates[API_name_cur]).intersection(query_json_cur['message']['query_graph']['edges']['e00']['predicates'] ))
    
    if len(shared_predicates) > 0:
        query_json_cur['message']['query_graph']['edges']['e00']['predicates'] = shared_predicates
        #print(API_name_cur + ": Predicates optimized to: " + str(shared_predicates))
    else:
        #print(API_name_cur + ": No shared predicates found. Using all predicates in the query.")
        # If no shared predicates, keep the original predicates
        query_json_cur['message']['query_graph']['edges']['e00']['predicates'] = query_json_cur['message']['query_graph']['edges']['e00']['predicates']

    return query_json_cur

def query_KP(API_name_cur, query_json, resources):
    """
    Query an individual API with a TRAPI 1.5.0 query JSON,
    without modifying the original query_json.

    Parameters
    ----------
    API_name_cur : str
        Name of the API to query.
    query_json : dict
        A query in TRAPI 1.5.0 format.
    resources : TranslatorResources
        Container with ``api_names`` and ``api_predicates``.
    """
    API_url_cur = resources.api_names[API_name_cur]
    # deep‐copy so we never touch the caller’s data
    query_copy = deepcopy(query_json)
    # optimize on our private copy
    query_json_cur = optimize_query_json(query_copy, API_name_cur, resources.api_predicates)
    response = requests.post(API_url_cur, json=query_json_cur)
    if response.status_code == 200:
        result = response.json().get("message", {})
        kg = result.get("knowledge_graph", {})
        edges = kg.get("edges", {})
        if edges:
            print(f"{API_name_cur}: Success!")
            return result
        elif "knowledge_graph" in result:
            return None
            #print(f"{API_name_cur}: No result returned")
    else:
        #print(f"{API_name_cur}: Warning Code: {response.status_code}")
        return None

def parallel_api_query(query_json, select_APIs, resources, max_workers=1):
    '''
    Queries multiple APIs in parallel and merges the results into a single knowledge graph.

    Parameters
    ----------
    query_json : dict
        The query JSON to be sent to each API.
    select_APIs : list[str]
        List of API names to query.
    resources : TranslatorResources
        Container with ``api_names`` and ``api_predicates``.
    max_workers : int
        Number of parallel workers to use for querying.

    Returns
    -------
    KnowledgeGraph
        A merged knowledge graph from all successful API responses.

    Examples
    --------
    >>> result = parallel_api_query(query_json=query_json, select_APIs=sele_APIs, resources=resources, max_workers=len(sele_APIs))

    '''
    # Parallel query
    result = []
    no_results_returned = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from copy import deepcopy
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # copy the query_json for each API to avoid modifying the original query_json
        query_json_cur = deepcopy(query_json)
        future_to_url = {executor.submit(query_KP, API_name_cur, query_json_cur, resources): API_name_cur for API_name_cur in select_APIs}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                data = future.result()
                if 'knowledge_graph' in data:
                    result.append(data)
            except Exception as exc:
                no_results_returned.append(url)
                #print('%r generated an exception: %s' % (url, exc))
    
    included_KP_ID = []
    for i in range(0,len(result)):
        if result[i]['knowledge_graph'] is not None:
            if 'knowledge_graph' in result[i]:
                if 'edges' in result[i]['knowledge_graph']:
                    if len(result[i]['knowledge_graph']['edges']) > 0:
                        included_KP_ID.append(i)

    result_merged = {}
    for i in included_KP_ID:
        result_merged = {**result_merged, **result[i]['knowledge_graph']['edges']}

    return KnowledgeGraph(edges=result_merged)
