import requests
import json
import pandas as pd


def find_link(name, use_new_url=True):
    #pre = "https://dev.smart-api.info/api/metakg/consolidated?size=2000&q=%28api.x-translator.component%3AKP+AND+api.name%3A" # This works for the previous version
    if use_new_url:
        pre = "https://smart-api.info/api/metakg?size=5000&q=(api.x-translator.component:KP+AND+api.name:"
        end = ")&facet_size=300&aggs=object.raw,subject.raw"
    else:
        pre = "https://smart-api.info/api/metakg/consolidated?size=5000&q=%28api.x-translator.component%3AKP+AND+api.name%3A" 
        end = "%5C%28Trapi+v1.5.0%5C%29%29"
    name = name.replace(' - ', ' ')
    if '(Trapi v1.5.0)' in name:
        url = pre
        name_raw = name.split("(")[0]
        words = name_raw.split(" ")
    
        # TODO: replace '(Trapi v1.5.0)' with '\(Trapi+v1.5.0\)'
        length = len(words)
        if length == 1:
            url = url + words[0] + end
        else:
            for i in range(0,length-1):
                url = url + words[i] + "+"
            url = url+words[length-1]+end
    else:
        words = name.split(" ")
        url = pre
        length = len(words)
        
        for i in range(0,length-1):
            url = url + words[i] + "+"

        url = url+words[length-1]
        if use_new_url:
            url += end
        else:
            url = url+"%29"
    return url


def get_KP_metadata(APInames:dict[str, str], use_new_url=True) -> pd.DataFrame:
    '''
    This function is used to get the metadata of the KPs in the APInames dictionary.

    Parameters
    ----------
    APInames : dict
        This is the second output of `TCT.translator_kpinfo.get_translator_kpinfo()`. This is a dict of API name to API URL.

    Returns
    -------
    metaKG : pandas.DataFrame
        This is a dataframe that represents the meta KG for the KPs in the APInames input - columns include [TODO].

    Examples
    --------
    >>> metaKG = get_KP_metadata(APInames) 
    >>> All_predicates = list(set(metaKG['Predicate']))
    All_categories = list((set(list(set(metaKG['Subject']))+list(set(metaKG['Object'])))))
    '''

    result_df = pd.DataFrame()
    API_list = []
    Predicate_list = []
    subject_list = []
    object_list = []
    url_list = []
    #for KP in KPnames:
    for KP in APInames.keys():
        json_text ={}
        if KP == "RTX KG2 - TRAPI 1.5.0": 
            text =requests.get("https://smart-api.info/api/metakg/consolidated?size=20&q=%28api.x-translator.component%3AKP+AND+api.name%3ARTX+KG2+%5C-+TRAPI+1%5C.4%5C.0%29").text  # This works for the previous version
            json_text = json.loads(text)
        else:
            text = requests.get(find_link(KP, use_new_url=use_new_url)).text
            json_text = json.loads(text)
            if 'hits' not in json_text:
                if use_new_url:
                    #print(KP, '- no hits found in new metakg URL, trying old URL pattern')
                    text = requests.get(find_link(KP, use_new_url=False)).text
                    json_text = json.loads(text)
                else:
                    print(KP, '- no hits found')
                    continue
        for i in (json_text['hits']):
            Predicate_list.append("biolink:"+i['_id'].split("-")[1])
            API_list.append(KP)
            subject_list.append('biolink:'+i['_id'].split("-")[0])
            object_list.append('biolink:'+i['_id'].split("-")[2])
            url_list.append(APInames[KP])

    result_df = pd.DataFrame({ 'API': API_list, 'Predicate': Predicate_list, "Subject":subject_list, "Object":object_list, "URL":url_list})
    
    return(result_df)


def add_new_API_for_query(APInames:dict[str, str], metaKG:pd.DataFrame, newAPIname:str, newAPIurl:str, newAPIpredicate:str, newAPIsubject:str, newAPIobject:str):
    '''
    This function is used to add a new API beyond the current list of APIs for query

    Parameters
    ----------
    APInames : dict
        This is the second output of `TCT.translator_kpinfo.get_translator_kpinfo()`.

    metaKG : pandas.DataFrame
        This is the output of `get_kp_metadata`.

    newAPIname : str

    newAPIurl : str

    newAPIpredicate : str

    newAPIsubject : str

    newAPIobject : str


    Returns
    -------

    Examples
    --------
    >>> APInames, metaKG = add_new_API_for_query(APInames, metaKG, "BigGIM_BMG", "http://127.0.0.1:8000/find_path_by_predicate", "Gene-physically_interacts_with-gene", "Gene", "Gene")

    '''
    APInames[newAPIname] = newAPIurl

    new_row = pd.DataFrame({"API":newAPIname,
                            "Predicate":newAPIpredicate,
                            "Subject":newAPIsubject, "Object":newAPIobject,
                            "URL":newAPIurl}, index=[0])
    metaKG = pd.concat([metaKG, new_row], ignore_index=True)
    return APInames, metaKG


def add_plover_API(APInames:dict[str, str], metaKG:pd.DataFrame) -> tuple[dict[str, str], pd.DataFrame]:
    '''
    This function is used to add the Plover APIs developed by the CATRAX team to the APInames and metaKG.

    Current APIs include :
    CATRAX BigGIM DrugResponse Performance Phase, 
    CATRAX Pharmacogenomics, 
    Clinical Trials, 
    Drug Approvals, 
    Multiomics, 
    Microbiome, 
    and RTX KG2.

    If an API endpoint is not available (i.e. returns a non-200 return code), then the API will not be included.

    Parameters
    ----------
    APInames : dict
        This is the second output of `TCT.translator_kpinfo.get_translator_kpinfo()`. This is a dict of API name to API URL.

    metaKG : pandas.DataFrame
        This is the output of `get_kp_metadata`.

    Examples
    --------
    >>> APInames, metaKG = add_plover_API(APInames, metaKG)
    '''
    import requests
    CI_URL_PREFIX = "https://multiomics.ci.transltr.io/"
    DEV_URL_PREFIX = "https://multiomics.rtx.ai:9990/"
    url = CI_URL_PREFIX + 'BigGIM_DrugResponse_PerformancePhase/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'BigGIM_DrugResponse_PerformancePhase/meta_knowledge_graph'
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "CATRAX BigGIM DrugResponse Performance Phase KP - TRAPI 1.5.0", 
                                                         CI_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase/query", 
                                                         data["edges"][i]['predicate'], 
                                                         data["edges"][i]['subject'], 
                                                         data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "CATRAX BigGIM DrugResponse Performance Phase KP - TRAPI 1.5.0", 
                                                             DEV_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase/query", 
                                                             data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase and " + DEV_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase. Status code:", response.status_code)


    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "BigGIM_DrugResponse_PerformancePhase")


    url = CI_URL_PREFIX + 'PharmacogenomicsKG/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'PharmacogenomicsKG/meta_knowledge_graph'
    try: 
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "CATRAX Pharmacogenomics KP - TRAPI 1.5.0", CI_URL_PREFIX + "PharmacogenomicsKG/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "CATRAX Pharmacogenomics KP - TRAPI 1.5.0", DEV_URL_PREFIX + "PharmacogenomicsKG/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "PharmacogenomicsKG and " + DEV_URL_PREFIX + "PharmacogenomicsKG. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "PharmacogenomicsKG. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "PharmacogenomicsKG")

    
    url = CI_URL_PREFIX + 'ctkp/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'ctkp/meta_knowledge_graph'
    
    try: 
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Clinical Trials KP - TRAPI 1.5.0", CI_URL_PREFIX + "ctkp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Clinical Trials KP - TRAPI 1.5.0", DEV_URL_PREFIX + "ctkp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "ctkp and " + DEV_URL_PREFIX + "ctkp. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "ctkp. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "ctkp")

    url = CI_URL_PREFIX + 'dakp/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'dakp/meta_knowledge_graph'

    #url = 'https://multiomics.rtx.ai:9990/dakp/meta_knowledge_graph'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Drug Approvals KP - TRAPI 1.5.0", CI_URL_PREFIX + "dakp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Drug Approvals KP - TRAPI 1.5.0", DEV_URL_PREFIX + "dakp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "dakp and " + DEV_URL_PREFIX + "dakp. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "dakp. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "dakp")
    

    url = CI_URL_PREFIX + 'mokp/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'mokp/meta_knowledge_graph'
    #url = 'https://multiomics.rtx.ai:9990/mokp/meta_knowledge_graph'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Multiomics KP - TRAPI 1.5.0", CI_URL_PREFIX + "mokp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Multiomics KP - TRAPI 1.5.0", DEV_URL_PREFIX + "mokp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "mokp and " + DEV_URL_PREFIX + "mokp. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "mokp. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "mokp")
    
    url = CI_URL_PREFIX + 'mbkp/meta_knowledge_graph'
    url_dev = DEV_URL_PREFIX + 'mbkp/meta_knowledge_graph'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Microbiome KP - TRAPI 1.5.0", CI_URL_PREFIX + "mbkp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        elif response.status_code == 404:
            # Try the dev URL if the CI URL returns a 404
            response_dev = requests.get(url_dev, timeout=5)
            if response_dev.status_code == 200:
                data = response_dev.json()
                for i in range(len(data["edges"])):
                    APInames, metaKG = add_new_API_for_query(APInames, metaKG, "Microbiome KP - TRAPI 1.5.0", DEV_URL_PREFIX + "mbkp/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
            else:
                print("Warning: Failed to retrieve data from both the " + CI_URL_PREFIX + "mbkp and " + DEV_URL_PREFIX + "mbkp. Status codes:", response.status_code, response_dev.status_code)
        else:
            print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "mbkp. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the " + CI_URL_PREFIX + "mbkp")
    

    url = 'https://kg2cploverdb.ci.transltr.io/meta_knowledge_graph'
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for i in range(len(data["edges"])):
                APInames, metaKG = add_new_API_for_query(APInames, metaKG, "RTX KG2 - TRAPI 1.5.0", "https://kg2cploverdb.ci.transltr.io/kg2c/query", data["edges"][i]['predicate'], data["edges"][i]['subject'], data["edges"][i]['object'])
        else:
            print("Warning: Failed to retrieve data from the https://kg2cploverdb.ci.transltr.io. Status code:", response.status_code)
    except requests.exceptions.RequestException:
        print("Warning: Failed to retrieve data from the https://kg2cploverdb.ci.transltr.io")

    return APInames, metaKG

def load_translator_resources(use_new_metakg_url=False):
    """
    Load the necessary resources for the Translator.

    Params
    ------
    use_new_metakg_url
        If True, this uses https://smart-api.info/api/metakg. If False, this uses https://smart-api.info/api/metakg/consolidated?

    Returns
    -------
    APInames
    metaKG
    Translator_KP_info
    """
    from .translator_kpinfo import get_translator_kp_info
    Translator_KP_info, APInames = get_translator_kp_info()
    metaKG = get_KP_metadata(APInames, use_new_url=use_new_metakg_url)
    
    APInames, metaKG = add_plover_API(APInames, metaKG)
    metaKG = metaKG[metaKG['Predicate'] != 'biolink:rdfs:subClassOf']

    return  APInames, metaKG, Translator_KP_info
