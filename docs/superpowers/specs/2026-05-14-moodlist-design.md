# moodlist — Design Spec

**Date:** 2026-05-14
**Status:** Draft for review
**Author:** Claude + user (collaborative brainstorm)

## 1. Problem

The user has a personal FLAC library (~425 tracks under `~/Music/`, organized by
artist folder; heavy in classic rock and metal — Metallica, AC/DC, Queen, Guns
N' Roses, etc.) played through foobar2000 on macOS. They want to generate
mood- or theme-based playlists by typing a natural-language query
("top 80s metal", "best Queen songs", "stuff like Master of Puppets"), have
it open immediately in foobar2000, and avoid repeating LLM cost when the same
query is asked again.

## 2. Goals

- Free-form natural-language input via Alfred (`moodlist <query>`).
- Open the resulting playlist in foobar2000 with one keystroke.
- Pick tracks that actually exist in the local library (no hallucinated
  song names).
- Cache results so repeat queries don't burn LLM cost.
- Retain one canonical playlist file per `(year, query)` pair; never auto-purge
  across queries or across years, so the `~/.moodlist/playlists/` directory
  accumulates a browsable history in Finder.
- Local git repo from day 1 at `~/projects/moodlist/`.

## 3. Non-goals (v1)

- **Live chart data** (Last.fm, Spotify, Billboard). Queries like "today's top
  20 rock" fail with a clear message in v1. Deferred to v2.
- Audio-feature analysis (energy, valence, tempo via Spotify API or
  `librosa`). Mood matching relies on the LLM's knowledge of the picked
  tracks.
- Multi-user / network features.
- GUI beyond the Alfred workflow.
- Automatic playlist scheduling (cron jobs, "morning rock daily" etc.).
- Sharing/exporting playlists outside foobar2000.

## 4. Architecture

### 4.1 Storage layout

```
~/projects/moodlist/                   ← git repo (local-only)
├── .gitignore
├── README.md
├── pyproject.toml                     (uv-managed, Python 3.12+)
├── config.example.toml                (template; real config never committed)
├── moodlist/
│   ├── __init__.py
│   ├── cli.py                         (argparse → orchestrator → Alfred JSON)
│   ├── indexer.py                     (FLAC tags → SQLite library)
│   ├── agent.py                       (single Haiku call, prompt-cached library)
│   ├── llm.py                         (Anthropic client wrapper)
│   ├── cache.py                       (query-cache.sqlite)
│   └── writer.py                      (m3u8 + open foobar2000)
├── alfred/
│   ├── script-filter.sh
│   ├── info.plist.template
│   └── moodlist.alfredworkflow        (built artifact, committed)
├── tests/
│   ├── test_indexer.py
│   ├── test_agent.py
│   ├── test_cache.py
│   ├── test_writer.py
│   ├── test_cli.py
│   └── fixtures/
└── docs/
    └── superpowers/specs/
        └── 2026-05-14-moodlist-design.md

~/.moodlist/                           ← runtime, NEVER in git
├── config.toml                        (Anthropic API key, library root, fb2k path)
├── library.sqlite                     (full FLAC index w/ year, album, etc.)
├── library.cache.json                 (compact context sent to Haiku; rebuilt on reindex)
├── library.version                    (sha256 hash of compact context)
├── query-cache.sqlite                 (normalized query → playlist file)
├── playlists/                         (NEVER deleted)
│   ├── 2026-top-80s-metal.m3u8
│   ├── 2026-best-queen-songs.m3u8
│   └── …
└── misses.log                         (LLM's "wanted but missing" suggestions)
```

The split is strict: **code & specs in `~/projects/moodlist/`** (versioned);
**all data, secrets, and generated artifacts in `~/.moodlist/`** (never
versioned).

### 4.2 Component boundaries

Each module has a narrow public interface and one responsibility.

| Module | Responsibility | Public interface |
|---|---|---|
| `indexer.py` | Scan `~/Music/**/*.flac` with `mutagen`, write `library.sqlite` and `library.cache.json`, compute `library.version`. | `build() -> None`, `is_stale() -> bool`, `load_compact() -> list[Track]` |
| `cache.py` | Query-cache lookup and write; query normalization. | `lookup(query, library_version) -> Path \| None`, `store(query, library_version, path) -> None`, `normalize(query) -> str` |
| `agent.py` | Single Claude API call; returns picked track IDs. | `pick(query: str, library: list[Track], date_salt: str) -> AgentResult` |
| `llm.py` | Anthropic SDK wrapper: messages API, prompt caching, JSON-mode, retries on transient errors only. | `call(messages, system, cache_breakpoints) -> dict` |
| `writer.py` | Compose `.m3u8` content, write file, invoke `open -a foobar2000 <path>`. | `write(tracks: list[Track], slug: str, year: int) -> Path`, `open_in_foobar(path: Path) -> None` |
| `cli.py` | Argument parsing, orchestration, Alfred-JSON output. | `main(argv) -> int` |

A unit should be understandable without reading any other unit's internals;
data crosses boundaries via plain dicts / dataclasses.

### 4.3 End-to-end data flow

`moodlist top 80s metal` (typed into Alfred):

```
Alfred Script Filter
  → alfred/script-filter.sh
    → moodlist (CLI) "top 80s metal" --alfred-json

CLI flow:
  1. Load config.toml. Bail with helpful error if missing or API key absent.
  2. Check indexer.is_stale(); if so, run indexer.build().
  3. Normalize the query (lowercase, collapse whitespace).
  4. cache.lookup(query, library_version):
     - HIT  → emit Alfred JSON pointing at existing playlist file. EXIT.
     - MISS → continue.
  5. Load library.cache.json (compact list, with stable integer IDs).
  6. agent.pick(query, library, date_salt=today_iso):
       - llm.call with:
           system    : "You select playlist tracks by integer ID …"
           user 1    : library list, marked cache_control=ephemeral
           user 2    : query + today's date salt
         response schema: {picks:[int], reasoning:str,
                           wanted_but_missing:[str], needs_live:bool, …}
       - validate every picked ID exists in library; drop invalid.
       - if needs_live → emit Alfred JSON with explanatory error. EXIT.
  7. writer.write(picked_tracks, slug, year) →
       ~/.moodlist/playlists/2026-<slug>.m3u8
     (overwrite if file exists for same year + slug)
  8. cache.store(query, library_version, path) — upserts the row.
  9. Append any wanted_but_missing entries to misses.log.
 10. Emit Alfred JSON:
       { "items": [{
           "title":    "Top 80s metal — 20 tracks",
           "subtitle": "Picked studio versions; 0 chart misses.",
           "arg":      "/Users/myorek/.moodlist/playlists/2026-top-80s-metal.m3u8",
           "icon":     {"path": "icon.png"}
         }] }

Alfred Action (next step):
  open -a foobar2000 "{arg}"
  → foobar2000 loads the .m3u8 (verified working with public.audio UTI fallback).
```

## 5. Detailed design

### 5.1 Library indexing (`indexer.py`)

- Walks `config.library_root` (default `~/Music`) for `**/*.flac`.
- Reads tags with `mutagen.flac.FLAC`: `ARTIST`, `ALBUM`, `TITLE`,
  `DATE`/`YEAR`, `TRACKNUMBER`, `DISCNUMBER`.
- Writes `library.sqlite` (full data) and `library.cache.json` (compact for
  LLM prompt: `id`, `artist`, `title`, `year`).
- Computes `library.version` as `sha256(library.cache.json bytes)[:12]`.
- All versions of a song (live, demo, remastered, B-side) appear in the list
  as separate rows. The LLM is instructed to prefer studio versions unless
  the query implies otherwise.
- Freshness check: stat-mtime each artist folder under `library_root`; if any
  is newer than `library.cache.json`, full reindex.
- 425 tracks reindex in well under a second; no incremental optimization
  needed.

### 5.2 Query cache (`cache.py`)

- SQLite at `~/.moodlist/query-cache.sqlite`. Single table:

  ```sql
  CREATE TABLE query_cache (
    query_hash       TEXT PRIMARY KEY,         -- sha256(normalized_query | library_version)
    normalized_query TEXT NOT NULL,
    library_version  TEXT NOT NULL,
    playlist_path    TEXT NOT NULL,
    created_at       TEXT NOT NULL,            -- ISO 8601
    last_used_at     TEXT NOT NULL,
    hit_count        INTEGER NOT NULL DEFAULT 0
  );
  ```

- Normalization: lowercase → Unicode NFKC → collapse whitespace → strip
  leading/trailing punctuation. `"Top 80s Metal "` and `"top 80s metal"` hash
  to the same row.
- Lookup increments `hit_count` and updates `last_used_at`.
- **Cache never expires.** Invalidation happens implicitly via
  `library_version`: a reindex that changes the compact representation
  produces a new version, and old rows are no longer returned. They are not
  purged from disk (cheap to keep; useful for stats).
- `--fresh` flag (Alfred prefix `moodlist!`): bypass `lookup`, force a new agent
  call, then `store` (overwriting the row for the same hash).

### 5.3 Agent call (`agent.py`)

One Claude Haiku 4.5 call per uncached query.

**Prompt structure** (multiple message blocks, with prompt-cache breakpoints
on the library context):

```
system:
  You are a music-playlist curator. The user has a fixed local library
  represented as a list of [id, artist, title, year] tuples. Pick tracks
  by INTEGER ID. Never invent IDs that aren't in the list.

  - Prefer studio versions over demos/live/B-sides unless the query
    explicitly asks otherwise.
  - For "top X" queries, use your knowledge of canonical hits from that
    era/genre. Cross-reference against the library.
  - If the query asks about CURRENT charts ("today", "this week",
    "currently trending"), respond with {"needs_live": true, ...}
    instead of picking — do not guess current data.
  - Provide a one-line reasoning suitable for showing to the user.
  - If you know of canonical tracks that match the query but are NOT
    in this library, list them in `wanted_but_missing` (max 5).

  Output JSON conforming to this schema:
  {
    "picks":               [int],     // library IDs
    "reasoning":           string,    // one short line
    "wanted_but_missing":  [string],  // "Artist - Title" strings
    "needs_live":          boolean
  }

user (cache_control=ephemeral):
  Library:
  [
    {"id": 1, "artist": "AC/DC", "title": "Highway to Hell", "year": 1979},
    {"id": 2, "artist": "AC/DC", "title": "Let There Be Rock", "year": 1977},
    …
  ]

user:
  Query: "top 80s metal"
  Date: 2026-05-14
  Desired count: 20
```

**Model parameters:**
- `model`: `claude-haiku-4-5-20251001`
- `temperature`: `0.4` (slight variety; combined with the date salt this
  gives different orderings/picks day-to-day without chaotic swings)
- `max_tokens`: `1024`
- `response_format`: JSON schema (the SDK's structured-output mode)

**Validation:** every returned ID is checked against the library set;
unknown IDs are dropped (and logged); if fewer than `floor(0.5 * count)`
valid IDs remain, the call is treated as failed and surfaced as such in
Alfred (no playlist opens).

**Cost & latency budget (per typical query, 3 scenarios):**
- **Query-cache hit** (local SQLite hit): $0, ~50ms — Claude is not called at all.
- **Prompt-cache hit** (Claude called; library context is in Anthropic's
  ephemeral cache from a recent call): ~$0.0008, ~0.8s.
- **Cold call** (Claude called; prompt cache cold): ~$0.003, ~1.5s. Input
  is ~13k tokens library + ~200 tokens query; output ~300 tokens.

### 5.4 Writer (`writer.py`)

- Filename: `<year>-<slug>.m3u8` where `slug = slugify(normalized_query)`
  (lowercase, hyphenate, strip non-`[a-z0-9-]`).
- Overwrites if the file already exists for the same `(year, slug)`. The
  query cache row tracks the canonical mapping; older content is replaced.
- File contents (UTF-8, no BOM):

  ```
  #EXTM3U
  #EXTINF:<duration_sec>,<artist> - <title>
  <absolute file path>
  #EXTINF:…
  …
  ```

  Duration is the FLAC's reported length in seconds (read once at index
  time, cached in `library.sqlite`).
- `open_in_foobar(path)` shells out to `open -a foobar2000 "{path}"`.
  Verified working during brainstorm: foobar2000.app accepts `.m3u8`
  via LaunchServices despite not declaring a playlist UTI.

### 5.5 CLI / Alfred glue (`cli.py`, `alfred/`)

- Top-level CLI: `moodlist "<query>"` with flags:
  - `--alfred-json` — emit Alfred Script-Filter JSON instead of plain text.
  - `--fresh` — bypass query cache.
  - `--reindex` — force a full library reindex before answering.
  - `--count N` — override default playlist length (default 20).
  - `--dry-run` — print picks, don't write file or open foobar.
- The Alfred workflow has **one keyword** (`moodlist`) with two variants
  resolved by argument prefix:
  - `moodlist <query>` → `moodlist "<query>" --alfred-json`
  - `moodlist! <query>` → `moodlist "<query>" --alfred-json --fresh`
- Alfred displays the title/subtitle from the JSON. Pressing Enter triggers
  a follow-on `Open File` action with the `arg` (the m3u8 path).
- A separate Alfred keyword `moodlist-reindex` runs `moodlist --reindex`
  and reports the new track count.

## 6. Error handling

Errors fail loudly with one clear message. No retry loops, no silent
fallbacks.

| Failure | Behavior |
|---|---|
| Anthropic API key missing | First-run error pointing at `~/.moodlist/config.toml` |
| Anthropic API transient (5xx, network) | One retry with backoff; then surface error to Alfred |
| LLM returns unparseable JSON | Surface "model returned malformed JSON"; log raw response |
| LLM returns 0 valid IDs | Surface "couldn't pick any tracks for this query"; don't open foobar |
| Library empty | Suggest `moodlist-reindex` in Alfred subtitle |
| Library reindex fails (permissions, corrupt file) | Skip the bad file, log, continue |
| foobar2000 not installed | Detect at config-load; one-time error message |
| `needs_live=true` from agent | Alfred: "Live chart data not available in v1. Want all-time instead?" |

## 7. Testing strategy

TDD. Write the failing test first; then the minimal implementation. Build
order is dictated by dependencies — pure units first, then integrations.

**Build order:**
1. `indexer` — pure, file-only, fast feedback loop.
2. `cache` — pure SQLite logic, no LLM, no network.
3. `writer` — pure formatting + one shell call.
4. `llm` — Anthropic client wrapper; mocked in unit tests, one E2E smoke.
5. `agent` — composes prompt, calls `llm`, validates IDs.
6. `cli` — glues everything together.
7. Alfred workflow — manual smoke test once CLI is green.

**Unit tests:**
- `test_indexer.py`: tag parsing, unicode artist names (`AC／DC`),
  `feat.` collaborators, missing year, multi-disc.
- `test_cache.py`: normalization equivalences, lookup miss vs. hit,
  hit_count increment, library_version invalidation.
- `test_writer.py`: m3u8 format, UTF-8 encoding, `#EXTINF` lines,
  overwrite-on-collision.
- `test_agent.py`: LLM mocked with canned JSON; assert ID validation,
  needs_live branch, malformed-JSON branch.
- `test_cli.py`: argparse, Alfred-JSON shape, error message routing.

**Integration / smoke:**
- One end-to-end test that hits the real Anthropic API with a tiny
  hand-built library fixture and verifies the call returns a sensible
  playlist. Tagged `@pytest.mark.e2e`; opt-in.

**No tests for the Alfred shell glue.** It's three lines; manual smoke.

## 8. Future / deferred

These are explicitly **out of scope** for v1 but the design accommodates
them without refactor:

- **v2: Last.fm provider** for live-chart queries. Slots in cleanly: agent
  detects `needs_live`, calls a Last.fm fetcher, then makes a second
  Haiku call to intersect with library. No structural change.
- **v3: more genres / curated playlists shared as gists.**
- **v4: simple Mac menu-bar app** that wraps the CLI for users without Alfred.

## 9. Open questions

None. All decisions resolved during the brainstorming session of 2026-05-14.

## 10. Decision log

- **2026-05-14** — knowledge-only v1 (no Last.fm). Single Haiku call.
- **2026-05-14** — library context: compact (id, artist, title, year).
- **2026-05-14** — show all versions to LLM; let it pick studio over demo.
- **2026-05-14** — temperature 0.4 + date salt for slight variety.
- **2026-05-14** — Alfred shows preview with track count, then Enter opens foobar.
- **2026-05-14** — cache never expires; `--fresh` (`moodlist!` prefix) overrides.
- **2026-05-14** — playlist naming `YYYY-<slug>.m3u8`, overwrite on same-year
  same-query collision.
- **2026-05-14** — code at `~/projects/moodlist/`, local git only; runtime
  data at `~/.moodlist/`, never versioned.
