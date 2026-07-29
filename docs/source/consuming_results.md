Consuming results
=================

This page documents the stable contract for building tools (dashboards, viewers,
exports) on top of TCT finder results. Prefer these named attributes and helpers
over unpacking results as tuples, which is deprecated.

## Finder return objects

`Neighborhood_finder()` returns a `NeighborhoodResult`:

| Field | Type | Description |
| --- | --- | --- |
| `input_node_id` | `str` | The resolved input CURIE |
| `knowledge_graph` | `KnowledgeGraph` | Raw TRAPI edges, dict-like |
| `parsed` | `ParsedKnowledgeGraph` | Edges consolidated by subject-object pair |
| `ranked` | `pandas.DataFrame` | Ranking of output nodes |

`Path_finder()` returns a `PathResult` with `paths` (a `DataFrame` of bridging
nodes), `node1_id`, `node2_id`, and per-hop `knowledge_graph1`/`knowledge_graph2`,
`parsed1`/`parsed2`, `ranked1`/`ranked2`.

```python
nb = TCT.Neighborhood_finder("MONDO:0008170",
                             node2_categories=["biolink:Drug"],
                             resources=resources)
G = nb.knowledge_graph.to_networkx(resolve_names=True, include_attributes=True)
```

Pass `verbose=True` to either finder to restore progress prints (they are silent
by default). A CURIE that cannot be normalized raises `ValueError`.

## `to_networkx()` attribute schema

`KnowledgeGraph.to_networkx(resolve_names=False, include_attributes=False)` returns
an `nx.MultiDiGraph`. `NeighborhoodResult.to_networkx()` and
`PathResult.to_networkx()` accept the same two flags and delegate to the underlying
knowledge graph(s).

**Node attributes** (only when `resolve_names=True`):

| Attribute | Type | Description |
| --- | --- | --- |
| `label` | `str` | Preferred name (falls back to the CURIE) |
| `categories` | `list[str] \| None` | Biolink type list, most-specific first |

Node keys are CURIEs. For a single primary category, take `categories[0]`.

**Edge attributes** (always):

| Attribute | Type |
| --- | --- |
| `key` | `str` (edge id) |
| `predicate` | `str` |
| `primary_sources` | `list[str]` |
| `aggregator_sources` | `list[str]` |

With `include_attributes=True`, each edge additionally carries `publications`
(`list[str]`, PubMed ids normalized to `PMID:<n>`), `supporting_text`
(`list[str]`), and `confidence_scores` (`dict[str, float]`).

`ParsedKnowledgeGraph.to_networkx()` emits one edge per unique predicate per pair
with only a `predicate` edge attribute (no sources or rich attributes).

## Tables

`knowledge_graph.to_dataframe()` returns a `DataFrame` with columns `Subject`,
`Object`, `Predicate` (one row per raw edge).

The `ranked` DataFrame has columns: `output_node`, `Name`, `Num_of_primary_infores`,
`type_of_nodes` (`"subject"`/`"object"`), and `unique_predicates` (a list per row),
sorted descending by `Num_of_primary_infores`.

Any edge table (including a MetaKG DataFrame, columns `API`, `Subject`, `Object`,
`Predicate`, `URL`) can be converted with `dataframe_to_graph(df, source_col=...,
target_col=..., edge_attrs=[...])`.

## Enriching edges directly

To pull structured metadata from an arbitrary TRAPI edge's `attributes` list:

```python
from TCT.attribute_extraction import extract_rich_edge_attributes
rich = extract_rich_edge_attributes(edge["attributes"])
# {"publications": [...], "supporting_text": [...], "confidence_scores": {...}}
```
