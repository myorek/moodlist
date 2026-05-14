from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from mutagen.flac import FLAC

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    artist       TEXT NOT NULL,
    title        TEXT NOT NULL,
    album        TEXT NOT NULL DEFAULT '',
    year         INTEGER,
    path         TEXT NOT NULL UNIQUE,
    duration_sec INTEGER NOT NULL DEFAULT 0
);
"""


def _first_tag(tags, key: str, default: str = "") -> str:
    vals = tags.get(key) or tags.get(key.lower())
    if not vals:
        return default
    return vals[0] if isinstance(vals, list) else str(vals)


def _parse_year(raw: str) -> int | None:
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())[:4]
    return int(digits) if len(digits) == 4 else None


class Indexer:
    def __init__(self, library_root: Path, moodlist_dir: Path):
        self.library_root = Path(library_root).expanduser()
        self.moodlist_dir = Path(moodlist_dir)
        self.db_path = self.moodlist_dir / "library.sqlite"

    def build(self) -> int:
        self.moodlist_dir.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            self.db_path.unlink()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA)
            n = 0
            for path in sorted(self.library_root.rglob("*.flac")):
                try:
                    f = FLAC(str(path))
                except Exception as e:
                    print(f"moodlist: skipping {path}: {e}", file=sys.stderr)
                    continue
                artist = _first_tag(f.tags, "ARTIST") if f.tags else ""
                title = _first_tag(f.tags, "TITLE") if f.tags else path.stem
                album = _first_tag(f.tags, "ALBUM") if f.tags else ""
                year = _parse_year(_first_tag(f.tags, "DATE") if f.tags else "")
                dur = int(f.info.length) if f.info else 0
                conn.execute(
                    "INSERT INTO tracks(artist,title,album,year,path,duration_sec)"
                    " VALUES (?,?,?,?,?,?)",
                    (artist, title, album, year, str(path), dur),
                )
                n += 1
            conn.commit()
            return n
        finally:
            conn.close()

    def load_compact(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, artist, title, year FROM tracks ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return [
            {"id": r[0], "artist": r[1], "title": r[2], "year": r[3]}
            for r in rows
        ]
