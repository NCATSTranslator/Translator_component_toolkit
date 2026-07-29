import pytest
import pandas as pd

from TCT.translator_kpinfo import get_translator_kp_info


@pytest.mark.network
def test_get_translator_kp_info_returns_tuple():
    """Live API test: get_translator_kp_info returns a tuple of (DataFrame, dict)."""
    result = get_translator_kp_info()

    assert isinstance(result, tuple)
    assert len(result) == 2

    smartapi_df, api_names = result
    assert isinstance(smartapi_df, pd.DataFrame)
    assert isinstance(api_names, dict)


@pytest.mark.network
def test_get_translator_kp_info_dataframe_columns():
    """Live API test: DataFrame has the expected columns."""
    smartapi_df, _ = get_translator_kp_info()

    expected_columns = ["id", "title", "prod_url", "ci_url", "test_url"]
    for col in expected_columns:
        assert col in smartapi_df.columns, f"Missing column: {col}"


@pytest.mark.network
def test_get_translator_kp_info_non_empty():
    """Live API test: both DataFrame and dict are non-empty."""
    smartapi_df, api_names = get_translator_kp_info()

    assert len(smartapi_df) > 0, "DataFrame should be non-empty"
    assert len(api_names) > 0, "API names dict should be non-empty"
