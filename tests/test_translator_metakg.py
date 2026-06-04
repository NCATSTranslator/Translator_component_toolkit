import pandas as pd
from unittest.mock import patch, MagicMock

from TCT.translator_metakg import (
    find_link,
    get_KP_metadata,
    add_new_API_for_query,
    add_plover_API,
    load_translator_resources,
)


# ---------------------------------------------------------------------------
# find_link tests
# ---------------------------------------------------------------------------

class TestFindLink:
    """Tests for the find_link function."""

    def test_name_with_trapi_suffix_old_url(self):
        """The legacy consolidated URL (use_new_url=False) encodes the Trapi suffix."""
        url = find_link("Some API (Trapi v1.5.0)", use_new_url=False)
        assert url.startswith(
            "https://smart-api.info/api/metakg/consolidated?size=5000&q="
        )
        # The URL should end with the encoded Trapi suffix
        assert "%5C%28Trapi+v1.5.0%5C%29" in url

    def test_name_without_trapi_suffix_new_url(self):
        """The default (new) URL uses the metakg endpoint with aggs facets."""
        url = find_link("Some API Name")
        assert url.startswith(
            "https://smart-api.info/api/metakg?size=5000&q="
        )
        assert "Some+API+Name" in url
        assert url.endswith(")&facet_size=300&aggs=object.raw,subject.raw")

    def test_single_word_name_new_url(self):
        """Single-word name on the default (new) URL."""
        url = find_link("SingleWord")
        assert url.startswith(
            "https://smart-api.info/api/metakg?size=5000&q="
        )
        assert "SingleWord" in url

    def test_single_word_name_old_url(self):
        """Single-word name on the legacy URL ends with the encoded paren."""
        url = find_link("SingleWord", use_new_url=False)
        assert url.startswith(
            "https://smart-api.info/api/metakg/consolidated?size=5000&q="
        )
        assert url.endswith("%29")


# ---------------------------------------------------------------------------
# get_KP_metadata tests
# ---------------------------------------------------------------------------

class TestGetKPMetadata:
    """Tests for get_KP_metadata with mocked HTTP calls."""

    @patch("TCT.translator_metakg.requests.get")
    def test_returns_dataframe_with_expected_columns(self, mock_get):
        """Mock SmartAPI metakg response and verify DataFrame structure."""
        mock_response = MagicMock()
        mock_response.text = '{"hits": [{"_id": "Gene-interacts_with-SmallMolecule"}]}'
        mock_get.return_value = mock_response

        api_names = {"TestAPI": "https://example.com/query"}
        result = get_KP_metadata(api_names)

        assert isinstance(result, pd.DataFrame)
        for col in ["API", "Predicate", "Subject", "Object", "URL"]:
            assert col in result.columns, f"Missing column: {col}"
        assert len(result) == 1
        assert result.iloc[0]["API"] == "TestAPI"
        assert result.iloc[0]["Predicate"] == "biolink:interacts_with"
        assert result.iloc[0]["Subject"] == "biolink:Gene"
        assert result.iloc[0]["Object"] == "biolink:SmallMolecule"
        assert result.iloc[0]["URL"] == "https://example.com/query"

    @patch("TCT.translator_metakg.requests.get")
    def test_rtx_kg2_special_case(self, mock_get):
        """The 'RTX KG2 - TRAPI 1.5.0' key should use a hardcoded URL."""
        mock_response = MagicMock()
        mock_response.text = '{"hits": [{"_id": "Gene-related_to-Disease"}]}'
        mock_get.return_value = mock_response

        api_names = {"RTX KG2 - TRAPI 1.5.0": "https://rtx.example.com/query"}
        result = get_KP_metadata(api_names)

        # Verify the hardcoded URL was used for RTX KG2
        call_url = mock_get.call_args[0][0]
        assert "RTX+KG2" in call_url
        assert len(result) == 1
        assert result.iloc[0]["API"] == "RTX KG2 - TRAPI 1.5.0"


# ---------------------------------------------------------------------------
# add_new_API_for_query tests
# ---------------------------------------------------------------------------

class TestAddNewAPIForQuery:
    """Tests for add_new_API_for_query (pure computation)."""

    def test_adds_api_and_row(self):
        """Adding a new API updates the dict and appends a row to the DataFrame."""
        api_names = {"ExistingAPI": "https://existing.example.com/query"}
        meta_kg = pd.DataFrame({
            "API": ["ExistingAPI"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:SmallMolecule"],
            "URL": ["https://existing.example.com/query"],
        })

        new_api_names, new_meta_kg = add_new_API_for_query(
            api_names, meta_kg,
            "NewAPI",
            "https://new.example.com/query",
            "biolink:related_to",
            "biolink:Disease",
            "biolink:Gene",
        )

        assert "NewAPI" in new_api_names
        assert new_api_names["NewAPI"] == "https://new.example.com/query"
        assert len(new_meta_kg) == 2
        new_row = new_meta_kg[new_meta_kg["API"] == "NewAPI"].iloc[0]
        assert new_row["Predicate"] == "biolink:related_to"
        assert new_row["Subject"] == "biolink:Disease"
        assert new_row["Object"] == "biolink:Gene"
        assert new_row["URL"] == "https://new.example.com/query"


# ---------------------------------------------------------------------------
# add_plover_API tests
# ---------------------------------------------------------------------------

class TestAddPloverAPI:
    """Tests for add_plover_API with mocked HTTP calls."""

    @patch("TCT.translator_metakg.requests.get")
    def test_adds_plover_apis(self, mock_get):
        """Mock all 7 Plover API meta_knowledge_graph endpoints."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "edges": [
                {
                    "predicate": "biolink:interacts_with",
                    "subject": "biolink:Gene",
                    "object": "biolink:Gene",
                }
            ]
        }
        mock_get.return_value = mock_response

        api_names = {"ExistingAPI": "https://existing.example.com/query"}
        meta_kg = pd.DataFrame({
            "API": ["ExistingAPI"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:SmallMolecule"],
            "URL": ["https://existing.example.com/query"],
        })

        new_api_names, new_meta_kg = add_plover_API(api_names, meta_kg)

        # Should have called requests.get 7 times (one per Plover endpoint)
        assert mock_get.call_count == 7

        # Should have added new rows (7 new APIs, each with 1 edge)
        assert len(new_meta_kg) == 1 + 7  # 1 existing + 7 new

        # The original API should still be present
        assert "ExistingAPI" in new_api_names

        # Some of the Plover APIs should be present
        expected_plover_names = [
            "CATRAX BigGIM DrugResponse Performance Phase KP - TRAPI 1.5.0",
            "CATRAX Pharmacogenomics KP - TRAPI 1.5.0",
            "Clinical Trials KP - TRAPI 1.5.0",
            "Drug Approvals KP - TRAPI 1.5.0",
            "Multiomics KP - TRAPI 1.5.0",
            "Microbiome KP - TRAPI 1.5.0",
            "RTX KG2 - TRAPI 1.5.0",
        ]
        for name in expected_plover_names:
            assert name in new_api_names


# ---------------------------------------------------------------------------
# load_translator_resources tests
# ---------------------------------------------------------------------------

class TestLoadTranslatorResources:
    """Tests for load_translator_resources with mocked dependencies."""

    @patch("TCT.translator_metakg.add_plover_API")
    @patch("TCT.translator_metakg.get_KP_metadata")
    @patch("TCT.translator_kpinfo.get_translator_kp_info")
    def test_returns_three_items(self, mock_kp_info, mock_kp_metadata, mock_plover):
        """load_translator_resources returns a tuple of 3 items."""
        mock_df = pd.DataFrame({
            "id": ["id1"],
            "title": ["API1"],
            "prod_url": ["https://example.com"],
            "ci_url": [None],
            "test_url": [None],
        })
        mock_api_names = {"API1": "https://example.com/query"}
        mock_kp_info.return_value = (mock_df, mock_api_names)

        mock_meta_kg = pd.DataFrame({
            "API": ["API1"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Gene"],
            "URL": ["https://example.com/query"],
        })
        mock_kp_metadata.return_value = mock_meta_kg

        mock_plover.return_value = (mock_api_names, mock_meta_kg)

        result = load_translator_resources()

        assert isinstance(result, tuple)
        assert len(result) == 3
