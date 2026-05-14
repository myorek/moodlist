# moodlist

Mood-based playlist generator for foobar2000 on macOS. Type a natural-language
query like `top 80s metal` or `best Queen songs` and a `.m3u8` playlist gets
written and opened in foobar2000 — picked from the FLAC files already in your
library by Claude Haiku 4.5.

```text
ml top 80s metal       →  foobar2000 opens with 20 tracks
ml! best Queen songs   →  fresh pick (bypass cache)
ml-reindex             →  rescan ~/Music for new files
```

---

## How it works

1. The indexer scans your FLAC library (`~/Music` by default) into a SQLite
   index plus a compact JSON snapshot.
2. The agent sends your query + the compact library list to Claude Haiku 4.5,
   marked with `cache_control: ephemeral` so the library context is cached on
   Anthropic's side.
3. Haiku picks track IDs from the list. We validate every ID against the
   index, write an `.m3u8`, store the result in a query cache, and hand the
   path to foobar2000.
4. Repeat queries hit the local query cache and skip Claude entirely.

There is no network usage beyond the Anthropic API. The library list never
leaves your machine, except as part of the prompt to Anthropic.

---

## Requirements

- **macOS** (uses `open -a foobar2000` to launch).
- **Python 3.12 or newer** — `brew install python@3.12` if missing.
- **uv** — `brew install uv` if missing.
- **foobar2000 for Mac** — [download from foobar2000.org](https://www.foobar2000.org/mac).
- **Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com/).
- **Alfred 5** (optional but recommended) — [alfredapp.com](https://www.alfredapp.com/).
- **ffmpeg** (optional) — only needed if you ever need to regenerate the test
  fixture FLAC.

---

## Install

```bash
git clone https://github.com/myorek/moodlist.git ~/projects/moodlist
cd ~/projects/moodlist
./install.sh
```

`install.sh` is idempotent. It:

- Verifies your prereqs (`python3 >= 3.12`, `uv`).
- Creates a virtualenv at `./.venv/` and installs the package.
- Creates `~/.moodlist/` with a `playlists/` subdir.
- Copies `config.example.toml` → `~/.moodlist/config.toml` if missing.
- Symlinks `~/.local/bin/moodlist` to the venv binary so the CLI works
  from any shell.
- Warns if `~/.local/bin` isn't on your `$PATH` (add
  `export PATH="$HOME/.local/bin:$PATH"` to your shell rc if so).

Then edit `~/.moodlist/config.toml` and paste your real Anthropic API key
over the `sk-ant-...` placeholder.

### Verify the install

```bash
./install.sh --doctor
```

Reports the state of every prerequisite, the venv, the runtime dir, your
config, your library index, and the PATH symlink. Useful when something
isn't behaving.

---

## Using from the console

```bash
moodlist --reindex                  # one-time: scan ~/Music for FLAC files

moodlist "top 80s metal"            # generate playlist, open in foobar
moodlist "best Queen songs"
moodlist "songs like Master of Puppets"

moodlist --fresh "top 80s metal"    # bypass cache, force a new pick
moodlist --count 10 "rock classics" # request 10 tracks instead of default 20
moodlist --dry-run "top rock"       # write playlist, print path, don't open foobar
moodlist --help                     # full flag reference
```

The first run of a unique query takes 5-6 seconds (Claude Haiku call). The
same query within the same library state returns in under a second (local
query cache).

Time-sensitive queries (`today's top rock`, `this week's trending`) are
**not** supported in v1 — Haiku's knowledge cuts off in 2025, so we don't
fake live chart data. The CLI returns a clear message instead.

---

## Using from Alfred

A pre-built workflow is checked into `alfred/moodlist.alfredworkflow`.

### Install the workflow

```bash
open ~/projects/moodlist/alfred/moodlist.alfredworkflow
```

Alfred opens an import dialog. Click **Import**. Done.

If you didn't clone the repo at `~/projects/moodlist/`, the workflow's
scripts won't find the venv. Either clone to that path, or edit each Run
Script object in the workflow to point at your actual venv location.

### Three keywords

| Keyword       | Argument | Effect                                                          |
| ------------- | -------- | --------------------------------------------------------------- |
| `ml`          | query    | Generate playlist (uses cache if available), open in foobar2000 |
| `ml!`         | query    | Force a fresh pick, bypass cache, open in foobar2000            |
| `ml-reindex`  | (none)   | Rescan `~/Music` for new FLAC files; macOS notification on done |

Examples in Alfred:

- `ml top 80s metal` → Enter → ~6 sec wait → foobar2000 pops up with playlist.
- `ml top 80s metal` again → instant (cached).
- `ml! top 80s metal` → ~6 sec → fresh pick, likely different ordering.
- `ml-reindex` → macOS notification "moodlist library reindexed".

Alfred doesn't show a preview before Enter — the bar closes immediately and
foobar opens when the playlist is ready. If you want a preview, the
`moodlist --dry-run "<query>"` form prints the path without opening foobar.

---

## Configuration (`~/.moodlist/config.toml`)

```toml
[anthropic]
api_key = "sk-ant-..."                          # required
model   = "claude-haiku-4-5-20251001"

[library]
root = "~/Music"                                # where your FLAC files live
extensions = ["flac"]

[foobar2000]
app = "foobar2000"                              # value passed to `open -a`

[playlist]
default_count = 20
temperature   = 0.4                             # 0.0 = deterministic, 1.0 = wild
```

The query cache invalidates whenever `library.version` changes (i.e. you
add or remove FLAC files and re-run `moodlist --reindex`), so old playlists
never reference missing tracks.

---

## Storage layout

```
~/projects/moodlist/         ← code & tests (this repo)
~/.moodlist/                 ← runtime state (NEVER in git)
├── config.toml              ← API key, library root, defaults
├── library.sqlite           ← full FLAC index
├── library.cache.json       ← compact list sent to Haiku
├── library.version          ← sha256 prefix (cache key)
├── query-cache.sqlite       ← query → playlist path
├── playlists/               ← every playlist ever generated
│   ├── 2026-top-80s-metal.m3u8
│   ├── 2026-best-queen-songs.m3u8
│   └── …
└── misses.log               ← canonical tracks Haiku wanted but you don't own
```

Playlists are named `<year>-<slug>.m3u8` and accumulate over time. The
same year + same query overwrites (so `--fresh` replaces the previous
pick rather than piling up versions).

---

## Troubleshooting

**`moodlist: command not found` after install** — add
`export PATH="$HOME/.local/bin:$PATH"` to your `~/.zshrc` or `~/.bashrc`,
then `source` it.

**Foobar2000 doesn't open** — confirm `/Applications/foobar2000.app` exists
and that `open -a foobar2000 ~/.moodlist/playlists/<any>.m3u8` works from
the terminal.

**Empty playlist / `0 tracks`** — your library may not have enough tracks
matching the query. Check `~/.moodlist/misses.log` for what Haiku wanted
but couldn't find. Or your library is unindexed: run `moodlist --reindex`.

**`config not found` error** — `./install.sh` skipped creating it for
some reason. Run `./install.sh` again, or manually
`cp config.example.toml ~/.moodlist/config.toml`.

**Need an end-to-end health check** — `./install.sh --doctor`.

---

## Tests

```bash
make test        # all 35 unit tests, no network
make lint        # ruff
pytest -m e2e    # one e2e test against real Anthropic API
                 # (needs ANTHROPIC_API_KEY in the environment)
```

Unit tests mock the Anthropic SDK; nothing leaves your machine.

---

## Development

- **Spec:** `docs/superpowers/specs/2026-05-14-moodlist-design.md` (tagged
  `spec-v1.0`).
- **Implementation plan:** `docs/superpowers/plans/2026-05-14-moodlist.md`.
- **Module layout:** one responsibility per file — `indexer.py`,
  `cache.py`, `agent.py`, `llm.py`, `writer.py`, `cli.py`.
- TDD throughout; every behavior has a failing test before its
  implementation.

```bash
make install     # equivalent to ./install.sh
make doctor      # equivalent to ./install.sh --doctor
make reindex     # equivalent to ./install.sh --reindex
make test        # pytest -v
make lint        # ruff check
```

---

## License

Personal use. No license declared — talk to me before redistributing.
