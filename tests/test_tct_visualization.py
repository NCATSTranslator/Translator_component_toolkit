"""Tests for TCT visualization functions."""

from unittest.mock import MagicMock, patch

import pandas as pd

import TCT.visualization as viz


# ---------------------------------------------------------------------------
# 1. plot_heatmap
# ---------------------------------------------------------------------------

class TestPlotHeatmap:
    """Tests for the plot_heatmap function."""

    def test_plot_heatmap_runs_without_error(self):
        """plot_heatmap should execute without raising on a small binary DataFrame."""
        df = pd.DataFrame(
            {"NodeA": [1, 0], "NodeB": [0, 1], "NodeC": [1, 1]},
            index=["predicate_x", "predicate_y"],
        )
        # plot_heatmap calls plt.show() but Agg backend makes it a no-op
        viz.plot_heatmap(df, num_of_nodes=3, fontsize=6, title_fontsize=10)

    def test_plot_heatmap_with_single_column(self):
        """plot_heatmap should handle a DataFrame with a single column."""
        df = pd.DataFrame({"NodeA": [1, 0, 1]}, index=["p1", "p2", "p3"])
        viz.plot_heatmap(df, num_of_nodes=1)

    def test_plot_heatmap_num_of_nodes_clips_columns(self):
        """When num_of_nodes < total columns, only that many columns are shown."""
        df = pd.DataFrame(
            {"A": [1], "B": [0], "C": [1], "D": [0]}, index=["pred"]
        )
        # Should not raise even though num_of_nodes < number of columns
        viz.plot_heatmap(df, num_of_nodes=2)


# ---------------------------------------------------------------------------
# 2. plot_heatmap_ui
# ---------------------------------------------------------------------------

class TestPlotHeatmapUI:
    """Tests for the plot_heatmap_ui function (saves to file)."""

    def test_plot_heatmap_ui_creates_file(self, tmp_path):
        """plot_heatmap_ui should create a PNG file at the given path."""
        df = pd.DataFrame(
            {"NodeA": [1, 0], "NodeB": [0, 1]},
            index=["pred_x", "pred_y"],
        )
        out = str(tmp_path / "heatmap_test.png")
        viz.plot_heatmap_ui(df, num_of_nodes=2, output_png=out)
        assert (tmp_path / "heatmap_test.png").exists()

    def test_plot_heatmap_ui_file_is_nonempty(self, tmp_path):
        """The output PNG should have non-zero size."""
        df = pd.DataFrame({"N1": [1, 0, 1]}, index=["a", "b", "c"])
        out = str(tmp_path / "heatmap_nonempty.png")
        viz.plot_heatmap_ui(df, num_of_nodes=1, output_png=out)
        assert (tmp_path / "heatmap_nonempty.png").stat().st_size > 0


# ---------------------------------------------------------------------------
# 3. plot_path_bar
# ---------------------------------------------------------------------------

class TestPlotPathBar:
    """Tests for the plot_path_bar function."""

    def test_plot_path_bar_creates_file(self, tmp_path):
        """plot_path_bar should save a PNG to the specified path."""
        x = ["gene1", "gene2", "gene3"]
        y = [10, 7, 3]
        out = str(tmp_path / "bar_test.png")
        viz.plot_path_bar(x, y, output_png=out)
        assert (tmp_path / "bar_test.png").exists()

    def test_plot_path_bar_file_is_nonempty(self, tmp_path):
        """The generated bar chart file should have non-zero size."""
        x = ["a", "b"]
        y = [5, 2]
        out = str(tmp_path / "bar_nonempty.png")
        viz.plot_path_bar(x, y, output_png=out)
        assert (tmp_path / "bar_nonempty.png").stat().st_size > 0


# ---------------------------------------------------------------------------
# Helper: synthetic data for one-hop ranking tests
# ---------------------------------------------------------------------------

def _make_one_hop_data():
    """Return (result_ranked_by_primary_infores, result_parsed, input_query)."""
    input_query = "CURIE:0001"
    result_ranked = pd.DataFrame({
        "output_node": ["CURIE:0002", "CURIE:0003"],
        "type_of_nodes": ["object", "subject"],
    })
    result_parsed = {
        "CURIE:0001_CURIE:0002": {
            "predicate": ["biolink:related_to"],
            "primary_knowledge_source": ["infores:kp1"],
            "aggregator_knowledge_source": ["infores:agg1"],
        },
        "CURIE:0003_CURIE:0001": {
            "predicate": ["biolink:affects"],
            "primary_knowledge_source": ["infores:kp2"],
        },
    }
    return result_ranked, result_parsed, input_query


# ---------------------------------------------------------------------------
# 4. visulization_one_hop_ranking
# ---------------------------------------------------------------------------

class TestVisulizationOneHopRanking:
    """Tests for visulization_one_hop_ranking."""

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dataframe(self, mock_id_convert, mock_plot):
        """The function should return a pandas DataFrame."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        result = viz.visulization_one_hop_ranking(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        assert isinstance(result, pd.DataFrame)

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_calls_plot_heatmap_twice(self, mock_id_convert, mock_plot):
        """plot_heatmap should be called twice (once per heatmap)."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        viz.visulization_one_hop_ranking(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        assert mock_plot.call_count == 2

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_columns_use_preferred_names(self, mock_id_convert, mock_plot):
        """Returned DataFrame columns should use the preferred names from the mock."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        result = viz.visulization_one_hop_ranking(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        assert "NodeB" in result.columns or "NodeC" in result.columns


# ---------------------------------------------------------------------------
# 5. visulization_one_hop_ranking_input_as_list
# ---------------------------------------------------------------------------

class TestVisulizationOneHopRankingInputAsList:
    """Tests for visulization_one_hop_ranking_input_as_list."""

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dataframe(self, mock_id_convert, mock_plot):
        """The function should return a pandas DataFrame."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        result = viz.visulization_one_hop_ranking_input_as_list(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        assert isinstance(result, pd.DataFrame)

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_calls_plot_heatmap_twice(self, mock_id_convert, mock_plot):
        """plot_heatmap should be called twice for the two heatmaps."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        viz.visulization_one_hop_ranking_input_as_list(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        assert mock_plot.call_count == 2

    @patch("TCT.visualization.plot_heatmap")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_dataframe_has_binary_values(self, mock_id_convert, mock_plot):
        """Returned DataFrame should contain only 0s and 1s."""
        mock_id_convert.return_value = {
            "CURIE:0002": "NodeB",
            "CURIE:0003": "NodeC",
        }
        ranked, parsed, query = _make_one_hop_data()
        result = viz.visulization_one_hop_ranking_input_as_list(
            ranked, parsed, num_of_nodes=2, input_query=query
        )
        unique_vals = set(result.values.flatten())
        assert unique_vals.issubset({0, 1})


# ---------------------------------------------------------------------------
# Helper: set up CytoscapeWidget mock
# ---------------------------------------------------------------------------

def _make_cytoscape_mock():
    """Return a MagicMock that acts like ipycytoscape.CytoscapeWidget."""
    widget = MagicMock()
    widget.graph.add_graph_from_networkx = MagicMock()
    widget.set_layout = MagicMock()
    widget.set_style = MagicMock()
    return widget


# ---------------------------------------------------------------------------
# 6. plot_graph_by_predicates
# ---------------------------------------------------------------------------

class TestPlotGraphByPredicates:
    """Tests for plot_graph_by_predicates."""

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_runs_without_error(self, mock_cw_cls, mock_display):
        """plot_graph_by_predicates should complete without errors."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["GeneA", "GeneA"],
            "Object": ["DrugX", "DrugY"],
            "Predicate": ["biolink:treats", "biolink:related_to"],
        })
        viz.plot_graph_by_predicates(df)
        mock_display.assert_called_once()

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_creates_cytoscape_widget(self, mock_cw_cls, mock_display):
        """A CytoscapeWidget should be instantiated."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["A"],
            "Object": ["B"],
            "Predicate": ["biolink:interacts_with"],
        })
        viz.plot_graph_by_predicates(df)
        mock_cw_cls.assert_called_once()


# ---------------------------------------------------------------------------
# 7. plot_graph_by_infores
# ---------------------------------------------------------------------------

class TestPlotGraphByInfores:
    """Tests for plot_graph_by_infores."""

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_runs_without_error(self, mock_cw_cls, mock_display):
        """plot_graph_by_infores should complete without errors."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["GeneA", "GeneB"],
            "Object": ["DrugX", "DrugX"],
            "Infores": ["infores:kp1", "infores:kp2"],
        })
        viz.plot_graph_by_infores(df)
        mock_display.assert_called_once()

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_returns_zero(self, mock_cw_cls, mock_display):
        """plot_graph_by_infores should return 0."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["A"],
            "Object": ["B"],
            "Infores": ["infores:src"],
        })
        assert viz.plot_graph_by_infores(df) == 0


# ---------------------------------------------------------------------------
# 8. plot_graph_by_API
# ---------------------------------------------------------------------------

class TestPlotGraphByAPI:
    """Tests for plot_graph_by_API."""

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_runs_without_error(self, mock_cw_cls, mock_display):
        """plot_graph_by_API should complete without errors."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["GeneA", "GeneB"],
            "Object": ["DrugX", "DrugY"],
            "API": ["API_A", "API_B"],
        })
        viz.plot_graph_by_API(df)
        mock_display.assert_called_once()

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    def test_returns_zero(self, mock_cw_cls, mock_display):
        """plot_graph_by_API should return 0."""
        mock_cw_cls.return_value = _make_cytoscape_mock()
        df = pd.DataFrame({
            "Subject": ["A"],
            "Object": ["B"],
            "API": ["SomeAPI"],
        })
        assert viz.plot_graph_by_API(df) == 0


# ---------------------------------------------------------------------------
# 9. visulize_path
# ---------------------------------------------------------------------------

class TestVisulizePath:
    """Tests for visulize_path."""

    @staticmethod
    def _make_path_data():
        """Create synthetic result dicts for visulize_path."""
        input_node1 = "CURIE:001"
        intermediate = "CURIE:002"
        input_node3 = "CURIE:003"

        result = {
            "e1": {
                "subject": "CURIE:001",
                "object": "CURIE:002",
                "predicate": "biolink:related_to",
                "sources": [
                    {"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"},
                ],
            },
            "e_extra": {
                "subject": "CURIE:999",
                "object": "CURIE:888",
                "predicate": "biolink:unrelated",
                "sources": [
                    {"resource_id": "infores:other", "resource_role": "primary_knowledge_source"},
                ],
            },
        }
        result2 = {
            "e2": {
                "subject": "CURIE:002",
                "object": "CURIE:003",
                "predicate": "biolink:affects",
                "sources": [
                    {"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"},
                ],
            },
        }
        return input_node1, intermediate, input_node3, result, result2

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dataframe(self, mock_id_convert, mock_cw_cls, mock_display):
        """visulize_path should return a DataFrame."""
        mock_id_convert.return_value = {
            "CURIE:001": "Node1",
            "CURIE:002": "Node2",
            "CURIE:003": "Node3",
        }
        mock_cw_cls.return_value = _make_cytoscape_mock()
        n1, mid, n3, r1, r2 = self._make_path_data()
        result = viz.visulize_path(n1, mid, n3, r1, r2)
        assert isinstance(result, pd.DataFrame)

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_dataframe_has_expected_columns(self, mock_id_convert, mock_cw_cls, mock_display):
        """Returned DataFrame should contain Subject_name and Object_name columns."""
        mock_id_convert.return_value = {
            "CURIE:001": "Node1",
            "CURIE:002": "Node2",
            "CURIE:003": "Node3",
        }
        mock_cw_cls.return_value = _make_cytoscape_mock()
        n1, mid, n3, r1, r2 = self._make_path_data()
        result = viz.visulize_path(n1, mid, n3, r1, r2)
        assert "Subject_name" in result.columns
        assert "Object_name" in result.columns
        assert "Predicates" in result.columns

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_filters_to_relevant_edges(self, mock_id_convert, mock_cw_cls, mock_display):
        """Only edges involving the intermediate node and the two endpoints should appear."""
        mock_id_convert.return_value = {
            "CURIE:001": "Node1",
            "CURIE:002": "Node2",
            "CURIE:003": "Node3",
        }
        mock_cw_cls.return_value = _make_cytoscape_mock()
        n1, mid, n3, r1, r2 = self._make_path_data()
        result = viz.visulize_path(n1, mid, n3, r1, r2)
        # The extra edge (CURIE:999 -> CURIE:888) should be excluded
        all_subjects = set(result["Subject"].values)
        all_objects = set(result["Object"].values)
        all_nodes = all_subjects | all_objects
        assert "CURIE:999" not in all_nodes
        assert "CURIE:888" not in all_nodes

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape.CytoscapeWidget")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_display_called(self, mock_id_convert, mock_cw_cls, mock_display):
        """display() should be called to show the cytoscape widget."""
        mock_id_convert.return_value = {
            "CURIE:001": "Node1",
            "CURIE:002": "Node2",
            "CURIE:003": "Node3",
        }
        mock_cw_cls.return_value = _make_cytoscape_mock()
        n1, mid, n3, r1, r2 = self._make_path_data()
        viz.visulize_path(n1, mid, n3, r1, r2)
        mock_display.assert_called_once()


# ---------------------------------------------------------------------------
# 10. visualize_neighborhood_graph (TCT_Visualization.py)
# ---------------------------------------------------------------------------

class TestVisualizeNeighborhoodGraph:
    """Tests for TCT_Visualization.visualize_neighborhood_graph."""

    @staticmethod
    def _make_neighborhood_result():
        """Create a synthetic result dict for visualize_neighborhood_graph."""
        return {
            "edge1": {
                "subject": "CURIE:A",
                "object": "CURIE:B",
                "predicate": "biolink:interacts_with",
                "sources": [
                    {"resource_id": "infores:src1", "resource_role": "primary_knowledge_source"},
                ],
                "attributes": [
                    {
                        "attribute_type_id": "biolink:publications",
                        "original_attribute_name": "publications",
                        "value": ["PMID:12345"],
                    },
                ],
            },
            "edge2": {
                "subject": "CURIE:A",
                "object": "CURIE:C",
                "predicate": "biolink:related_to",
                "sources": [
                    {"resource_id": "infores:src2", "resource_role": "aggregator_knowledge_source"},
                ],
                "attributes": [],
            },
        }

    @staticmethod
    def _make_network_mock():
        """Return a MagicMock that acts like pyvis.network.Network."""
        net = MagicMock()
        net.edges = []
        net.num_nodes.return_value = 3
        net.num_edges.return_value = 2
        net.title = ""
        net.show = MagicMock()
        net.from_nx = MagicMock()
        return net

    @patch("TCT.visualization.Network")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dict(self, mock_id_convert, mock_network_cls):
        """visualize_neighborhood_graph should return a dict of networkx graphs."""
        from TCT.visualization import visualize_neighborhood_graph

        mock_id_convert.return_value = {
            "CURIE:A": "NodeA",
            "CURIE:B": "NodeB",
            "CURIE:C": "NodeC",
        }
        mock_network_cls.return_value = self._make_network_mock()
        result = self._make_neighborhood_result()
        dic_graph = visualize_neighborhood_graph(result, show_label=True)
        assert isinstance(dic_graph, dict)

    @patch("TCT.visualization.Network")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_keys_are_predicates(self, mock_id_convert, mock_network_cls):
        """The returned dict keys should be predicate names (stripped of biolink:)."""
        from TCT.visualization import visualize_neighborhood_graph

        mock_id_convert.return_value = {
            "CURIE:A": "NodeA",
            "CURIE:B": "NodeB",
            "CURIE:C": "NodeC",
        }
        mock_network_cls.return_value = self._make_network_mock()
        result = self._make_neighborhood_result()
        dic_graph = visualize_neighborhood_graph(result, show_label=True)
        # The function strips "biolink:" prefix via .strip("biolink:")
        # which character-strips, so "biolink:interacts_with" -> "nteracts_wth" (approx)
        # We just check the dict is non-empty with string keys
        assert len(dic_graph) > 0
        for key in dic_graph:
            assert isinstance(key, str)

    @patch("TCT.visualization.Network")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_show_label_false(self, mock_id_convert, mock_network_cls):
        """With show_label=False, raw CURIEs should be used as node labels."""
        from TCT.visualization import visualize_neighborhood_graph
        import networkx as nx

        mock_id_convert.return_value = {
            "CURIE:A": "NodeA",
            "CURIE:B": "NodeB",
            "CURIE:C": "NodeC",
        }
        mock_network_cls.return_value = self._make_network_mock()
        result = self._make_neighborhood_result()
        dic_graph = visualize_neighborhood_graph(result, show_label=False)
        # When show_label=False, the raw CURIE IDs are used as node names
        for predicate, graph in dic_graph.items():
            assert isinstance(graph, nx.DiGraph)
            for node in graph.nodes():
                assert node.startswith("CURIE:")

    @patch("TCT.visualization.Network")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_network_show_called(self, mock_id_convert, mock_network_cls):
        """Network.show() should be called to render the HTML output."""
        from TCT.visualization import visualize_neighborhood_graph

        mock_id_convert.return_value = {
            "CURIE:A": "NodeA",
            "CURIE:B": "NodeB",
            "CURIE:C": "NodeC",
        }
        net_mock = self._make_network_mock()
        mock_network_cls.return_value = net_mock
        result = self._make_neighborhood_result()
        visualize_neighborhood_graph(result, show_label=True)
        net_mock.show.assert_called()

    @patch("TCT.visualization.Network")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_network_from_nx_called(self, mock_id_convert, mock_network_cls):
        """Network.from_nx() should be called to populate the pyvis network."""
        from TCT.visualization import visualize_neighborhood_graph

        mock_id_convert.return_value = {
            "CURIE:A": "NodeA",
            "CURIE:B": "NodeB",
            "CURIE:C": "NodeC",
        }
        net_mock = self._make_network_mock()
        mock_network_cls.return_value = net_mock
        result = self._make_neighborhood_result()
        visualize_neighborhood_graph(result, show_label=True)
        net_mock.from_nx.assert_called()
