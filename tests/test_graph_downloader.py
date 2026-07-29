"""Tests for TCT.graph_downloader.

Network download, zstd decompression, and tar extraction are all mocked; the
kg_loader handoff is mocked too. No real downloads occur.
"""

from unittest.mock import patch, MagicMock

import pytest

from TCT import graph_downloader as gd


def test_load_graph_unknown_name():
    with pytest.raises(ValueError):
        gd.load_graph("not_a_real_graph")


def test_load_graph_when_files_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "CACHE_DIR", tmp_path)
    graph_path = tmp_path / "signor"
    graph_path.mkdir()
    # pre-create the expected files so no download is triggered
    (graph_path / "graph-metadata.json").write_text("{}")
    (graph_path / "nodes.jsonl").write_text("")
    (graph_path / "edges.jsonl").write_text("")

    sentinel_graph = object()
    with patch("TCT.kg_loader.import_kg2_jsonl", return_value=("n", "e", "nt", "et")) as mock_import, \
         patch("TCT.kg_loader.load_kg2_igraph_from_data", return_value=sentinel_graph) as mock_load, \
         patch.object(gd, "download_graph") as mock_download:
        result = gd.load_graph("signor")

    assert result is sentinel_graph
    mock_download.assert_not_called()
    mock_import.assert_called_once()
    mock_load.assert_called_once()


def test_load_graph_triggers_download(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "CACHE_DIR", tmp_path)

    def fake_download(name):
        # create the files the loader expects
        p = tmp_path / name
        (p / "graph-metadata.json").write_text("{}")
        (p / "nodes.jsonl").write_text("")
        (p / "edges.jsonl").write_text("")

    with patch.object(gd, "download_graph", side_effect=fake_download) as mock_download, \
         patch("TCT.kg_loader.import_kg2_jsonl", return_value=("n", "e", "nt", "et")), \
         patch("TCT.kg_loader.load_kg2_igraph_from_data", return_value=object()):
        gd.load_graph("signor")

    mock_download.assert_called_once_with("signor")


def test_download_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(gd, "CACHE_DIR", tmp_path)
    graph_path = tmp_path / "signor"
    graph_path.mkdir()

    fake_response = MagicMock()
    fake_response.iter_content.return_value = [b"compressed-bytes"]

    with patch("TCT.graph_downloader.requests.get", return_value=fake_response) as mock_get, \
         patch("TCT.graph_downloader.ZstdDecompressor") as mock_zstd, \
         patch("TCT.graph_downloader.tarfile.open") as mock_tar:
        mock_tar.return_value.__enter__.return_value = MagicMock()
        gd.download_graph("signor")

    # downloaded from the configured signor URL and wrote the archive
    mock_get.assert_called_once()
    assert "signor" in mock_get.call_args[0][0]
    assert (graph_path / "signor.tar.zst").exists()
    # decompression + extraction were invoked
    mock_zstd.return_value.copy_stream.assert_called_once()
    mock_tar.return_value.__enter__.return_value.extractall.assert_called_once_with(graph_path)
