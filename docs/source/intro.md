Introduction
============
## What is TCT?
Translator Component Toolkit is a python library that allowing users to explore and use KGs in the Translator ecosystems.
Users can check out the key functions here: https://ncatstranslator.github.io/Translator_component_toolkit/ 

## Key features for TCT
Allowing users to select APIs, predicates according to the user's intention. <br>
Parallel and fast querying of the selected APIs.<br>
Providing reproducible results by setting constraints.<br>
Allowing testing whether a user defined API follows a [TRAPI](https://github.com/NCATSTranslator/ReasonerAPI) standard or not. <br>
Faciliting to explore knowledge graphs from both Translator ecosystem and user defined APIs.<br>
Connecting large language models to convert user's questions into TRAPI queries. <br>

### Contributing
TCT is a tool that helps to explore knowledge graphs developed in the Biomedical Data Translator Consortium. Consortium members and external contributors are encouraged to submit issues and pull requests. 

### Contact info
Guangrong Qin, guangrong.qin@isbscience.org

## How to use TCT
### Install Requirements

To install TCT as a python library, you can install the library using `pip install TCT` from the command line. 

The TCT is continuously updated, if you would like to use the latest functions, you can also  clone this most recent github repository (https://github.com/NCATSTranslator/Translator_component_toolkit/tree/main), 
`git clone https://github.com/NCATSTranslator/Translator_component_toolkit.git`
`cd Translator_component_toolkit`
`pip install -e .`


### Please follow the example notebooks (four utilities) below to explore the Translator APIs.

#### KG overview
Explore different KGs **[KG overview](https://github.com/gloriachin/Translator_component_toolkit/tree/main/notebooks/overview_of_KGs.ipynb)**

#### Neighborhood finder
Example notebook for **[NeighborhoodFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Neighborhood_finder.ipynb)**

#### Path finder
Example notebook for **[PathFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Path_finder.ipynb)**

#### Network finder
Example notebook for **[NetworkFinder](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Neighborhood_finder_multiple_nodes.ipynb)**

#### Connecting to a user's API
API should be developed following the standard from [TRAPI](https://github.com/NCATSTranslator/ReasonerAPI). <br>
An example notebook for add a user's API can be found [here](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Connecting_userAPI.ipynb).<br>
**Note: It does not work if no user' API is established**<br>

## Key Translator components
Connecting to key Translator components can be found [here](./components)

