from pathlib import Path

from moodlist.cache import QueryCache, normalize_query


def test_normalize_lowercases_and_trims_and_collapses_whitespace():
    assert normalize_query("  Top 80s   METAL ") == "top 80s metal"


def test_normalize_unicode_nfkc():
    # NFKC normalizes fullwidth letters AND fullwidth solidus to ASCII equivalents.
    # Plan spec listed "ac／dc rocks" but U+FF0F (fullwidth solidus) also maps to
    # U+002F (solidus) under NFKC, so the correct expectation is "ac/dc rocks".
    assert normalize_query("ＡＣ／ＤＣ rocks") == "ac/dc rocks"


def test_store_then_lookup_returns_path(temp_home):
    cache = QueryCache(temp_home / "query-cache.sqlite")
    cache.store("top 80s metal", "ver1",
                Path("/tmp/2026-top-80s-metal.m3u8"))
    hit = cache.lookup("Top 80s Metal", "ver1")
    assert hit == Path("/tmp/2026-top-80s-metal.m3u8")


def test_lookup_misses_on_different_library_version(temp_home):
    cache = QueryCache(temp_home / "query-cache.sqlite")
    cache.store("q", "v1", Path("/tmp/x.m3u8"))
    assert cache.lookup("q", "v2") is None


def test_lookup_hit_increments_hit_count(temp_home):
    cache = QueryCache(temp_home / "query-cache.sqlite")
    cache.store("q", "v", Path("/tmp/x.m3u8"))
    cache.lookup("q", "v")
    cache.lookup("q", "v")
    assert cache.hit_count("q", "v") == 2


def test_store_twice_overwrites_existing_row(temp_home):
    cache = QueryCache(temp_home / "query-cache.sqlite")
    cache.store("q", "v", Path("/tmp/a.m3u8"))
    cache.store("q", "v", Path("/tmp/b.m3u8"))
    assert cache.lookup("q", "v") == Path("/tmp/b.m3u8")
