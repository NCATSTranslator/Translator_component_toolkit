"""Result classes with built-in graph conversion for TCT query results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import networkx as nx
import pandas as pd


@runtime_checkable
class GraphConvertible(Protocol):
    """Protocol for types that can be converted to a NetworkX graph."""

    def to_networkx(self, resolve_names: bool = False) -> nx.MultiDiGraph: ...


class KnowledgeGraph:
    """Wraps raw TRAPI edges dict from parallel_api_query().

    Provides dict-like access and graph conversion.
    """

    def __init__(self, edges: dict[str, dict]):
        self._edges = edges

    @property
    def edges(self) -> dict[str, dict]:
        return self._edges

    # Dict-like interface
    def __len__(self):
        return len(self._edges)

    def __iter__(self):
        return iter(self._edges)

    def __getitem__(self, key):
        return self._edges[key]

    def __contains__(self, key):
        return key in self._edges

    def __eq__(self, other):
        if isinstance(other, dict):
            return self._edges == other
        if isinstance(other, KnowledgeGraph):
            return self._edges == other._edges
        return NotImplemented

    def __bool__(self):
        return bool(self._edges)

    def items(self):
        return self._edges.items()

    def keys(self):
        return self._edges.keys()

    def values(self):
        return self._edges.values()

    def get(self, key, default=None):
        return self._edges.get(key, default)

    def to_networkx(self, resolve_names: bool = False, include_attributes: bool = False) -> nx.MultiDiGraph:
        """Convert to a NetworkX MultiDiGraph with full edge metadata."""
        G = nx.MultiDiGraph()

        for edge_id, edge_data in self._edges.items():
            subject = edge_data["subject"]
            obj = edge_data["object"]
            predicate = edge_data.get("predicate", "")

            primary_sources = []
            aggregator_sources = []
            for source in edge_data.get("sources", []):
                role = source.get("resource_role", "")
                resource_id = source.get("resource_id", "")
                if role == "primary_knowledge_source":
                    primary_sources.append(resource_id)
                elif role == "aggregator_knowledge_source":
                    aggregator_sources.append(resource_id)

            edge_kwargs = dict(
                key=edge_id,
                predicate=predicate,
                primary_sources=primary_sources,
                aggregator_sources=aggregator_sources,
            )

            if include_attributes:
                from .attribute_extraction import extract_rich_edge_attributes

                rich = extract_rich_edge_attributes(edge_data.get("attributes", []))
                edge_kwargs.update(rich)

            G.add_edge(subject, obj, **edge_kwargs)

        if resolve_names and len(G.nodes()) > 0:
            from . import node_normalizer

            name_map, category_map = node_normalizer.get_preferred_names_and_categories(list(G.nodes()))
            nx.set_node_attributes(G, name_map, "label")
            nx.set_node_attributes(G, category_map, "categories")

        return G

    def parse(self) -> ParsedKnowledgeGraph:
        """Consolidate edges by subject-object pair.

        Equivalent to the standalone parse_KG() logic.
        """
        result_parsed = {}
        for i in self._edges:
            edge = self._edges[i]
            subject_object = edge["subject"] + "_" + edge["object"]

            if subject_object not in result_parsed:
                result_parsed[subject_object] = {}
                result_parsed[subject_object]["predicate"] = [edge["predicate"]]
                result_parsed[subject_object]["subject"] = edge["subject"]
                result_parsed[subject_object]["object"] = edge["object"]

                for j in edge.get("sources", []):
                    if j["resource_role"] == "primary_knowledge_source":
                        result_parsed[subject_object]["primary_knowledge_source"] = [
                            j["resource_id"]
                        ]

                    evidence = (
                        edge["subject"]
                        + "_"
                        + edge["predicate"]
                        + "_"
                        + edge["object"]
                        + "_"
                        + j["resource_id"]
                    )

                    if j["resource_role"] == "aggregator_knowledge_source":
                        result_parsed[subject_object][
                            "aggregator_knowledge_source"
                        ] = [j["resource_id"]]
                        evidence = evidence + "_" + j["resource_id"]
                result_parsed[subject_object]["evidence"] = [evidence]

            else:
                result_parsed[subject_object]["predicate"].append(edge["predicate"])
                evidence = ""
                for j in edge.get("sources", []):
                    if j["resource_role"] == "primary_knowledge_source":
                        result_parsed[subject_object][
                            "primary_knowledge_source"
                        ].append(j["resource_id"])
                        evidence = (
                            edge["subject"]
                            + "_"
                            + edge["predicate"]
                            + "_"
                            + edge["object"]
                            + "_"
                            + j["resource_id"]
                        )
                    if j["resource_role"] == "aggregator_knowledge_source":
                        if (
                            "aggregator_knowledge_source"
                            not in result_parsed[subject_object]
                        ):
                            result_parsed[subject_object][
                                "aggregator_knowledge_source"
                            ] = [j["resource_id"]]
                        else:
                            result_parsed[subject_object][
                                "aggregator_knowledge_source"
                            ].append(j["resource_id"])
                        evidence = evidence + "_" + j["resource_id"]
                result_parsed[subject_object]["evidence"].append(evidence)

        return ParsedKnowledgeGraph(entries=result_parsed)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a DataFrame with Subject, Object, Predicate columns."""
        rows = []
        for edge_data in self._edges.values():
            rows.append(
                {
                    "Subject": edge_data["subject"],
                    "Object": edge_data["object"],
                    "Predicate": edge_data.get("predicate", ""),
                }
            )
        return pd.DataFrame(rows)


class ParsedKnowledgeGraph:
    """Wraps consolidated edges (grouped by subject-object pair).

    Provides dict-like access and graph conversion.
    """

    def __init__(self, entries: dict[str, dict]):
        self._entries = entries

    @property
    def entries(self) -> dict[str, dict]:
        return self._entries

    # Dict-like interface
    def __len__(self):
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __getitem__(self, key):
        return self._entries[key]

    def __contains__(self, key):
        return key in self._entries

    def __eq__(self, other):
        if isinstance(other, dict):
            return self._entries == other
        if isinstance(other, ParsedKnowledgeGraph):
            return self._entries == other._entries
        return NotImplemented

    def __bool__(self):
        return bool(self._entries)

    def items(self):
        return self._entries.items()

    def keys(self):
        return self._entries.keys()

    def values(self):
        return self._entries.values()

    def get(self, key, default=None):
        return self._entries.get(key, default)

    def to_networkx(self, resolve_names: bool = False) -> nx.MultiDiGraph:
        """Convert to a NetworkX MultiDiGraph with one edge per unique predicate per pair."""
        G = nx.MultiDiGraph()

        for entry in self._entries.values():
            subject = entry["subject"]
            obj = entry["object"]
            for predicate in set(entry.get("predicate", [])):
                G.add_edge(subject, obj, predicate=predicate)

        if resolve_names and len(G.nodes()) > 0:
            from . import node_normalizer

            name_map, category_map = node_normalizer.get_preferred_names_and_categories(list(G.nodes()))
            nx.set_node_attributes(G, name_map, "label")
            nx.set_node_attributes(G, category_map, "categories")

        return G

    def rank(self, input_node: str) -> pd.DataFrame:
        """Rank by primary infores count.

        Equivalent to the standalone rank_by_primary_infores() logic.
        """
        from . import node_normalizer

        output_nodes = []
        num_of_primary_infores = []
        type_of_nodes = []
        unique_predicates = []

        for i in self._entries:
            entry = self._entries[i]
            curr_predict = entry["predicate"]
            subject = entry["subject"]
            obj = entry["object"]

            if subject == input_node:
                output_nodes.append(obj)
                type_of_nodes.append("object")
                num_of_primary_infores.append(
                    len(set(entry.get("primary_knowledge_source", [])))
                )
                unique_predicates.append(curr_predict)
            elif obj == input_node:
                output_nodes.append(subject)
                type_of_nodes.append("subject")
                num_of_primary_infores.append(
                    len(set(entry.get("primary_knowledge_source", [])))
                )
                unique_predicates.append(curr_predict)

        new_colnames = node_normalizer.convert_ids_to_preferred_names(output_nodes)

        rank_df = pd.DataFrame()
        rank_df["output_node"] = output_nodes
        rank_df["Name"] = new_colnames
        rank_df["Num_of_primary_infores"] = num_of_primary_infores
        rank_df["type_of_nodes"] = type_of_nodes
        rank_df["unique_predicates"] = unique_predicates

        return rank_df.sort_values(by=["Num_of_primary_infores"], ascending=False)


@dataclass
class NeighborhoodResult:
    """Wraps Neighborhood_finder() output."""

    input_node_id: str
    knowledge_graph: KnowledgeGraph
    parsed: ParsedKnowledgeGraph
    ranked: pd.DataFrame

    def to_networkx(self, resolve_names: bool = False, include_attributes: bool = False) -> nx.MultiDiGraph:
        """Delegates to knowledge_graph.to_networkx()."""
        return self.knowledge_graph.to_networkx(
            resolve_names=resolve_names, include_attributes=include_attributes
        )

    def __iter__(self):
        import warnings

        warnings.warn(
            "Unpacking NeighborhoodResult as a tuple is deprecated. "
            "Use named attributes: result.input_node_id, result.knowledge_graph, "
            "result.parsed, result.ranked",
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.input_node_id
        yield self.knowledge_graph
        yield self.parsed
        yield self.ranked

    def __len__(self):
        return 4


@dataclass
class PathResult:
    """Wraps Path_finder() output."""

    paths: pd.DataFrame
    node1_id: str
    node2_id: str
    knowledge_graph1: KnowledgeGraph
    knowledge_graph2: KnowledgeGraph
    parsed1: ParsedKnowledgeGraph
    parsed2: ParsedKnowledgeGraph
    ranked1: pd.DataFrame
    ranked2: pd.DataFrame

    def to_networkx(self, resolve_names: bool = False, include_attributes: bool = False) -> nx.MultiDiGraph:
        """Merges both knowledge graphs via nx.compose()."""
        g1 = self.knowledge_graph1.to_networkx(
            resolve_names=resolve_names, include_attributes=include_attributes
        )
        g2 = self.knowledge_graph2.to_networkx(
            resolve_names=resolve_names, include_attributes=include_attributes
        )
        return nx.compose(g1, g2)

    def __iter__(self):
        import warnings

        warnings.warn(
            "Unpacking PathResult as a tuple is deprecated. "
            "Use named attributes: result.paths, result.node1_id, etc.",
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.paths
        yield self.node1_id
        yield self.node2_id
        yield self.knowledge_graph1
        yield self.knowledge_graph2
        yield self.parsed1
        yield self.parsed2
        yield self.ranked1
        yield self.ranked2

    def __len__(self):
        return 9


def dataframe_to_graph(
    df: pd.DataFrame,
    source_col: str = "Subject",
    target_col: str = "Object",
    edge_attrs: list[str] | None = None,
) -> nx.MultiDiGraph:
    """Convert an edge DataFrame to a NetworkX MultiDiGraph.

    Works with MetaKG DataFrames and other edge DataFrames.
    """
    return nx.from_pandas_edgelist(
        df,
        source=source_col,
        target=target_col,
        edge_attr=edge_attrs,
        create_using=nx.MultiDiGraph,
    )
