from __future__ import annotations

import datetime as _dt
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Tail patterns we treat as version markers and strip before final normalization.
# Order matters: longer/more specific first so partial matches don't preempt them.
_VERSION_TAIL_RE = re.compile(
    r"""
    \s*
    \(?                                   # optional opening paren
    (?:
        feat\.?\s.+                      |  # "feat. X" or "feat X"
        ft\.?\s.+                        |  # "ft. X"
        live                             |
        demo                             |
        b-?side                          |
        alternate\s+version              |
        extended\s+(?:mix|version)       |
        remaster(?:ed)?(?:\s+\d{4})?     |
        remix
    )
    \)?                                   # optional closing paren
    \s*$                                  # must be at end of string
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Punctuation to replace with a space before whitespace-collapse.
# Includes ASCII punctuation plus en/em dashes, fullwidth slash.
_PUNCT_RE = re.compile(r"""[.,;:"''`!?()\[\]{}\-—–/\\|]""")


def normalize_track_name(s: str) -> str:
    """Canonical key for a track name.

    Steps:
      1. NFKC unicode normalization (fullwidth → ASCII, ligatures, etc.)
      2. Strip version-marker tails like "(live)", "(remastered)",
         "feat. X" — these denote different cuts of the same recording.
      3. Replace punctuation with whitespace.
      4. Lowercase.
      5. Collapse all whitespace runs to a single space.
      6. Strip leading/trailing whitespace.
    """
    s = unicodedata.normalize("NFKC", s)
    # Iteratively strip version tails (a track may have stacked tails)
    while True:
        new = _VERSION_TAIL_RE.sub("", s).rstrip()
        if new == s:
            break
        s = new
    s = _PUNCT_RE.sub(" ", s)
    s = s.lower()
    s = " ".join(s.split())
    return s


SCHEMA = """
CREATE TABLE IF NOT EXISTS wishlist (
    dedup_key      TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    mention_count  INTEGER NOT NULL DEFAULT 1,
    queries_seen   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS wishlist_last_seen ON wishlist (last_seen DESC);
CREATE INDEX IF NOT EXISTS wishlist_mentions  ON wishlist (mention_count DESC);
"""


@dataclass(frozen=True)
class WishlistEntry:
    dedup_key: str
    display_name: str
    first_seen: str
    last_seen: str
    mention_count: int
    queries_seen: list[str] = field(default_factory=list)


class WishlistDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
        finally:
            conn.close()
        # One-time migration from misses.log if wishlist is empty.
        if self.count() == 0:
            self._migrate_from_misses_log(self.db_path.parent / "misses.log")

    def _migrate_from_misses_log(self, log_path: Path) -> None:
        import sys
        if not log_path.exists():
            return
        try:
            content = log_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"wishlist migration: could not read {log_path}: {e}",
                  file=sys.stderr)
            return
        for line_num, line in enumerate(content.splitlines(), start=1):
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            date_str, query, display = parts[0], parts[1], parts[2]
            if not date_str.strip() or not query.strip() or not display.strip():
                continue
            try:
                self.upsert(display.strip(), query.strip(), date_str.strip())
            except Exception as e:
                print(
                    f"wishlist migration: skipping line {line_num}: {e}",
                    file=sys.stderr,
                )

    def upsert(self, display_name: str, query: str, seen_at: str) -> bool:
        """Insert or update one entry. Returns True if newly inserted,
        False if updated."""
        key = normalize_track_name(display_name)
        if not key:
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            existing = conn.execute(
                "SELECT queries_seen FROM wishlist WHERE dedup_key = ?",
                (key,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO wishlist "
                    "(dedup_key, display_name, first_seen, last_seen, "
                    " mention_count, queries_seen) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (key, display_name, seen_at, seen_at, query),
                )
                conn.commit()
                return True
            existing_queries = set(q for q in existing[0].split("\n") if q)
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
    ) -> list[WishlistEntry]:
        conn = sqlite3.connect(self.db_path)
        try:
            sql = (
                "SELECT dedup_key, display_name, first_seen, last_seen, "
                "       mention_count, queries_seen "
                "FROM wishlist"
            )
            params: list = []
            if since is not None:
                sql += " WHERE last_seen >= ?"
                params.append(since.isoformat())
            sql += " ORDER BY mention_count DESC, last_seen DESC"
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            rows = conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()
        return [
            WishlistEntry(
                dedup_key=r[0],
                display_name=r[1],
                first_seen=r[2],
                last_seen=r[3],
                mention_count=r[4],
                queries_seen=[q for q in r[5].split("\n") if q],
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
