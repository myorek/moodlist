#!/usr/bin/env bash
# Alfred Script Filter bridge for moodlist.
#
# Usage:
#   script-filter.sh "<query>"           # normal (cached)
#   script-filter.sh --fresh "<query>"   # bypass cache (the `ml!` keyword)
#
# Also still honors MOODLIST_FRESH=1 in the environment for backward
# compatibility with older workflow setups.

set -euo pipefail

MOODLIST_VENV="${HOME}/projects/moodlist/.venv/bin/python"
FRESH_FLAG=""

# Accept --fresh as the first argv (preferred form).
if [[ "${1:-}" == "--fresh" ]]; then
  FRESH_FLAG="--fresh"
  shift
fi

# Backward-compat: env var also triggers fresh mode.
if [[ "${MOODLIST_FRESH:-0}" == "1" ]]; then
  FRESH_FLAG="--fresh"
fi

"${MOODLIST_VENV}" -m moodlist.cli "${1:-}" --alfred-json ${FRESH_FLAG}
