#!/bin/bash
# Prepares and starts the MCP servers listed in .mcp.json.
#   setup.sh prepare [console-skill|markitdown|rea|all]   install what is missing
#   setup.sh run <name>                                   prepare, then start the server on stdio
# Every step is skipped when it is already done. Installs go to ~/.cache/claude-mcp, outside the repo.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/claude-mcp"
CONSOLE_SKILL_URL=https://github.com/Jakeschincariol/console-skill
CONSOLE_SKILL_REV=a508929f1e8f5dd6f54afe489fd74340df3b6f74
REA_VERSION=6.7.0

prepare_console_skill() {
  local dir="$cache/console-skill"
  if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" != "$CONSOLE_SKILL_REV" ]; then
    rm -rf "$dir"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" fetch -q --depth 1 "$CONSOLE_SKILL_URL" "$CONSOLE_SKILL_REV"
    git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
  fi
}

prepare_markitdown() {
  local venv="$cache/markitdown-venv"
  local hashes="$venv/.setup.sha256"
  local files=("${BASH_SOURCE[0]}")
  local pkgs=(markitdown-mcp)
  # Inside the markitdown repo, run the checkout's own packages instead of the PyPI release
  if [ -f "$root/packages/markitdown-mcp/pyproject.toml" ]; then
    pkgs=(-e "$root/packages/markitdown[all]" -e "$root/packages/markitdown-mcp")
    files+=("$root/packages/markitdown/pyproject.toml" "$root/packages/markitdown-mcp/pyproject.toml")
  fi
  if ! sha256sum --check --status "$hashes" 2>/dev/null || [ "$(cat "$venv/.root" 2>/dev/null)" != "$root" ]; then
    rm -rf "$venv"
    python3 -m venv "$venv"
    "$venv/bin/pip" install -q --disable-pip-version-check "${pkgs[@]}"
    echo "$root" > "$venv/.root"
    sha256sum "${files[@]}" > "$hashes"
  fi
}

prepare_rea() {
  # Installed into the cache rather than run with npx: inside the rea repo npx
  # resolves rea-agents to the repo's own unbuilt package
  local dir="$cache/rea"
  if [ "$("$dir/node_modules/.bin/rea-agents" --version 2>/dev/null)" != "$REA_VERSION" ]; then
    rm -rf "$dir"
    npm install -s --no-fund --no-audit --prefix "$dir" "rea-agents@$REA_VERSION"
  fi
}

prepare() {
  case "$1" in
    console-skill) prepare_console_skill ;;
    markitdown) prepare_markitdown ;;
    rea) prepare_rea ;;
    all) prepare_console_skill; prepare_markitdown; prepare_rea ;;
    *) echo "unknown server: $1" >&2; exit 2 ;;
  esac
}

case "${1:-}" in
  prepare)
    prepare "${2:-all}"
    ;;
  run)
    # stdout belongs to the MCP protocol, so setup output goes to stderr
    prepare "${2:?server name}" >&2
    case "$2" in
      console-skill) exec python3 "$root/.claude/mcp/console_skill_server.py" --skills "$cache/console-skill" ;;
      markitdown) exec "$cache/markitdown-venv/bin/markitdown-mcp" ;;
      rea) exec "$cache/rea/node_modules/.bin/rea-agents" mcp ;;
    esac
    ;;
  *)
    echo "usage: setup.sh prepare [name|all] | setup.sh run <name>" >&2
    exit 2
    ;;
esac
