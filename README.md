Introduction
==================================

## What is TCT?
Translator Component Toolkit (TCT) is a Python library for exploring and using knowledge graphs in the Translator ecosystem.
Users can check out the key function documentations here: [https://ncatstranslator.github.io/Translator_component_toolkit/](https://ncatstranslator.github.io/Translator_component_toolkit/) 

[TCT Github repo](https://github.com/NCATSTranslator/Translator_component_toolkit/tree/main)

## Key features for TCT
Allowing users to select APIs, predicates according to the user's intention. <br>
Parallel and fast querying of the selected APIs.<br>
Providing reproducible results by setting constraints.<br>
Faciliting to explore knowledge graphs from both Translator ecosystem and user defined APIs.<br>
Connecting large language models to convert user's questions into TRAPI queries. <br>
Find the identifier given a name using name resolver<br>
Annotate a node using node annotator<br>
Explore knowledge graphs in Translator<br>
Find neighbors in the Translator KGs for a given node <br>
Find paths between node A and node B in the Translator KG <br>
Find a subnetwork given a list of nodes in the Translator KG <br>
Developer-friendly wrappers for resolving labels/CURIEs, caching Translator resources, and returning parsed finder results <br>
Connecting user's API with Translator API <br>
*Note: Visualization capabilities (pyvis, matplotlib, seaborn) can be installed separately via the `vision` extra.*


## How to use TCT

### Install Requirements

To install TCT as a python library:

```bash
pip install TCT
# TCT is in development, to get the most recent update, user can install it through the github repo
```

**This is the recommended approach for a minimal installation.**

The minimal installation includes both the Python library and the `tct`
command-line interface. Install the optional MCP dependencies when an agent or
MCP client will run TCT as a server:

```bash
pip install "TCT[mcp]"
```

Visualization support is optional. Install it with the `vision` extra when you need the plotting and graph-rendering utilities:

```bash
pip install "TCT[vision]"
```

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

### Service environment

TCT uses production service URLs by default. Select CI for services that have a
CI deployment either in Python:

```python
import TCT

TCT.configure(environment="ci")
```

or when starting a process such as the MCP server:

```bash
TCT_ENVIRONMENT=ci tct-server
```

Services without a separate CI deployment continue to use their shared URL.
For local testing, individual known services can be replaced explicitly:

```python
TCT.configure(
    environment="ci",
    overrides={"arax": "http://localhost:8080/query"},
)
```

To include visualization support in the UV environment:

```bash
uv sync --extra vision
```

To develop or run the MCP server from a source checkout:

```bash
uv sync --extra mcp
```

To observe CLI and MCP tool invocations with Langfuse:

```bash
uv sync --extra mcp --extra langfuse
```

## Python, CLI, and MCP interfaces

TCT exposes one curated set of well-documented operations through three
interfaces:

| Interface | Intended use | Starting point |
| --- | --- | --- |
| Python | Application and notebook development | `import TCT` |
| CLI | Shell scripts, exploration, and agent command execution | `tct --help` |
| MCP | Tool discovery and invocation by MCP clients | `tct-server` |

The CLI and MCP server are generated from the same functions in
`TCT.interfaces.tools`. Function names, signatures, annotations, defaults, and
docstrings therefore provide the common tool contract. The MCP server remains
available from the existing `tct-server` command and from the compatibility
imports in `TCT.server`.

### Explore the CLI

Start at the root help, then ask for help on any listed command:

```bash
tct --help

\\\\
tct name-lookup --help
tct normalize-nodes --help
```

Commands use kebab-case names and long options. List options accept one or
more space-separated values, structured options accept JSON, and boolean
options support both `--option` and `--no-option`. Results are written as JSON
so they can be inspected directly or piped to another program. Common TCT
results such as dataclasses, mappings, collections, and tables are converted
recursively. Tool failures are written concisely to standard error and return
a nonzero exit status.

```bash
tct name-lookup --query aspirin
tct normalize-nodes --query CHEBI:15365 CHEBI:6801 --no-conflate
```

See [EXAMPLES.md](EXAMPLES.md) for CLI discovery, structured inputs, finder
commands, Python use, and MCP client configuration.

### Run the MCP server

After installing the `mcp` extra, start the stdio server with:

```bash
tct-server
```

MCP clients discover the same tool names, descriptions, input types, required
parameters, and defaults shown by the CLI. A typical client configuration is:

```json
{
  "mcpServers": {
    "tct": {
      "command": "tct-server"
    }
  }
}
```

When running from a source checkout, run `uv sync --extra mcp` first and use
`uv run tct-server`.

### Optional Langfuse observability

The CLI and MCP adapters can create one Langfuse `tool` observation for each
call made through their shared invocation boundary. No TCT function is
decorated: direct Python library calls remain uninstrumented and importing TCT
does not require the Langfuse SDK.

Install the optional extra and configure the standard Langfuse environment
variables:

```bash
uv sync --extra mcp --extra langfuse

export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export LANGFUSE_BASE_URL=https://cloud.langfuse.com

uv run tct name-lookup --query aspirin
uv run tct-server
```

Tracing turns on automatically when both keys are present. Set
`TCT_LANGFUSE_ENABLED=false` to disable it explicitly, or set it to `true` to
enable it when credentials are supplied by another Langfuse-supported
mechanism. `LANGFUSE_TRACING_ENVIRONMENT` can distinguish deployments such as
`ci`, `staging`, and `production` in Langfuse; it is independent of
`TCT_ENVIRONMENT`, which selects TCT service endpoints.

Observations are named `tct.tool.<tool_name>`, tagged with the `cli` or `mcp`
interface, and include normalized arguments, defaults, and successful results.
The original exception crosses the observation boundary on failure before the
CLI or MCP adapter converts it to its stable interface error. Because this can
record biomedical queries and service responses, configure Langfuse according
to the data-handling requirements of the deployment.

### Shared tool capabilities

The table uses CLI kebab-case spellings; MCP publishes the corresponding
Python names in snake_case.

| Area | Commands |
| --- | --- |
| Translator resources | `get-translator-resources`, `get-kp-info`, `get-metakg-data`, `get-api-predicates` |
| Name resolution | `name-lookup`, `get-name-synonyms`, `batch-name-lookup` |
| Node normalization | `normalize-nodes` |
| MetaKG extension | `add-custom-api-to-metakg`, `add-plover-apis-to-metakg` |
| TRAPI query preparation and execution | `optimize-query-for-api`, `query-knowledge-provider`, `parallel-query-apis` |
| Graph finding | `neighborhood-finder`, `path-finder` |
| Legacy compatibility | `trapi-query-endpoint` |

`trapi-query-endpoint` preserves the existing public tool contract but is a
legacy placeholder in this release; its underlying operation also requires a
query body that is not present in the public command signature.

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

#### Developer-friendly finder APIs
The finder notebooks above include quick-start sections using the developer-friendly `pathfinder` and `neighborhood_finder` APIs, now part of TCT's main API surface (`from TCT import query_TCT_pathfinder, neighborhood_finder`).

Use the detailed NeighborhoodFinder, PathFinder, NetworkFinder, KG overview, and visualization notebooks when you need more fine-grained endpoint selection, predicate control, raw query construction, parser workflows, or visualization setup.


#### Connecting to a user's API
API should be developed following the standard from [TRAPI](https://github.com/NCATSTranslator/ReasonerAPI). <br>
An example notebook for add a user's API can be found [here](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/Connecting_userAPI.ipynb).<br>
**Note: It does not work if no user' API is established**<br>

### Visualize the results
After each pipeline, it will generate a result file for visualization. A user can use **[the Visualization html](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/notebooks/visualize_TCT_results.html)** file to visulaize the results.

## Key Translator components
Connecting to key Translator components can be found [here](https://github.com/NCATSTranslator/Translator_component_toolkit/blob/main/TranslatorComponentsIntroduction.md)

### Contributing
TCT is a tool that helps to explore knowledge graphs developed in the Biomedical Data Translator Consortium. Consortium members and external contributors are encouraged to submit issues and pull requests. 

### Contact info
Guangrong Qin, guangrong.qin@isbscience.org
