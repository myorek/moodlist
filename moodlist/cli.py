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


def _debug_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "debug", False))


def _debug_print(args: argparse.Namespace, line: str = "") -> None:
    if not _debug_enabled(args):
        return
    try:
        sys.stderr.write(line + "\n")
    except OSError:
        pass


def _debug_section(args: argparse.Namespace, name: str) -> None:
    _debug_print(args, f"\n=== {name} ===")


def _redact_api_key(key: str) -> str:
    if len(key) <= 10:
        return "***"
    return key[:8] + "***"


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
    parser.add_argument("--debug", action="store_true",
                        help="print diagnostic sections to stderr")
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        return _alfred_error("moodlist not configured", str(e)) if args.alfred_json \
               else (print(f"ERROR: {e}", file=sys.stderr) or 1)

    _debug_section(args, "config")
    _debug_print(args, f"api_key:        {_redact_api_key(cfg.api_key)}")
    _debug_print(args, f"model:          {cfg.model}")
    _debug_print(args, f"library_root:   {cfg.library_root}")
    _debug_print(args, f"default_count:  {cfg.default_count}")
    _debug_print(args, f"temperature:    {cfg.temperature}")

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

    _debug_section(args, "library context")
    _debug_print(args, f"{len(library)} tracks loaded from library.cache.json")
    _debug_print(args, f"library_version: {library_version}")
    if library:
        _debug_print(args, "sample (first 3):")
        for t in library[:3]:
            _debug_print(args, f"  [{t['id']}]   {t['artist']} - {t['title']} ({t['year']})")
        if len(library) > 3:
            _debug_print(args, "sample (last 3):")
            for t in library[-3:]:
                _debug_print(args, f"  [{t['id']}]   {t['artist']} - {t['title']} ({t['year']})")

    _debug_section(args, "query")
    _debug_print(args, f"raw:           \"{args.query}\"")
    _debug_print(args, f"normalized:    \"{normalize_query(args.query)}\"")
    _debug_print(args, f"default_count: {desired_count}")
    _debug_print(args, f"fresh:         {'yes' if args.fresh else 'no'}")

    # Cache lookup
    if not args.fresh:
        hit = cache.lookup(args.query, library_version)
        if hit and hit.exists():
            _debug_print(args, "cache lookup:  HIT")
            _debug_section(args, "output")
            _debug_print(args, f"playlist (cached): {hit}")
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
                sys.stdout.write(str(hit))
            return 0
        _debug_print(args, "cache lookup:  MISS")
    else:
        _debug_print(args, "cache lookup:  SKIPPED (--fresh)")

    # Cache miss → call agent
    _debug_section(args, "prompt")
    _debug_print(args, f"system: {len(agent.SYSTEM_PROMPT.splitlines())} lines, "
                       f"{len(agent.SYSTEM_PROMPT)} chars")
    if args.debug:
        _debug_print(args, "(+ DEBUG_SUFFIX appended)")
    blocks = agent.build_user_blocks(library, args.query,
                                     _dt.date.today().isoformat(),
                                     desired_count)
    _debug_print(args, f"user blocks: {len(blocks)}")
    for i, b in enumerate(blocks):
        cc = b.get("cache_control")
        cc_str = f", cache_control={cc['type']}" if cc else ""
        _debug_print(args, f"  [{i}] {b['type']}, {len(b['text'])} chars{cc_str}")

    today = _dt.date.today().isoformat()
    _debug_section(args, "haiku call")
    call_start = _dt.datetime.now()
    try:
        result = agent.pick(
            query=args.query,
            library=library,
            date_iso=today,
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            desired_count=desired_count,
            debug=args.debug,
        )
    except agent.AgentError as e:
        return _alfred_error("Couldn't build playlist", str(e)) \
            if args.alfred_json else (print(str(e), file=sys.stderr) or 1)
    call_elapsed = (_dt.datetime.now() - call_start).total_seconds()
    _debug_print(args, f"duration: {call_elapsed:.2f}s")

    if result.needs_live:
        _debug_section(args, "haiku response")
        _debug_print(args, "needs_live: True (live chart query)")
        return _alfred_error(
            "Live chart data not available in v1",
            "Try \"all-time top rock\" instead.",
        ) if args.alfred_json else (print("needs live data", file=sys.stderr) or 1)

    _debug_section(args, "haiku response")
    _debug_print(args, f"raw picks ({len(result.raw_picks)}): {result.raw_picks}")
    _debug_print(args, f"overall reasoning: \"{result.reasoning}\"")
    if result.pick_reasons:
        _debug_print(args)
        _debug_print(args, "per-track reasons:")
        lib_by_id = {t["id"]: t for t in library}
        for pid in result.picks:
            row = lib_by_id.get(pid, {})
            label = f"{row.get('artist', '?')} - {row.get('title', '?')} ({row.get('year', '?')})"
            reason = result.pick_reasons.get(pid, "(no reason returned)")
            _debug_print(args, f"  [{pid}]  {label}")
            _debug_print(args, f"        \"{reason}\"")
    if result.wanted_but_missing:
        _debug_print(args)
        _debug_print(args, "wanted_but_missing:")
        for m in result.wanted_but_missing:
            _debug_print(args, f"  - {m}")

    _debug_section(args, "validation")
    dropped = [p for p in result.raw_picks if p not in result.picks]
    _debug_print(args, f"{len(result.picks)}/{len(result.raw_picks)} IDs valid, "
                       f"{len(dropped)} dropped")
    if dropped:
        _debug_print(args, f"dropped IDs: {dropped}")

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

    _debug_section(args, "output")
    _debug_print(args, f"playlist:       {playlist_path}")
    _debug_print(args, f"tracks written: {len(tracks)}")
    _debug_print(args, "cache row:      stored")

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
        sys.stdout.write(str(playlist_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
