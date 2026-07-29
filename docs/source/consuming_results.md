Consuming results
=================

This page describes the stable contract for building things on top of TCT's
finders: dashboards, viewers, exports, or any downstream analysis.

## Quick start

```python
import TCT
from TCT.translator_resources import TranslatorResources

resources = TranslatorResources.load()

nb = TCT.Neighborhood_finder("MONDO:0008170",
                             node2_categories=["biolink:Drug"],
                             resources=resources)

nb.ranked.head()                 # ranked output nodes, as a DataFrame
G = nb.to_networkx(resolve_names=True, include_attributes=True)
```

## What the finders return

`Neighborhood_finder()` returns a `NeighborhoodResult`:

| Field | Type | Description |
| --- | --- | --- |
| `input_node_id` | `str` | The resolved input CURIE |
| `knowledge_graph` | `KnowledgeGraph` | Raw TRAPI edges, dict-like |
| `parsed` | `ParsedKnowledgeGraph` | Edges consolidated by subject-object pair |
| `ranked` | `pandas.DataFrame` | Ranked output nodes |

`Path_finder()` returns a `PathResult`, which holds the same three views for each
of its two hops:

| Field | Type | Description |
| --- | --- | --- |
| `paths` | `pandas.DataFrame` | Bridging nodes, ranked |
| `node1_id`, `node2_id` | `str` | The two resolved input CURIEs |
| `knowledge_graph1`, `knowledge_graph2` | `KnowledgeGraph` | Raw edges per hop |
| `parsed1`, `parsed2` | `ParsedKnowledgeGraph` | Consolidated edges per hop |
| `ranked1`, `ranked2` | `pandas.DataFrame` | Ranked nodes per hop |

## Choosing a representation

| If you want to | Use |
| --- | --- |
| Draw or traverse a graph | `result.to_networkx()` |
| Rank or table the neighbors | `result.ranked` |
| List every raw edge | `result.knowledge_graph.to_dataframe()` |
| Inspect individual TRAPI edges | `result.knowledge_graph` (dict-like) |
| Group edges by subject-object pair | `result.parsed` |

## Graphs

`to_networkx()` returns an `nx.MultiDiGraph` keyed by CURIE. It is available on
`KnowledgeGraph`, `ParsedKnowledgeGraph`, and both result objects, and takes two
flags:

- `resolve_names=True` adds node names and categories. This makes one batched
  Node Normalizer request, so it is the slow path; skip it if you only need the
  graph structure.
- `include_attributes=True` adds publications, supporting text, and confidence
  scores to each edge.

**Node attributes** (present only with `resolve_names=True`):

| Attribute | Type | Description |
| --- | --- | --- |
| `label` | `str` | Preferred name, falling back to the CURIE |
| `categories` | `list[str] \| None` | Biolink types, most specific first |

For a single primary category, take `categories[0]`.

**Edge attributes** (always present):

| Attribute | Type | Description |
| --- | --- | --- |
| `predicate` | `str` | Biolink predicate |
| `primary_sources` | `list[str]` | Primary knowledge sources |
| `aggregator_sources` | `list[str]` | Aggregator knowledge sources |

The TRAPI edge id is the multigraph edge key rather than an attribute, so read it
with `keys=True`:

```python
for subject, obj, edge_id, data in G.edges(keys=True, data=True):
    ...
```

**Edge attributes** (added by `include_attributes=True`):

| Attribute | Type | Description |
| --- | --- | --- |
| `publications` | `list[str]` | Publication CURIEs, PubMed ids normalized to `PMID:<n>` |
| `supporting_text` | `list[str]` | Sentences supporting the edge |
| `confidence_scores` | `dict[str, float]` | Scores keyed by their source attribute |

`ParsedKnowledgeGraph.to_networkx()` is the exception: it emits one edge per
unique predicate per pair, carrying only `predicate`.

## Tabular output

`knowledge_graph.to_dataframe()` gives one row per raw edge, with columns
`Subject`, `Object`, `Predicate`.

The `ranked` DataFrame (and `paths`) is sorted descending by
`Num_of_primary_infores`:

| Column | Description |
| --- | --- |
| `output_node` | Neighbor CURIE |
| `Name` | Preferred name |
| `Num_of_primary_infores` | Count of distinct primary sources, the rank key |
| `type_of_nodes` | `"subject"` or `"object"`, the neighbor's side of the edge |
| `unique_predicates` | List of predicates connecting it to the input node |

Any edge table converts to a graph with `dataframe_to_graph()`, including a
MetaKG DataFrame (columns `API`, `Subject`, `Object`, `Predicate`, `URL`):

```python
from TCT import dataframe_to_graph
G = dataframe_to_graph(metakg, source_col="Subject", target_col="Object",
                       edge_attrs=["Predicate", "API"])
```

## Working with raw edges

`KnowledgeGraph` and `ParsedKnowledgeGraph` behave like read-only dicts, so you
can index, test membership, iterate, and call `len()`, `items()`, `keys()`,
`values()`, and `get()`:

```python
kg = nb.knowledge_graph
len(kg)                          # number of edges
edge = kg["edge_id"]             # a raw TRAPI edge dict

for edge_id, edge in kg.items():
    edge["subject"], edge["object"], edge["predicate"]
```

To pull structured metadata out of any TRAPI edge yourself:

```python
from TCT.attribute_extraction import extract_rich_edge_attributes

rich = extract_rich_edge_attributes(edge["attributes"])
# {"publications": [...], "supporting_text": [...], "confidence_scores": {...}}
```

## Notes

- The finders are silent by default. Pass `verbose=True` for progress output.
- An input CURIE that cannot be normalized raises `ValueError`.
- Unpacking a result as a tuple still works but is deprecated, and emits a
  `DeprecationWarning`. Use the named attributes above.
