from __future__ import annotations

import datetime as _dt
import hashlib
import sqlite3
import unicodedata
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS query_cache (
    query_hash       TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    library_version  TEXT NOT NULL,
    playlist_path    TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    last_used_at     TEXT NOT NULL,
    hit_count        INTEGER NOT NULL DEFAULT 0
);
"""


def normalize_query(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.lower().strip()
    s = " ".join(s.split())
    return s


def _hash(normalized: str, library_version: str) -> str:
    payload = f"{normalized}|{library_version}".encode()
    return hashlib.sha256(payload).hexdigest()


class QueryCache:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")

    def store(self, query: str, library_version: str, playlist_path: Path) -> None:
        norm = normalize_query(query)
        h = _hash(norm, library_version)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO query_cache "
            "(query_hash, normalized_query, library_version, playlist_path, "
            " created_at, last_used_at, hit_count) "
            "VALUES (?,?,?,?,?,?,0) "
            "ON CONFLICT(query_hash) DO UPDATE SET "
            "  playlist_path = excluded.playlist_path, "
            "  last_used_at = excluded.last_used_at",
            (h, norm, library_version, str(playlist_path),
             self._now(), self._now()),
        )
        conn.commit()
        conn.close()

    def lookup(self, query: str, library_version: str) -> Path | None:
        norm = normalize_query(query)
        h = _hash(norm, library_version)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT playlist_path FROM query_cache WHERE query_hash = ?", (h,)
        ).fetchone()
        if row is None:
            conn.close()
            return None
        conn.execute(
            "UPDATE query_cache "
            "SET hit_count = hit_count + 1, last_used_at = ? "
            "WHERE query_hash = ?",
            (self._now(), h),
        )
        conn.commit()
        conn.close()
        return Path(row[0])

    def hit_count(self, query: str, library_version: str) -> int:
        norm = normalize_query(query)
        h = _hash(norm, library_version)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT hit_count FROM query_cache WHERE query_hash = ?", (h,)
        ).fetchone()
        conn.close()
        return int(row[0]) if row else 0
