from __future__ import annotations

import datetime as _dt
import sqlite3

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


def test_wishlistdb_creates_schema_on_init(temp_home):
    db_path = temp_home / "wishlist.sqlite"
    WishlistDB(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    assert ("wishlist",) in rows


def test_upsert_inserts_new_entry(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    inserted = db.upsert(
        display_name="Black Sabbath - Paranoid",
        query="top 80s metal",
        seen_at="2026-05-14",
    )
    assert inserted is True
    assert db.count() == 1


def test_upsert_existing_increments_mention_count(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Black Sabbath - Paranoid", "top 80s metal", "2026-05-14")
    inserted = db.upsert("Black Sabbath - Paranoid", "best metal", "2026-05-15")
    assert inserted is False
    entries = db.list(limit=None)
    assert len(entries) == 1
    assert entries[0].mention_count == 2


def test_upsert_existing_updates_last_seen(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Black Sabbath - Paranoid", "q1", "2026-05-14")
    db.upsert("Black Sabbath - Paranoid", "q2", "2026-05-20")
    entries = db.list(limit=None)
    assert entries[0].last_seen == "2026-05-20"
    assert entries[0].first_seen == "2026-05-14"


def test_upsert_appends_unique_queries_to_queries_seen(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Track A", "q1", "2026-05-14")
    db.upsert("Track A", "q2", "2026-05-15")
    db.upsert("Track A", "q1", "2026-05-16")  # duplicate query
    entries = db.list(limit=None)
    assert sorted(entries[0].queries_seen) == ["q1", "q2"]


def test_upsert_uses_normalized_dedup_key(temp_home):
    """Two display_name variants that normalize identically dedup."""
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Black Sabbath - Paranoid", "q1", "2026-05-14")
    db.upsert("black sabbath – paranoid", "q2", "2026-05-15")
    assert db.count() == 1


def test_list_orders_by_mentions_then_recency(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Track A", "q1", "2026-05-14")
    db.upsert("Track B", "q1", "2026-05-15")
    db.upsert("Track B", "q2", "2026-05-15")          # B has 2 mentions
    db.upsert("Track C", "q1", "2026-05-16")          # C is most recent, 1 mention
    entries = db.list(limit=None)
    names = [e.display_name for e in entries]
    assert names == ["Track B", "Track C", "Track A"]


def test_list_default_limit_50(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    for i in range(60):
        db.upsert(f"Track {i}", "q", "2026-05-14")
    assert len(db.list()) == 50
    assert len(db.list(limit=None)) == 60


def test_list_since_filters_to_recent(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Old", "q", "2026-04-01")
    db.upsert("New", "q", "2026-05-10")
    cutoff = _dt.date(2026, 5, 1)
    entries = db.list(since=cutoff, limit=None)
    assert [e.display_name for e in entries] == ["New"]


def test_remove_matching_deletes_only_listed_keys(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    db.upsert("Black Sabbath - Paranoid", "q", "2026-05-14")
    db.upsert("Iron Maiden - The Trooper", "q", "2026-05-14")
    db.upsert("Metallica - One", "q", "2026-05-14")
    removed = db.remove_matching({
        normalize_track_name("Black Sabbath - Paranoid"),
        normalize_track_name("Metallica - One"),
    })
    assert removed == 2
    names = [e.display_name for e in db.list(limit=None)]
    assert names == ["Iron Maiden - The Trooper"]


def test_count_returns_total_rows(temp_home):
    db = WishlistDB(temp_home / "w.sqlite")
    assert db.count() == 0
    db.upsert("Track A", "q", "2026-05-14")
    db.upsert("Track B", "q", "2026-05-14")
    assert db.count() == 2


def test_migration_from_misses_log_dedupes(temp_home):
    """A misses.log with duplicates produces a deduped wishlist."""
    log = temp_home / "misses.log"
    log.write_text(
        "2026-05-14\ttop 80s metal\tBlack Sabbath - Paranoid\n"
        "2026-05-14\tbest metal\tBlack Sabbath - Paranoid\n"
        "2026-05-14\tbest metal\tIron Maiden - Run to the Hills\n"
    )
    db = WishlistDB(temp_home / "wishlist.sqlite")
    assert db.count() == 2
    entries = {e.display_name: e for e in db.list(limit=None)}
    assert entries["Black Sabbath - Paranoid"].mention_count == 2
    assert sorted(entries["Black Sabbath - Paranoid"].queries_seen) == \
        ["best metal", "top 80s metal"]


def test_migration_does_not_run_when_wishlist_already_populated(temp_home):
    log = temp_home / "misses.log"
    log.write_text("2026-05-14\tq\tTrack X\n")
    db = WishlistDB(temp_home / "wishlist.sqlite")
    assert db.count() == 1  # migration ran once

    # Add more to the log, recreate WishlistDB — should NOT re-import
    log.write_text(log.read_text() + "2026-05-14\tq\tTrack Y\n")
    db2 = WishlistDB(temp_home / "wishlist.sqlite")
    assert db2.count() == 1  # still 1; migration is idempotent


def test_migration_skips_malformed_lines_without_crashing(temp_home, capsys):
    log = temp_home / "misses.log"
    log.write_text(
        "2026-05-14\tgood query\tGood Track\n"
        "this is a malformed line with no tabs\n"
        "\t\t\n"
        "2026-05-15\tanother query\tAnother Track\n"
    )
    db = WishlistDB(temp_home / "wishlist.sqlite")
    assert db.count() == 2
    names = [e.display_name for e in db.list(limit=None)]
    assert "Good Track" in names
    assert "Another Track" in names
