#!/bin/bash
# co-vibe.sh — launcher for co-vibe.py
# Resolves symlinks, loads .env, hands off to Python.

set -uo pipefail

# ── Vaporwave palette ──
RED='\033[0;31m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Resolve symlinks to find the real script directory ──
_resolve_script_dir() {
    local src="${BASH_SOURCE[0]}"
    while [ -L "$src" ]; do
        local dir="$(cd "$(dirname "$src")" && pwd)"
        src="$(readlink "$src")"
        [[ "$src" != /* ]] && src="$dir/$src"
    done
    cd "$(dirname "$src")" && pwd
}
SCRIPT_DIR="$(_resolve_script_dir)"

# ── Source .env (API keys etc.) ──
[ -f "${SCRIPT_DIR}/.env" ] && set -a && . "${SCRIPT_DIR}/.env" && set +a

# ── Preflight checks ──
if ! command -v python3 &>/dev/null; then
    echo -e "  ${RED}${BOLD}[ERROR]${RESET} python3 not found in PATH" >&2
    echo -e "  ${DIM}Install Python 3 and try again.${RESET}" >&2
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/co-vibe.py" ]; then
    echo -e "  ${RED}${BOLD}[ERROR]${RESET} co-vibe.py not found" >&2
    echo -e "  ${DIM}Expected: ${SCRIPT_DIR}/co-vibe.py${RESET}" >&2
    exit 1
fi

# ── Launch ──
exec python3 "${SCRIPT_DIR}/co-vibe.py" "$@"
