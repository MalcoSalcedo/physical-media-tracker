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


def test_fetch_tracklist_prefers_discogs_when_both_ids_present(conn):
    item_id = catalog.save_item(
        conn,
        artist="Radiohead",
        album="In Rainbows",
        format="Vinyl",
        discogs_id="26806592",
        musicbrainz_id="some-mbid",
    )
    item = catalog.get_item(conn, item_id)

    with (
        patch("app.catalog.discogs.get_tracklist", return_value=[{"title": "15 Step"}]) as d_mock,
        patch("app.catalog.musicbrainz.get_tracklist") as mb_mock,
    ):
        tracks = catalog.fetch_tracklist(item)

    assert tracks == [{"title": "15 Step"}]
    d_mock.assert_called_once_with("26806592")
    mb_mock.assert_not_called()


def test_fetch_tracklist_falls_back_to_musicbrainz_when_no_discogs_id(conn):
    item_id = catalog.save_item(
        conn, artist="Radiohead", album="In Rainbows", format="Vinyl", musicbrainz_id="some-mbid"
    )
    item = catalog.get_item(conn, item_id)

    with patch("app.catalog.musicbrainz.get_tracklist", return_value=[{"title": "Bodysnatchers"}]) as mb_mock:
        tracks = catalog.fetch_tracklist(item)

    assert tracks == [{"title": "Bodysnatchers"}]
    mb_mock.assert_called_once_with("some-mbid")


def test_fetch_tracklist_returns_empty_for_manual_entry_without_ids(conn):
    item_id = catalog.save_item(conn, artist="Unknown Artist", album="Mixtape", format="CD")
    item = catalog.get_item(conn, item_id)

    assert catalog.fetch_tracklist(item) == []


def test_save_and_get_tracks_roundtrip(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")

    catalog.save_tracks(
        conn,
        item_id,
        [
            {"position": "A1", "title": "15 Step", "duration_seconds": 237},
            {"position": "A2", "title": "Bodysnatchers", "duration_seconds": 242},
        ],
    )
    tracks = catalog.get_tracks(conn, item_id)

    assert [t["title"] for t in tracks] == ["15 Step", "Bodysnatchers"]
    assert tracks[0]["duration_seconds"] == 237


def test_save_tracks_replaces_previous_tracklist(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")

    catalog.save_tracks(conn, item_id, [{"title": "Old Track"}])
    catalog.save_tracks(conn, item_id, [{"title": "New Track"}])

    tracks = catalog.get_tracks(conn, item_id)
    assert [t["title"] for t in tracks] == ["New Track"]


def test_set_active_album_and_get_now_playing(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")

    catalog.set_active_album(conn, item_id)
    current = catalog.get_now_playing(conn)

    assert current["collection_id"] == item_id
    assert current["album"] == "In Rainbows"
    assert current["track_title"] is None
    assert current["source"] == "manual"


def test_set_active_album_overwrites_previous_selection(conn):
    first_id = catalog.save_item(conn, artist="Artist A", album="Album A", format="CD")
    second_id = catalog.save_item(conn, artist="Artist B", album="Album B", format="CD")

    catalog.set_active_album(conn, first_id)
    catalog.set_active_album(conn, second_id)
    current = catalog.get_now_playing(conn)

    assert current["collection_id"] == second_id
    assert current["album"] == "Album B"


def test_find_cached_match_returns_none_when_nothing_cached(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step"}, {"title": "Bodysnatchers"}])

    assert catalog.find_cached_match(conn, item_id, [1, 2, 3]) is None


def test_save_and_find_cached_fingerprint_roundtrip(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step"}, {"title": "Bodysnatchers"}])

    fp = [10, 20, 30, 40, 50]
    catalog.save_track_fingerprint(conn, item_id, "15 Step", fp)

    assert catalog.find_cached_match(conn, item_id, fp) == "15 Step"


def test_find_cached_match_picks_best_of_multiple_cached_tracks(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step"}, {"title": "Bodysnatchers"}])

    fp_a = [1, 2, 3, 4, 5, 6, 7, 8]
    fp_b = [100, 200, 300, 400, 500, 600, 700, 800]
    catalog.save_track_fingerprint(conn, item_id, "15 Step", fp_a)
    catalog.save_track_fingerprint(conn, item_id, "Bodysnatchers", fp_b)

    assert catalog.find_cached_match(conn, item_id, fp_b) == "Bodysnatchers"


def test_find_cached_match_rejects_dissimilar_fingerprint(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step"}])
    catalog.save_track_fingerprint(conn, item_id, "15 Step", [1, 2, 3, 4, 5])

    assert catalog.find_cached_match(conn, item_id, [999999, 888888, 777777]) is None
