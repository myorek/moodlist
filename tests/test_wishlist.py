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


def _make_v1_2_wishlist(db_path, rows):
    """Create a wishlist.sqlite with v1.2 schema and the given rows.
    Each row tuple: (dedup_key, display_name, first_seen, last_seen)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE wishlist (
                dedup_key      TEXT PRIMARY KEY,
                display_name   TEXT NOT NULL,
                first_seen     TEXT NOT NULL,
                last_seen      TEXT NOT NULL,
                mention_count  INTEGER NOT NULL DEFAULT 1,
                queries_seen   TEXT NOT NULL DEFAULT ''
            );
        """)
        for dedup, name, first, last in rows:
            conn.execute(
                "INSERT INTO wishlist "
                "(dedup_key, display_name, first_seen, last_seen, "
                " mention_count, queries_seen) VALUES (?, ?, ?, ?, 1, '')",
                (dedup, name, first, last),
            )
        conn.commit()
    finally:
        conn.close()


def _write_config_for_migration(temp_home):
    """Helper: write a config.toml so the migration can read the API key."""
    cfg = temp_home / "config.toml"
    cfg.write_text(
        '[anthropic]\n'
        'api_key = "sk-test"\n'
        'model   = "claude-haiku-4-5-20251001"\n'
        '\n'
        '[library]\n'
        'root = "~/Music"\n'
        'extensions = ["flac"]\n'
        '\n'
        '[foobar2000]\n'
        'app = "foobar2000"\n'
        '\n'
        '[playlist]\n'
        'default_count = 20\n'
        'temperature   = 0.4\n'
    )


def test_migration_detects_v1_2_schema(temp_home, mocker):
    """v1.2 schema (display_name column, no artist_en) triggers migration."""
    db_path = temp_home / "wishlist.sqlite"
    _make_v1_2_wishlist(db_path, [
        ("led zeppelin whole lotta love",
         "Led Zeppelin - Whole Lotta Love", "2026-05-14", "2026-05-15"),
    ])
    # Mock resolver to return one album record
    mocker.patch("moodlist.wishlist.resolve_albums", return_value=[
        WantedAlbum("Led Zeppelin", "レッド・ツェッペリン",
                    "Led Zeppelin II", 1969),
    ])
    _write_config_for_migration(temp_home)

    db = WishlistDB(db_path)
    # After migration the new schema is in place
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(wishlist)")}
    finally:
        conn.close()
    assert "artist_en" in cols
    # Migrated row present
    entries = db.list(limit=None)
    assert len(entries) == 1
    assert entries[0].artist_en == "Led Zeppelin"
    assert entries[0].album_en == "Led Zeppelin II"


def test_migration_aggregates_tracks_into_albums(temp_home, mocker):
    """Two tracks from the same album collapse to one wishlist row."""
    db_path = temp_home / "wishlist.sqlite"
    _make_v1_2_wishlist(db_path, [
        ("zep1", "Led Zeppelin - Whole Lotta Love", "2026-05-14", "2026-05-14"),
        ("zep2", "Led Zeppelin - Heartbreaker", "2026-05-15", "2026-05-15"),
    ])
    # Both resolve to the same album → resolver returns dedup'd list
    mocker.patch("moodlist.wishlist.resolve_albums", return_value=[
        WantedAlbum("Led Zeppelin", "レッド・ツェッペリン",
                    "Led Zeppelin II", 1969),
    ])
    _write_config_for_migration(temp_home)

    db = WishlistDB(db_path)
    entries = db.list(limit=None)
    assert len(entries) == 1
    # mention_count aggregates: 2 source rows → 2 mentions
    assert entries[0].mention_count == 2
    # first_seen is the earliest, last_seen is the latest
    assert entries[0].first_seen == "2026-05-14"
    assert entries[0].last_seen == "2026-05-15"


def test_migration_idempotent_when_v1_3_schema_already_present(temp_home, mocker):
    """Re-instantiating WishlistDB on a v1.3 table does not re-migrate."""
    db_path = temp_home / "wishlist.sqlite"
    # First, set up a v1.3 schema with one row
    db1 = WishlistDB(db_path)
    db1.upsert_album(
        WantedAlbum("A", None, "X", None), "q", "2026-05-15",
    )
    assert db1.count() == 1

    # resolver should NOT be called this time
    resolver_mock = mocker.patch("moodlist.wishlist.resolve_albums")
    db2 = WishlistDB(db_path)
    assert db2.count() == 1
    resolver_mock.assert_not_called()


def test_migration_skipped_when_resolver_fails(temp_home, mocker):
    """If the Haiku resolver raises, the v1.2 data is preserved in a
    pending-retry table and the v1.3 schema is created so subsequent
    operations don't crash. Migration retries on the next run."""
    db_path = temp_home / "wishlist.sqlite"
    _make_v1_2_wishlist(db_path, [
        ("zep1", "Led Zeppelin - Whole Lotta Love", "2026-05-14", "2026-05-15"),
    ])
    mocker.patch("moodlist.wishlist.resolve_albums",
                 side_effect=RuntimeError("network down"))
    _write_config_for_migration(temp_home)

    # Construction does NOT crash even though resolver failed
    db = WishlistDB(db_path)

    # The live `wishlist` table now has v1.3 schema (empty).
    conn = sqlite3.connect(db_path)
    try:
        live_cols = {row[1] for row in conn.execute("PRAGMA table_info(wishlist)")}
        pending_cols = {row[1] for row in conn.execute(
            "PRAGMA table_info(wishlist_v1_2_pending)"
        )}
    finally:
        conn.close()
    assert "artist_en" in live_cols
    assert "display_name" not in live_cols
    # The v1.2 data is preserved under the pending name.
    assert "display_name" in pending_cols
    # No crash on list/count even though migration deferred.
    assert db.count() == 0
    assert db.list(limit=None) == []


def test_migration_retries_from_pending_on_next_init(temp_home, mocker):
    """If a migration was deferred (data left in wishlist_v1_2_pending),
    the next WishlistDB construction retries the migration and, on
    success, populates the v1.3 wishlist + renames pending to backup."""
    db_path = temp_home / "wishlist.sqlite"
    _make_v1_2_wishlist(db_path, [
        ("zep1", "Led Zeppelin - Whole Lotta Love", "2026-05-14", "2026-05-15"),
    ])
    _write_config_for_migration(temp_home)

    # First attempt: resolver fails → pending stash created
    mocker.patch("moodlist.wishlist.resolve_albums",
                 side_effect=RuntimeError("network down"))
    WishlistDB(db_path)
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='wishlist_v1_2_pending'"
        ).fetchone() is not None
    finally:
        conn.close()

    # Second attempt: resolver succeeds → migration completes
    mocker.patch("moodlist.wishlist.resolve_albums", return_value=[
        WantedAlbum("Led Zeppelin", "レッド・ツェッペリン",
                    "Led Zeppelin II", 1969),
    ])
    db = WishlistDB(db_path)
    entries = db.list(limit=None)
    assert len(entries) == 1
    assert entries[0].artist_en == "Led Zeppelin"

    # Pending table is gone (renamed to backup); backup is present.
    conn = sqlite3.connect(db_path)
    try:
        pending = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='wishlist_v1_2_pending'"
        ).fetchone()
        backup = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='wishlist_v1_2_backup'"
        ).fetchone()
    finally:
        conn.close()
    assert pending is None
    assert backup is not None
