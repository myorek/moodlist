from __future__ import annotations

import datetime as _dt
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import llm
from .types import WantedAlbum

# ── normalization ──────────────────────────────────────────────────

_VERSION_TAIL_RE = re.compile(
    r"""
    \s*
    \(?
    (?:
        feat\.?\s.+                      |
        ft\.?\s.+                        |
        live                             |
        demo                             |
        b-?side                          |
        alternate\s+version              |
        extended\s+(?:mix|version)       |
        remaster(?:ed)?(?:\s+\d{4})?     |
        remix
    )
    \)?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PUNCT_RE = re.compile(r"""[.,;:"''`!?()\[\]{}\-—–/\\|]""")


def normalize_track_name(s: str) -> str:
    """Canonical key for a track name or 'artist - album' string."""
    s = unicodedata.normalize("NFKC", s)
    while True:
        new = _VERSION_TAIL_RE.sub("", s).rstrip()
        if new == s:
            break
        s = new
    s = _PUNCT_RE.sub(" ", s)
    s = s.lower()
    s = " ".join(s.split())
    return s


def derive_starters(
    artist_en: str, artist_ja: str | None
) -> tuple[str, str | None]:
    """Compute the bin starter character for an artist."""
    latin_source = artist_en
    if latin_source.lower().startswith("the "):
        latin_source = latin_source[4:]
    starter_latin = latin_source[:1].upper() if latin_source else "?"

    starter_kana: str | None = None
    if artist_ja:
        kana_source = artist_ja
        if kana_source.startswith("ザ・"):
            kana_source = kana_source[2:]
        starter_kana = kana_source[:1] if kana_source else None
    return starter_latin, starter_kana


# ── schema ─────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS wishlist (
    dedup_key       TEXT PRIMARY KEY,
    artist_en       TEXT NOT NULL,
    artist_ja       TEXT,
    starter_latin   TEXT NOT NULL,
    starter_kana    TEXT,
    album_en        TEXT NOT NULL,
    year            INTEGER,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    mention_count   INTEGER NOT NULL DEFAULT 1,
    queries_seen    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS wishlist_mentions ON wishlist (mention_count DESC);
CREATE INDEX IF NOT EXISTS wishlist_starter_kana ON wishlist (starter_kana);
CREATE INDEX IF NOT EXISTS wishlist_starter_latin ON wishlist (starter_latin);
"""


@dataclass(frozen=True)
class WishlistEntry:
    dedup_key: str
    artist_en: str
    artist_ja: str | None
    starter_latin: str
    starter_kana: str | None
    album_en: str
    year: int | None
    first_seen: str
    last_seen: str
    mention_count: int
    queries_seen: list[str] = field(default_factory=list)


def _album_dedup_key(artist_en: str, album_en: str) -> str:
    return normalize_track_name(f"{artist_en} - {album_en}")


class WishlistDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # If a v1.2 table exists, migrate before creating v1.3 schema
        if self._detect_v1_2_schema():
            self._migrate_v1_2_to_v1_3()
            return
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    def _detect_v1_2_schema(self) -> bool:
        """Return True if the existing wishlist table looks like v1.2
        (has display_name column, lacks artist_en)."""
        if not self.db_path.exists():
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            cols = {
                row[1] for row in conn.execute("PRAGMA table_info(wishlist)")
            }
        finally:
            conn.close()
        return "display_name" in cols and "artist_en" not in cols

    def _migrate_v1_2_to_v1_3(self) -> None:
        """Resolve v1.2 track-level rows into v1.3 album rows via a
        single Haiku call. On any failure, leave v1.2 table intact and
        return; retries on next construction."""
        from .config import load_config
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT display_name, first_seen, last_seen, queries_seen "
                "FROM wishlist"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            # No data; just create the new schema and drop the old table
            conn = sqlite3.connect(self.db_path)
            try:
                conn.executescript("DROP TABLE wishlist;")
                conn.executescript(SCHEMA)
            finally:
                conn.close()
            return

        try:
            cfg = load_config()
        except Exception as e:
            print(
                f"wishlist: v1.3 migration deferred (config error: {e})",
                file=sys.stderr,
            )
            return

        track_strings = [r[0] for r in rows]
        try:
            albums = resolve_albums(
                track_strings, api_key=cfg.api_key, model=cfg.model,
            )
        except Exception as e:
            print(
                f"wishlist: v1.3 migration deferred ({e}); will retry next run",
                file=sys.stderr,
            )
            return

        # Aggregate stats: global min/max across all source rows.
        all_first = min(r[1] for r in rows)
        all_last = max(r[2] for r in rows)

        # Create new schema (rename old table to v1_2 backup first)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript("""
                ALTER TABLE wishlist RENAME TO wishlist_v1_2_backup;
            """)
            conn.executescript(SCHEMA)

            # Insert each resolved album. mention_count divides source rows
            # evenly across resolved albums (minimum 1).
            n_albums = max(1, len(albums))
            per_album = max(1, len(rows) // n_albums)
            for album in albums:
                key = _album_dedup_key(album.artist, album.album)
                if not key:
                    continue
                starter_latin, starter_kana = derive_starters(
                    album.artist, album.artist_ja
                )
                conn.execute(
                    "INSERT OR IGNORE INTO wishlist "
                    "(dedup_key, artist_en, artist_ja, starter_latin, "
                    " starter_kana, album_en, year, first_seen, last_seen, "
                    " mention_count, queries_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')",
                    (key, album.artist, album.artist_ja, starter_latin,
                     starter_kana, album.album, album.year,
                     all_first, all_last, per_album),
                )
            conn.commit()
            print(
                f"wishlist: migrated {len(rows)} v1.2 entries → "
                f"{len(albums)} v1.3 albums "
                f"(old table preserved as wishlist_v1_2_backup)",
                file=sys.stderr,
            )
        finally:
            conn.close()

    def upsert_album(
        self, album: WantedAlbum, query: str, seen_at: str
    ) -> bool:
        """Insert or update one album row. Returns True if newly inserted,
        False if updated."""
        if not album.artist or not album.album:
            return False
        key = _album_dedup_key(album.artist, album.album)
        if not key:
            return False
        starter_latin, starter_kana = derive_starters(
            album.artist, album.artist_ja
        )
        conn = sqlite3.connect(self.db_path)
        try:
            existing = conn.execute(
                "SELECT queries_seen FROM wishlist WHERE dedup_key = ?",
                (key,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO wishlist "
                    "(dedup_key, artist_en, artist_ja, starter_latin, "
                    " starter_kana, album_en, year, first_seen, last_seen, "
                    " mention_count, queries_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (key, album.artist, album.artist_ja, starter_latin,
                     starter_kana, album.album, album.year,
                     seen_at, seen_at, query),
                )
                conn.commit()
                return True
            existing_queries = {q for q in existing[0].split("\n") if q}
            existing_queries.add(query)
            conn.execute(
                "UPDATE wishlist "
                "SET mention_count = mention_count + 1, "
                "    last_seen = MAX(last_seen, ?), "
                "    queries_seen = ? "
                "WHERE dedup_key = ?",
                (seen_at, "\n".join(sorted(existing_queries)), key),
            )
            conn.commit()
            return False
        finally:
            conn.close()

    def remove_matching(self, library_keys: set[str]) -> int:
        if not library_keys:
            return 0
        conn = sqlite3.connect(self.db_path)
        try:
            placeholders = ",".join("?" * len(library_keys))
            cur = conn.execute(
                f"DELETE FROM wishlist WHERE dedup_key IN ({placeholders})",
                tuple(library_keys),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def list(
        self,
        *,
        limit: int | None = 50,
        since: _dt.date | None = None,
        sort: str = "mentions",
    ) -> list[WishlistEntry]:
        if sort not in ("mentions", "latin", "kana"):
            raise ValueError(
                f"sort must be one of: mentions, latin, kana (got {sort!r})"
            )
        conn = sqlite3.connect(self.db_path)
        try:
            sql = (
                "SELECT dedup_key, artist_en, artist_ja, starter_latin, "
                "       starter_kana, album_en, year, first_seen, last_seen, "
                "       mention_count, queries_seen "
                "FROM wishlist"
            )
            params: list = []
            if since is not None:
                sql += " WHERE last_seen >= ?"
                params.append(since.isoformat())
            if sort == "mentions":
                sql += " ORDER BY mention_count DESC, last_seen DESC"
            elif sort == "latin":
                sql += " ORDER BY starter_latin ASC, artist_en ASC"
            elif sort == "kana":
                # Japanese (kana not null) first, then Latin-only.
                sql += (
                    " ORDER BY (starter_kana IS NULL) ASC, "
                    "starter_kana ASC, artist_en ASC"
                )
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()
        return [
            WishlistEntry(
                dedup_key=r[0],
                artist_en=r[1],
                artist_ja=r[2],
                starter_latin=r[3],
                starter_kana=r[4],
                album_en=r[5],
                year=r[6],
                first_seen=r[7],
                last_seen=r[8],
                mention_count=r[9],
                queries_seen=[q for q in r[10].split("\n") if q],
            )
            for r in rows
        ]

    def count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM wishlist").fetchone()
        finally:
            conn.close()
        return int(row[0])


_RESOLVER_SYSTEM_PROMPT = """\
You are a music-catalog resolver. For each input string of the form
"Artist - Track Title" (or sometimes a bare title), identify:
  - artist: canonical artist name (Latin script)
  - artist_ja: standard Japanese katakana transliteration, or null
    if the artist isn't commonly rendered in Japanese (AC/DC, U2)
  - album: the canonical studio album the track appears on
  - year: original release year of the album (not a reissue); null if unsure

Deduplicate: if multiple input strings resolve to the same album,
return ONE record. Output JSON only:

  {"albums": [{"artist": string, "artist_ja": string | null,
               "album": string, "year": int | null}, ...]}
"""


def resolve_albums(
    track_strings: list[str],
    *,
    api_key: str,
    model: str,
) -> list[WantedAlbum]:
    """Resolve a list of 'Artist - Track' strings into canonical album
    records via a single Haiku call. Returns a deduplicated list."""
    if not track_strings:
        return []

    user_text = (
        "Resolve each of these track strings to its canonical album:\n\n"
        + "\n".join(f"- {s}" for s in track_strings)
    )
    raw = llm.call(
        api_key=api_key,
        model=model,
        system=_RESOLVER_SYSTEM_PROMPT,
        user_blocks=[{"type": "text", "text": user_text}],
        temperature=0.0,
        max_tokens=2048,
    )

    out: list[WantedAlbum] = []
    for entry in raw.get("albums", []) or []:
        if not isinstance(entry, dict):
            continue
        artist = entry.get("artist")
        album = entry.get("album")
        if not isinstance(artist, str) or not artist.strip():
            continue
        if not isinstance(album, str) or not album.strip():
            continue
        artist_ja_raw = entry.get("artist_ja")
        artist_ja = artist_ja_raw if isinstance(artist_ja_raw, str) \
            and artist_ja_raw.strip() else None
        year_raw = entry.get("year")
        year = year_raw if isinstance(year_raw, int) else None
        out.append(WantedAlbum(artist=artist.strip(), artist_ja=artist_ja,
                               album=album.strip(), year=year))
    return out
