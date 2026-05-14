from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

from . import agent, writer
from .cache import QueryCache, normalize_query
from .config import load_config
from .indexer import Indexer
from .types import Track


def _load_full_tracks(db_path: Path, picks: list[int]) -> list[Track]:
    if not picks:
        return []
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" * len(picks))
        rows = conn.execute(
            f"SELECT id, artist, title, album, year, path, duration_sec "
            f"FROM tracks WHERE id IN ({placeholders})",
            picks,
        ).fetchall()
    finally:
        conn.close()
    by_id = {r[0]: r for r in rows}
    out = []
    for pid in picks:
        if pid in by_id:
            r = by_id[pid]
            out.append(Track(id=r[0], artist=r[1], title=r[2], album=r[3],
                             year=r[4], path=r[5], duration_sec=r[6]))
    return out


def _emit_alfred(items: list[dict]) -> None:
    print(json.dumps({"items": items}))


def _alfred_error(title: str, subtitle: str = "") -> int:
    _emit_alfred([{
        "title": title, "subtitle": subtitle,
        "valid": False, "icon": {"path": "icon.png"},
    }])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="moodlist")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--alfred-json", action="store_true")
    parser.add_argument("--fresh", action="store_true",
                        help="bypass query cache")
    parser.add_argument("--reindex", action="store_true",
                        help="force library rescan")
    parser.add_argument("--count", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--open", action="store_true",
                        help="invoke `open -a foobar2000` directly (skip Alfred)")
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        return _alfred_error("moodlist not configured", str(e)) if args.alfred_json \
               else (print(f"ERROR: {e}", file=sys.stderr) or 1)

    moodlist_dir = cfg.moodlist_dir
    ix = Indexer(library_root=cfg.library_root, moodlist_dir=moodlist_dir)

    if args.reindex or ix.is_stale():
        ix.build()

    if not args.query.strip():
        return _alfred_error("Type a query, e.g. `ml top 80s metal`") \
            if args.alfred_json else 0

    library = ix.load_compact()
    if not library:
        return _alfred_error("Library is empty", "Run `ml-reindex` after adding files") \
            if args.alfred_json else (print("library empty", file=sys.stderr) or 1)

    library_version = ix.library_version()
    cache = QueryCache(moodlist_dir / "query-cache.sqlite")
    desired_count = args.count or cfg.default_count

    # Cache lookup
    if not args.fresh:
        hit = cache.lookup(args.query, library_version)
        if hit and hit.exists():
            if args.alfred_json:
                _emit_alfred([{
                    "title": f"{args.query} — playlist ready",
                    "subtitle": f"cached result · {hit.name}",
                    "arg": str(hit),
                    "icon": {"path": "icon.png"},
                }])
            elif args.open:
                writer.open_in_foobar(hit, app=cfg.foobar_app)
            else:
                print(hit)
            return 0

    # Cache miss → call agent
    today = _dt.date.today().isoformat()
    try:
        result = agent.pick(
            query=args.query,
            library=library,
            date_iso=today,
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            desired_count=desired_count,
        )
    except agent.AgentError as e:
        return _alfred_error("Couldn't build playlist", str(e)) \
            if args.alfred_json else (print(str(e), file=sys.stderr) or 1)

    if result.needs_live:
        return _alfred_error(
            "Live chart data not available in v1",
            "Try \"all-time top rock\" instead.",
        ) if args.alfred_json else (print("needs live data", file=sys.stderr) or 1)

    tracks = _load_full_tracks(moodlist_dir / "library.sqlite", result.picks)
    slug = writer.slugify(normalize_query(args.query))
    year = _dt.date.today().year
    playlist_path = writer.write_m3u8(
        tracks, slug=slug, year=year,
        out_dir=moodlist_dir / "playlists",
    )

    cache.store(args.query, library_version, playlist_path)

    if result.wanted_but_missing:
        misses = moodlist_dir / "misses.log"
        with misses.open("a") as f:
            for m in result.wanted_but_missing:
                f.write(f"{today}\t{args.query}\t{m}\n")

    title = f"{args.query} — {len(tracks)} tracks"
    subtitle = result.reasoning or "picked fresh"

    if args.alfred_json:
        _emit_alfred([{
            "title": title, "subtitle": subtitle,
            "arg": str(playlist_path),
            "icon": {"path": "icon.png"},
        }])
    elif args.open or not args.dry_run:
        writer.open_in_foobar(playlist_path, app=cfg.foobar_app)
    else:
        print(playlist_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
