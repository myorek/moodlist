from __future__ import annotations

import datetime as _dt
import sqlite3

from moodlist.types import WantedAlbum
from moodlist.wishlist import WishlistDB, derive_starters, normalize_track_name


def test_normalize_lowercases_and_strips_whitespace():
    assert normalize_track_name("  Black Sabbath - Paranoid  ") == "black sabbath paranoid"


def test_normalize_handles_separator_variants():
    keys = {
        normalize_track_name("Black Sabbath - Paranoid"),
        normalize_track_name("Black Sabbath: Paranoid"),
        normalize_track_name("black sabbath – paranoid"),
        normalize_track_name("Black Sabbath -- Paranoid"),
        normalize_track_name("Black Sabbath / Paranoid"),
    }
    assert len(keys) == 1, f"expected one key, got {keys}"


def test_normalize_collapses_whitespace():
    assert normalize_track_name("Black   Sabbath\tParanoid") == "black sabbath paranoid"


def test_normalize_strips_parenthetical_live_demo_remaster_tails():
    base = normalize_track_name("Somebody to Love")
    assert normalize_track_name("Somebody to Love (live)") == base
    assert normalize_track_name("Somebody to Love (Live)") == base
    assert normalize_track_name("Somebody to Love (demo)") == base
    assert normalize_track_name("Somebody to Love (remastered)") == base
    assert normalize_track_name("Somebody to Love (remastered 2011)") == base
    assert normalize_track_name("Somebody to Love (alternate version)") == base
    assert normalize_track_name("Somebody to Love (extended mix)") == base


def test_normalize_strips_feat_suffix():
    base = normalize_track_name("Track Name")
    assert normalize_track_name("Track Name feat. Other Artist") == base
    assert normalize_track_name("Track Name ft. Other Artist") == base
    assert normalize_track_name("Track Name (feat. Other Artist)") == base


def test_normalize_preserves_year_when_inline():
    # Year inside parentheses that ISN'T a version marker stays as digits.
    assert normalize_track_name("For Whom the Bell Tolls (1986)") == "for whom the bell tolls 1986"


def test_normalize_handles_unicode_nfkc():
    # Fullwidth characters normalize to ASCII via NFKC.
    assert normalize_track_name("ＡＣ／ＤＣ - Highway") == "ac dc highway"


def test_normalize_empty_string_returns_empty():
    assert normalize_track_name("") == ""
    assert normalize_track_name("   ") == ""


def test_derive_starters_latin_only_no_japanese_name():
    assert derive_starters("AC/DC", None) == ("A", None)
    assert derive_starters("U2", None) == ("U", None)


def test_derive_starters_japanese_present_uses_first_kana():
    assert derive_starters("Led Zeppelin", "レッド・ツェッペリン") == ("L", "レ")
    assert derive_starters("Pink Floyd", "ピンク・フロイド") == ("P", "ピ")
    assert derive_starters("Queen", "クイーン") == ("Q", "ク")


def test_derive_starters_strips_leading_the_in_english():
    assert derive_starters("The Who", "ザ・フー") == ("W", "フ")
    assert derive_starters("The Beatles", None) == ("B", None)
    # Case-insensitive on "The"
    assert derive_starters("the doors", None) == ("D", None)


def test_derive_starters_strips_leading_za_dot_in_japanese():
    # "ザ・" (za + middle dot) is the Japanese "The"; strip it before
    # taking the first character.
    assert derive_starters("The Rolling Stones",
                           "ザ・ローリング・ストーンズ") == ("R", "ロ")


def test_derive_starters_returns_question_mark_for_empty_english():
    assert derive_starters("", None) == ("?", None)


def test_derive_starters_uppercases_latin():
    assert derive_starters("madonna", "マドンナ") == ("M", "マ")


def test_wishlistdb_creates_v1_3_schema_on_init(temp_home):
    db_path = temp_home / "wishlist.sqlite"
    WishlistDB(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(wishlist)")}
    finally:
        conn.close()
    assert "artist_en" in cols
    assert "artist_ja" in cols
    assert "starter_latin" in cols
    assert "starter_kana" in cols
    assert "album_en" in cols
    assert "year" in cols
    assert "dedup_key" in cols
    assert "mention_count" in cols


def test_upsert_album_inserts_new_row(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    inserted = db.upsert_album(
        WantedAlbum(artist="Led Zeppelin", artist_ja="レッド・ツェッペリン",
                    album="Led Zeppelin II", year=1969),
        query="top 70s rock",
        seen_at="2026-05-15",
    )
    assert inserted is True
    assert db.count() == 1
    entries = db.list(limit=None)
    e = entries[0]
    assert e.artist_en == "Led Zeppelin"
    assert e.artist_ja == "レッド・ツェッペリン"
    assert e.album_en == "Led Zeppelin II"
    assert e.year == 1969
    assert e.starter_latin == "L"
    assert e.starter_kana == "レ"
    assert e.mention_count == 1
    assert e.queries_seen == ["top 70s rock"]


def test_upsert_album_same_album_increments_mention_count(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    a = WantedAlbum(artist="Led Zeppelin", artist_ja="レッド・ツェッペリン",
                    album="Led Zeppelin II", year=1969)
    db.upsert_album(a, query="q1", seen_at="2026-05-14")
    inserted = db.upsert_album(a, query="q2", seen_at="2026-05-15")
    assert inserted is False
    entries = db.list(limit=None)
    assert len(entries) == 1
    assert entries[0].mention_count == 2
    assert sorted(entries[0].queries_seen) == ["q1", "q2"]
    assert entries[0].first_seen == "2026-05-14"
    assert entries[0].last_seen == "2026-05-15"


def test_upsert_album_uses_normalized_dedup_key(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(
        WantedAlbum(artist="Led Zeppelin", artist_ja=None,
                    album="Led Zeppelin II", year=1969),
        query="q1", seen_at="2026-05-15",
    )
    # Same album, slightly different spelling — should dedup
    db.upsert_album(
        WantedAlbum(artist="led zeppelin", artist_ja=None,
                    album="led zeppelin ii", year=None),
        query="q2", seen_at="2026-05-15",
    )
    assert db.count() == 1


def test_upsert_album_handles_no_japanese_name(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(
        WantedAlbum(artist="AC/DC", artist_ja=None,
                    album="Back in Black", year=1980),
        query="q", seen_at="2026-05-15",
    )
    e = db.list(limit=None)[0]
    assert e.artist_ja is None
    assert e.starter_kana is None
    assert e.starter_latin == "A"


def test_list_sort_mentions_orders_by_count_desc(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(WantedAlbum("Z", None, "ZA", None), "q", "2026-05-14")
    db.upsert_album(WantedAlbum("A", None, "AA", None), "q1", "2026-05-15")
    db.upsert_album(WantedAlbum("A", None, "AA", None), "q2", "2026-05-15")
    entries = db.list(limit=None, sort="mentions")
    names = [e.artist_en for e in entries]
    assert names == ["A", "Z"]  # A has 2 mentions, Z has 1


def test_list_sort_latin_orders_alphabetically(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(WantedAlbum("Pink Floyd", "ピンク・フロイド", "P", None), "q", "2026-05-15")
    db.upsert_album(WantedAlbum("AC/DC", None, "A", None), "q1", "2026-05-15")
    db.upsert_album(
        WantedAlbum("Led Zeppelin", "レッド・ツェッペリン", "L", None),
        "q1", "2026-05-15",
    )
    entries = db.list(limit=None, sort="latin")
    starters = [e.starter_latin for e in entries]
    assert starters == ["A", "L", "P"]


def test_list_sort_kana_orders_japanese_then_latin_only(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(WantedAlbum("Queen", "クイーン", "Q", None), "q", "2026-05-15")
    db.upsert_album(WantedAlbum("AC/DC", None, "A", None), "q", "2026-05-15")
    db.upsert_album(
        WantedAlbum("Led Zeppelin", "レッド・ツェッペリン", "L", None),
        "q", "2026-05-15",
    )
    entries = db.list(limit=None, sort="kana")
    # Japanese starters first (sorted), then Latin-only entries last.
    starters_kana = [e.starter_kana for e in entries]
    assert starters_kana[-1] is None  # AC/DC last
    # The first two are kana entries; we don't assert their inner order
    # beyond "Japanese entries appear before Latin-only entries".
    assert all(s is not None for s in starters_kana[:-1])


def test_list_default_limit_50(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    for i in range(60):
        db.upsert_album(
            WantedAlbum(f"Artist {i:03d}", None, f"Album {i:03d}", None),
            "q", "2026-05-15",
        )
    assert len(db.list()) == 50
    assert len(db.list(limit=None)) == 60


def test_list_since_filters_to_recent(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(WantedAlbum("Old", None, "Old Album", None), "q", "2026-04-01")
    db.upsert_album(WantedAlbum("New", None, "New Album", None), "q", "2026-05-10")
    cutoff = _dt.date(2026, 5, 1)
    entries = db.list(since=cutoff, limit=None)
    assert [e.artist_en for e in entries] == ["New"]


def test_remove_matching_deletes_only_listed_keys(temp_home):
    from moodlist.wishlist import normalize_track_name
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert_album(WantedAlbum("A", None, "A1", None), "q", "2026-05-15")
    db.upsert_album(WantedAlbum("B", None, "B1", None), "q", "2026-05-15")
    db.upsert_album(WantedAlbum("C", None, "C1", None), "q", "2026-05-15")
    removed = db.remove_matching({
        normalize_track_name("A - A1"),
        normalize_track_name("C - C1"),
    })
    assert removed == 2
    names = [e.artist_en for e in db.list(limit=None)]
    assert names == ["B"]


def test_count_returns_total_rows(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    assert db.count() == 0
    db.upsert_album(WantedAlbum("A", None, "A1", None), "q", "2026-05-15")
    db.upsert_album(WantedAlbum("B", None, "B1", None), "q", "2026-05-15")
    assert db.count() == 2


def test_resolve_albums_returns_wantedalbum_list(mocker):
    from moodlist.wishlist import resolve_albums

    mocker.patch("moodlist.wishlist.llm.call", return_value={
        "albums": [
            {"artist": "Led Zeppelin", "artist_ja": "レッド・ツェッペリン",
             "album": "Led Zeppelin II", "year": 1969},
            {"artist": "AC/DC", "artist_ja": None,
             "album": "Back in Black", "year": 1980},
        ]
    })
    result = resolve_albums(
        ["Led Zeppelin - Whole Lotta Love", "AC/DC - Back in Black"],
        api_key="k", model="m",
    )
    assert len(result) == 2
    assert result[0].artist == "Led Zeppelin"
    assert result[0].artist_ja == "レッド・ツェッペリン"
    assert result[0].album == "Led Zeppelin II"
    assert result[0].year == 1969
    assert result[1].artist_ja is None
    assert result[1].year == 1980


def test_resolve_albums_skips_malformed_entries(mocker):
    from moodlist.wishlist import resolve_albums

    mocker.patch("moodlist.wishlist.llm.call", return_value={
        "albums": [
            {"artist": "Good", "artist_ja": None, "album": "OK", "year": 2000},
            "not a dict",
            {"album": "no artist"},
            {"artist": "no album"},
        ]
    })
    result = resolve_albums(
        ["a", "b", "c", "d"], api_key="k", model="m",
    )
    assert len(result) == 1
    assert result[0].album == "OK"


def test_resolve_albums_returns_empty_on_empty_input():
    from moodlist.wishlist import resolve_albums
    # No mocker patch — should short-circuit before hitting llm.call.
    result = resolve_albums([], api_key="k", model="m")
    assert result == []


def test_resolve_albums_passes_strings_in_prompt(mocker):
    """The Haiku call must include all track strings somewhere in the user
    message so the model has them to resolve."""
    from moodlist.wishlist import resolve_albums

    captured: dict = {}
    def fake_call(**kwargs):
        captured.update(kwargs)
        return {"albums": []}
    mocker.patch("moodlist.wishlist.llm.call", side_effect=fake_call)

    resolve_albums(["Led Zeppelin - Whole Lotta Love"], api_key="k", model="m")
    user_text = " ".join(
        b["text"] for b in captured["user_blocks"]
        if isinstance(b, dict) and "text" in b
    )
    assert "Led Zeppelin - Whole Lotta Love" in user_text
