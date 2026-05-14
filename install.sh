#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# moodlist installer
# Usage:
#   ./install.sh            — full setup (idempotent)
#   ./install.sh --doctor   — check prereqs and current state
#   ./install.sh --reindex  — run library reindex only
#   ./install.sh --help     — this message
# ---------------------------------------------------------------------------

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
MOODLIST_DIR="${HOME}/.moodlist"
LOCAL_BIN="${HOME}/.local/bin"
SYMLINK="${LOCAL_BIN}/moodlist"
CONFIG_DEST="${MOODLIST_DIR}/config.toml"
CONFIG_SRC="${REPO_DIR}/config.example.toml"
PLACEHOLDER_KEY="sk-ant-..."

# ---------------------------------------------------------------------------
# Color helpers (respect NO_COLOR env var)
# ---------------------------------------------------------------------------
if [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]; then
  _GREEN='\033[0;32m'
  _YELLOW='\033[0;33m'
  _RED='\033[0;31m'
  _CYAN='\033[0;36m'
  _RESET='\033[0m'
else
  _GREEN='' _YELLOW='' _RED='' _CYAN='' _RESET=''
fi

ok()   { printf "${_GREEN}  ✓${_RESET}  %s\n" "$*"; }
warn() { printf "${_YELLOW}  ⚠${_RESET}  %s\n" "$*"; }
err()  { printf "${_RED}  ✗${_RESET}  %s\n" "$*" >&2; }
info() { printf "${_CYAN}  →${_RESET}  %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Prerequisite checks (shared by full install and --doctor)
# ---------------------------------------------------------------------------
PREREQS_OK=true

check_python() {
  if command -v python3 &>/dev/null; then
    local ver
    ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    local major minor
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [[ "$major" -gt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -ge 12 ]]; }; then
      ok "python3 ${ver} (>= 3.12)"
      return 0
    else
      err "python3 ${ver} found but >= 3.12 required"
      info "Install with: brew install python@3.12"
      PREREQS_OK=false
      return 1
    fi
  else
    err "python3 not found (>= 3.12 required)"
    info "Install with: brew install python@3.12"
    PREREQS_OK=false
    return 1
  fi
}

check_uv() {
  if command -v uv &>/dev/null; then
    local ver
    ver="$(uv --version 2>&1 | head -1)"
    ok "uv found (${ver})"
    return 0
  else
    err "uv not found (required)"
    info "Install from: https://github.com/astral-sh/uv#installation"
    PREREQS_OK=false
    return 1
  fi
}

check_ffmpeg() {
  if command -v ffmpeg &>/dev/null; then
    ok "ffmpeg found (optional — needed only to regenerate silence.flac fixture)"
    return 0
  else
    warn "ffmpeg not found (optional — only needed to regenerate silence.flac fixture)"
    return 0
  fi
}

check_foobar() {
  if [[ -d "/Applications/foobar2000.app" ]]; then
    ok "foobar2000 found at /Applications/foobar2000.app"
    return 0
  else
    warn "foobar2000 not found at /Applications/foobar2000.app (optional)"
    info "Download from: https://www.foobar2000.org/mac"
    return 0
  fi
}

check_path() {
  if echo ":${PATH}:" | grep -q ":${LOCAL_BIN}:"; then
    return 0  # on PATH
  else
    return 1  # not on PATH
  fi
}

# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------
cmd_help() {
  cat <<'EOF'
moodlist installer

Usage:
  ./install.sh            Full setup: venv, deps, runtime dir, config, symlink
  ./install.sh --doctor   Check prereqs and current state (no changes)
  ./install.sh --reindex  Run library reindex only (requires existing venv)
  ./install.sh --help     Show this message

Options are mutually exclusive; only the first argument is examined.
EOF
}

# ---------------------------------------------------------------------------
# --doctor
# ---------------------------------------------------------------------------
cmd_doctor() {
  printf "\n${_CYAN}=== moodlist doctor ===${_RESET}\n\n"

  printf "Prerequisites:\n"
  check_python || true
  check_uv || true
  check_ffmpeg
  check_foobar

  printf "\nArtifacts:\n"

  # .venv
  if [[ -d "${VENV_DIR}" ]]; then
    ok ".venv/ exists at ${VENV_DIR}"
  else
    warn ".venv/ does not exist (run ./install.sh)"
  fi

  # ~/.moodlist/
  if [[ -d "${MOODLIST_DIR}" ]]; then
    ok "~/.moodlist/ exists"
  else
    warn "~/.moodlist/ does not exist (run ./install.sh)"
  fi

  # ~/.moodlist/config.toml
  if [[ -f "${CONFIG_DEST}" ]]; then
    ok "~/.moodlist/config.toml exists"
    if grep -q "^api_key = \"${PLACEHOLDER_KEY}\"" "${CONFIG_DEST}" 2>/dev/null; then
      warn "  → API key is still the placeholder — edit config.toml before use"
    fi
  else
    warn "~/.moodlist/config.toml does not exist (run ./install.sh)"
  fi

  # ~/.moodlist/library.sqlite
  if [[ -f "${MOODLIST_DIR}/library.sqlite" ]]; then
    ok "~/.moodlist/library.sqlite exists"
  else
    warn "~/.moodlist/library.sqlite does not exist (run --reindex after setup)"
  fi

  # ~/.local/bin/moodlist symlink
  if [[ -L "${SYMLINK}" ]]; then
    local target
    target="$(readlink "${SYMLINK}")"
    ok "~/.local/bin/moodlist symlink exists → ${target}"
  else
    warn "~/.local/bin/moodlist symlink does not exist (run ./install.sh)"
  fi

  # foobar2000 (artifact check, already done in prereqs but grouped here too)
  # (already reported above under prerequisites)

  printf "\nPATH:\n"
  if check_path; then
    ok "~/.local/bin is on \$PATH"
  else
    warn "~/.local/bin is NOT on \$PATH"
    info "Add to your shell rc: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi

  printf "\nVersion:\n"
  local version
  version="$(grep '^version' "${REPO_DIR}/pyproject.toml" | head -1 | grep -o '"[^"]*"' | tr -d '"')"
  info "moodlist version (pyproject.toml): ${version}"

  printf "\n"

  # Exit non-zero only if required prereqs are missing
  if [[ "${PREREQS_OK}" != "true" ]]; then
    exit 1
  fi
  exit 0
}

# ---------------------------------------------------------------------------
# --reindex
# ---------------------------------------------------------------------------
cmd_reindex() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    err "No venv found at ${VENV_DIR}"
    info "Run ./install.sh first to set up the environment."
    exit 1
  fi
  info "Running library reindex…"
  exec "${VENV_DIR}/bin/python" -m moodlist.cli --reindex
}

# ---------------------------------------------------------------------------
# Full install
# ---------------------------------------------------------------------------
cmd_install() {
  printf "\n${_CYAN}=== moodlist installer ===${_RESET}\n\n"

  # Step 1: Prereqs
  printf "Step 1/6  Checking prerequisites…\n"
  check_python
  check_uv
  check_ffmpeg
  check_foobar

  if [[ "${PREREQS_OK}" != "true" ]]; then
    err "Required prerequisites missing. Fix them and re-run ./install.sh"
    exit 1
  fi

  # Step 2: Venv
  printf "\nStep 2/6  Setting up virtual environment…\n"
  if [[ -d "${VENV_DIR}" ]]; then
    info "Venv exists (${VENV_DIR}), refreshing deps…"
  else
    info "Creating venv at ${VENV_DIR}…"
    uv venv "${VENV_DIR}"
    ok "Venv created"
  fi
  info "Installing/refreshing dependencies (uv pip install -e '.[dev]')…"
  uv pip install --quiet -e ".[dev]" --python "${VENV_DIR}/bin/python"
  ok "Dependencies installed"

  # Step 3: Runtime directory
  printf "\nStep 3/6  Runtime directory…\n"
  if [[ ! -d "${MOODLIST_DIR}" ]]; then
    /bin/mkdir -p "${MOODLIST_DIR}"
    ok "Created ~/.moodlist/"
  else
    ok "~/.moodlist/ already exists"
  fi
  if [[ ! -d "${MOODLIST_DIR}/playlists" ]]; then
    /bin/mkdir -p "${MOODLIST_DIR}/playlists"
    ok "Created ~/.moodlist/playlists/"
  else
    ok "~/.moodlist/playlists/ already exists"
  fi

  # Step 4: Config bootstrap
  printf "\nStep 4/6  Config bootstrap…\n"
  if [[ ! -f "${CONFIG_DEST}" ]]; then
    /bin/cp "${CONFIG_SRC}" "${CONFIG_DEST}"
    ok "Created ~/.moodlist/config.toml from template"
    warn "IMPORTANT: Edit ~/.moodlist/config.toml and replace the placeholder API key before use."
  else
    ok "Config already present at ~/.moodlist/config.toml"
  fi

  # Step 5: CLI symlink
  printf "\nStep 5/6  CLI symlink…\n"
  if [[ ! -d "${LOCAL_BIN}" ]]; then
    /bin/mkdir -p "${LOCAL_BIN}"
    ok "Created ~/.local/bin/"
  fi
  /bin/ln -sf "${VENV_DIR}/bin/moodlist" "${SYMLINK}"
  ok "Symlink created: ${SYMLINK} → ${VENV_DIR}/bin/moodlist"

  if ! check_path; then
    warn "~/.local/bin is NOT on your \$PATH"
    info "Add this to your shell rc (~/.zshrc or ~/.bashrc):"
    info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi

  # Step 6: Optional first reindex
  printf "\nStep 6/6  Optional first reindex…\n"
  local api_key_line
  api_key_line="$(grep '^api_key' "${CONFIG_DEST}" 2>/dev/null | head -1 || true)"
  if echo "${api_key_line}" | grep -q "\"${PLACEHOLDER_KEY}\""; then
    warn "API key is still the placeholder — skipping reindex."
    info "Edit ~/.moodlist/config.toml and set your real API key, then run: ./install.sh --reindex"
  else
    info "Running initial library reindex…"
    "${SYMLINK}" --reindex && ok "Reindex complete"
  fi

  # Final hint
  printf "\n"
  ok "Done."
  info "Edit ~/.moodlist/config.toml if you haven't set your API key."
  info "Then try: moodlist 'top 80s metal'"
  info "For Alfred integration, see README.md → 'Alfred workflow setup'."
  printf "\n"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
case "${1:-}" in
  --help|-h)    cmd_help ;;
  --doctor)     cmd_doctor ;;
  --reindex)    cmd_reindex ;;
  "")           cmd_install ;;
  *)
    err "Unknown option: $1"
    cmd_help
    exit 1
    ;;
esac
