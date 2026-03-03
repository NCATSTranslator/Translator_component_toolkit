
# used May 30, 2025

import requests
import json
import pandas as pd

"""This is the root URL for the resource."""
URL = 'https://smart-api.info/api/query?q=tags.name:translator'


def _build_query_url(server: dict) -> str:
    """Build a query URL from a SmartAPI server entry."""
    url = server['url']
    # Check for ARS-specific URLs
    ars_urls = {
        'https://ars-prod.transltr.io',
        'https://ars.ci.transltr.io',
        'https://ars.test.transltr.io',
    }
    if url in ars_urls:
        return url + '/ars/api/submit/'
    if url.endswith('/'):
        return url + 'query/'
    return url + '/query/'


def get_translator_kp_info() -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Get the SmartAPI Translator KP info from the smart-api.info API.
    Returns a DataFrame with the SmartAPI Translator KP info.

    Returns
    -------
    smartapi_df : pandas.DataFrame
        Dataframe containing information about the APIS [TODO]

    API_names : dict
        dict of API names to URLs


    Examples
    --------
    >>> Translator_KP_info, APInames = get_translator_kp_info()
    >>> print(Translator_KP_info.head())
    """
    # Get x-bte smartapi specs
    url = "https://smart-api.info/api/query?q=tags.name:translator AND tags.name:trapi&size=1000&sort=_seq_no&raw=1&fields=paths,servers,tags,components.x-bte*,info,_meta"
    response = requests.get(url)
    try:
        response.raise_for_status()
    except Exception:
        print(f"error downloading smartapi specs: {response.status_code}")
        exit()

    content = json.loads(response.content)
    smartapis = content["hits"]

    id_list = []
    title_list = []
    prod_url_list = []
    ci_url_list = []
    test_url_list = []
    for api in smartapis:
        
        
        ci_found = False
        test_found = False
        prod_found = False
        for i in range(len(api['servers'])):
            
            server = api['servers'][i]
            if 'x-maturity' not in server:
                print(f"Skipping server without x-maturity: {server}")
                
            else:
                if server['x-maturity'] == 'production':
                    prod_url = _build_query_url(server)
                    prod_found = True

                if server['x-maturity'] == 'staging' or server['x-maturity'] == 'development':
                    ci_url = _build_query_url(server)
                    ci_found = True

                if server['x-maturity'] == 'testing':
                    test_url = _build_query_url(server)
                    test_found = True

        if not (prod_found or ci_found or test_found):
            print(api['info']['title'])
            print(f"Skipping server without production, staging or testing: {server}")
        else:
            id_list.append('https://smart-api.info/ui/'+api['_id'])
            title_list.append(api['info']['title'])
            if prod_found:
                prod_url_list.append(prod_url)
            else:
                prod_url_list.append(None)

            if ci_found:
                ci_url_list.append(ci_url)
            else:
                ci_url_list.append(None)
            if test_found:
                test_url_list.append(test_url)
            else:
                test_url_list.append(None)
                
    # write all the smartapis to a dataframe

    smartapi_df = pd.DataFrame({
        'id': id_list,
        'title': title_list,
        'prod_url': prod_url_list,
        'ci_url': ci_url_list,
        'test_url': test_url_list,
    })
    
    API_names = {}
    for i in range(len(smartapi_df)):
        if prod_url_list[i] is not None:
            #API_names[smartapi_df['title'][i]] = smartapi_df['prod_url'][i] + 'query/'
            API_names[smartapi_df['title'].values[i]] = prod_url_list[i]
        else:
            API_names[smartapi_df['title'].values[i]] = ci_url_list[i] 
    return smartapi_df, API_names
