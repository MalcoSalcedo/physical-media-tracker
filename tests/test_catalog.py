import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app import catalog

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


def test_lookup_uses_discogs_match_without_calling_musicbrainz():
    discogs_result = {"artist": "Boards of Canada", "album": "Music Has the Right to Children"}
    with (
        patch("app.catalog.discogs.search_by_barcode", return_value=discogs_result) as discogs_mock,
        patch("app.catalog.musicbrainz.search_by_barcode") as mb_mock,
    ):
        result = catalog.lookup_barcode("0724348037755")

    assert result == discogs_result
    discogs_mock.assert_called_once_with("0724348037755")
    mb_mock.assert_not_called()


def test_lookup_falls_back_to_musicbrainz_when_discogs_has_no_match():
    mb_result = {"artist": "Boards of Canada", "album": "Geogaddi"}
    with (
        patch("app.catalog.discogs.search_by_barcode", return_value=None),
        patch("app.catalog.musicbrainz.search_by_barcode", return_value=mb_result) as mb_mock,
    ):
        result = catalog.lookup_barcode("0724348037755")

    assert result == mb_result
    mb_mock.assert_called_once_with("0724348037755")


def test_lookup_returns_none_when_neither_source_matches():
    with (
        patch("app.catalog.discogs.search_by_barcode", return_value=None),
        patch("app.catalog.musicbrainz.search_by_barcode", return_value=None),
    ):
        result = catalog.lookup_barcode("0000000000000")

    assert result is None


def test_save_item_and_list_items_roundtrip(conn):
    item_id = catalog.save_item(
        conn,
        artist="Boards of Canada",
        album="Music Has the Right to Children",
        format="CD",
        barcode="0724348037755",
    )

    items = catalog.list_items(conn)

    assert item_id is not None
    assert len(items) == 1
    assert items[0]["artist"] == "Boards of Canada"
    assert items[0]["barcode"] == "0724348037755"
