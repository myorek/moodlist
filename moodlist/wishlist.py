from __future__ import annotations

import datetime as _dt
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

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
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
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
