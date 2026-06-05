# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **`results.py`** — result types with built-in NetworkX graph conversion:
  - `GraphConvertible` protocol defining `.to_networkx()` interface
  - `KnowledgeGraph` wrapping raw TRAPI edges with dict-like access, `.parse()`, `.to_dataframe()`, `.to_networkx()`
  - `ParsedKnowledgeGraph` with `.rank()` and `.to_networkx()`
  - `NeighborhoodResult` and `PathResult` dataclasses returned by finder functions
  - `dataframe_to_graph()` for converting edge DataFrames to `nx.MultiDiGraph`
- **`visualization.py`** — Extracted all visualization from `TCT.py` (~574 lines):
  - `HeatmapConfig` dataclass, `plot_heatmap()`, `plot_heatmap_ui()`
  - `visulization_one_hop_ranking()`, `visulization_one_hop_ranking_input_as_list()`
  - `plot_path_bar()`, `plot_graph_by_predicates()`, `plot_graph_by_infores()`, `plot_graph_by_API()`
  - `visulize_path()` (Cytoscape), `visualize_neighborhood_graph()` (PyVis)
- **`translator_resources.py`** — `TranslatorResources` dataclass bundling `(api_names, meta_kg, api_predicates)`:
  - `.load()` class method, `.from_tuple()`, `.as_tuple()` for backward compatibility
  - `.filter()` and `.rebuild_predicates()` methods
- **`attribute_extraction.py`** — Structured extraction from TRAPI edge attributes:
  - `extract_publications()`, `extract_supporting_text()`, `extract_confidence_scores()`
  - `extract_rich_edge_attributes()` composite extractor
  - Recursive handling of nested `biolink:has_supporting_study_result` with depth guard
- **`HopSpec`** dataclass and `build_multi_hop_query()` in `trapi.py` for multi-hop TRAPI queries
- `include_attributes` flag on `KnowledgeGraph.to_networkx()` for rich edge metadata
- `edge_attributes` and `multi_hop_query` example notebooks
- Comprehensive test suite (~5,500 lines) with 95% coverage threshold:
  - `test_results.py`, `test_attribute_extraction.py`, `test_trapi.py`, `test_backward_compat.py`
  - `test_tct_pure.py`, `test_tct_openai.py`, `test_tct_visualization.py`
  - `test_translator_resources.py`, `test_translator_metakg.py`, `test_translator_query.py`
  - `test_translator_kpinfo.py`, `test_server_tools.py`, `test_coverage_gaps.py`
  - Shared fixtures in `conftest.py`

### Changed
- **`TCT.py` refactored** — reduced by ~1,500 lines; visualization, result classes, and resource management extracted to dedicated modules. Core KG exploration, ranking, and ChatGPT functions remain.
- All public functions accepting `APInames/metaKG/API_predicates` now accept `resources=TranslatorResources(...)` with backward-compatible deprecation warnings via `_resolve_resources()`
- `server.py` updated for new module architecture
- `translator_kpinfo.py`, `translator_metakg.py`, `translator_query.py`, `node_normalizer.py` refactored for consistency
- `__init__.py` updated to export result classes, `TranslatorResources`, `HopSpec`, and attribute extraction functions
- `pyproject.toml`: added `nbconvert`, `ipykernel`, `notebook` dev deps; coverage threshold set to 95%
- Existing notebooks re-modernized after the upstream merge to use the result-class API (`Neighborhood_finder`/`Path_finder` → result objects) and `TranslatorResources.load()`/`.filter()`

### Merged from upstream (NCATSTranslator/main)
- New pipeline modules (with tests added to keep the 95% coverage gate):
  - `TCT_pathfinder.py` — multi-hop pathfinding: constraint-aware query builders, ARAGORN/ARAX endpoint wrappers, `pathfinder()` and `parse_results_for_pathfinder()`
  - `TCT_neighborhood_finder.py` — `neighborhood_finder()` and `parse_results_for_neighborhood_finder()`
  - `kg_loader.py` — KG2 CSV/JSONL import with NetworkX/igraph conversion and sparse-matrix utilities
  - `graph_downloader.py` — cached download/load of compressed (`.tar.zst`) graphs
- New dependencies: `igraph`, `zstandard`, `scipy`
- `trapi.build_query` now defaults to `return_json=False`; `query()` raises `TypeError` on a string argument
- `translator_query` gains `format_query_json()` and `build_attribute_constraint()` (used by the new pipeline modules)
- `name_resolver`: `synonyms()` now accepts a list of CURIEs; new `batch_synonyms()` for POST-based batch lookup
- `node_normalizer.get_normalized_nodes()` guards empty input and handles single-node responses
- `translator_metakg`: Plover endpoints are fetched with per-endpoint error handling; `find_link`/`get_KP_metadata` use the new SmartAPI metakg URL (result limit raised to 5000) with fallback (`use_new_url`)
- Visualization: `visualize_neighborhood_graph(output_filename_prefix=...)`; empty-result guards in `visulization_one_hop_ranking`/`plot_heatmap`
- New upstream notebooks: `Compare_pathfinder`, `Pathfinder_new`, `metakg_tests`, `queries_with_constraints`, `individual_endpoint_overview`
- Corrected spelling `Neighborhood_finder` is now canonical; `Neiborhood_finder` remains as a deprecated alias
- Fixed a latent argument-passing bug in `kg_loader.load_kg2`/`load_kg2_networkx`/`load_kg2_igraph`
- Follow-up: the branch's `Neighborhood_finder`/`Path_finder` (returning result classes) and upstream's `TCT_neighborhood_finder`/`TCT_pathfinder` modules currently coexist; unifying them so the upstream pipelines return result classes is left as future work

## [0.1.6] - 2025-12-09

### Added
- Node Normalizer and Name Resolver test suite (PR #17)
- `TranslatorNode.from_dict()` for centralizing NameRes response parsing
- Examples for GeneProtein and DrugChemical conflation
- Node Annotator module and tests (PR #21)
- `raise_for_status()` replacing manual HTTP status checks

### Changed
- NodeNorm/NameRes endpoints switched from Translator Prod to CI

### Removed
- `coverage.xml` from repository (PR #16)

## [0.1.5] - 2025-11-13

### Added
- Network visualization module (`TCT_visualization`)
- `ID_convert_to_preferred_name_nodeNormalizer` in `node_normalizer`
- `Test_neighborhood_vis` notebook

### Changed
- Revised Neighborhood finder to use CURIE IDs instead of node names (PR #24)
- Updated neighborhood finder and connection finder notebooks

## [0.1.4] - 2025-09-22

### Added
- MCP server via FastMCP (`server.py`, `main.py`) with `mcp_error_handler` decorator (PR #13)
- `tct-server` console entry point
- Name resolver documentation for additional `lookup()` arguments (PR #23)

### Changed
- Migrated from setuptools to UV + hatchling (PR #12)
- Added Makefile, GitHub Actions CI, Ruff linting, codespell, and test infrastructure
- Path finder notebook revised

## [0.1.3] - 2025-08-05

### Changed
- Revised connection finder, pathfinder, and overview notebooks
- Updated MetaKG link in `translator_metakg`
- Revised README documentation

## [0.1.2] - 2025-07-23

### Added
- `translator_query` module for multi-API query orchestration
- `translator_kpinfo` module for Knowledge Provider info
- Sphinx documentation for new modules

### Changed
- Reimplemented pathfinder and neighborhood explorer
- Revised network finder, connection finder notebooks
- Updated docstrings in `translator_node`

## [0.1.1] - 2025-06-30

### Added
- Node normalizer module with synonyms support
- Translator components documentation and introduction
- TRAPI filtering
- Batch lookup function for Name Resolver
- `name_resolver_lookup` notebook

### Changed
- Refined MetaKG fetching and KG connection logic
- Revised path visualization

## [0.1.0] - 2024-05-29

### Added
- Initial packaged release with `setup.py`
- Core `TCT.py` module with KG exploration functions
- Connection finder, path finder, network finder notebooks
- ChatGPT integration for question-to-TRAPI conversion
- `connecting_userAPI` notebook
- 3-hop pathfinder notebook

[Unreleased]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/NCATSTranslator/Translator_component_toolkit/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NCATSTranslator/Translator_component_toolkit/releases/tag/v0.1.0
