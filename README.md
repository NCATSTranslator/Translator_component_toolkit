Introduction
==================================

## What is TCT?
Translator Component Toolkit is a python library that allowing users to explore and use KGs in the Translator ecosystem.
Users can check out the key function documentations here: https://ncatstranslator.github.io/Translator_component_toolkit/ 

## Key features for TCT
Allowing users to select APIs, predicates according to the user's intention. <br>
Parallel and fast querying of the selected APIs.<br>
Providing reproducible results by setting constraints.<br>
Allowing testing whether a user defined API follows a [TRAPI](https://github.com/NCATSTranslator/ReasonerAPI) standard or not. <br>
Faciliting to explore knowledge graphs from both Translator ecosystem and user defined APIs.<br>
Connecting large language models to convert user's questions into TRAPI queries. <br>

## How to use TCT

### Install Requirements

To install TCT as a python library:

```bash
pip install TCT
# TCT is in development, to get the most recent update, user can install it throught the github repo
```

**This the recommended approach for installation.**


#### Development Installation

The TCT is continuously updated, if you would like to use the latest functions, you can clone this repository and install it in development mode:



**Using pip: (recommended for development)**
```bash
git clone https://github.com/NCATSTranslator/Translator_component_toolkit.git
cd Translator_component_toolkit
pip install -e .
```

**Using UV :**
```bash
git clone https://github.com/NCATSTranslator/Translator_component_toolkit.git
cd Translator_component_toolkit
uv sync
```

#### Building and Deployment
**Using pip:**
- Build: `python -m build`
- Install dependencies: `pip install -e .`

**Using UV:**
- Build: `uv build`
- Install dependencies: `uv sync`
- Run in UV environment: `uv run python your_script.py`


### Please follow the example notebooks (four utilities) below to explore the Translator APIs.

#### KG overview
Explore different KGs **[KG overview](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/overview_of_KGs.ipynb)**

#### Name Resolver and Node Normalizer
Example notebook for **[Name Resolver and Node Normalizer](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/name_resolver_lookup.ipynb)**

#### Neighborhood finder
Example notebook for **[NeighborhoodFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Neighborhood_finder.ipynb)**

#### Path finder
Example notebook for **[PathFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Path_finder.ipynb)**

#### Network finder
Example notebook for **[NetworkFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Neighborhood_finder_multiple_nodes.ipynb)**


### Visulize the results
After each pipleline, it will generate a result file for visualization. A user can use **[the Visualization html](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/visulize_path_finder_results.html)** file to visulaize the results.

## Key Translator components
Connecting to key Translator components can be found [here](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/TranslatorComponentsIntroduction.md)

### Contributing
TCT is a tool that helps to explore knowledge graphs developed in the Biomedical Data Translator Consortium. Consortium members and external contributors are encouraged to submit issues and pull requests. 

### Contact info
Guangrong Qin, guangrong.qin@isbscience.org
