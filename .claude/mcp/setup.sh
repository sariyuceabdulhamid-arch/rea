#!/bin/bash
# Prepares and starts the MCP servers listed in .mcp.json.
#   setup.sh prepare [console-skill|markitdown|rea|all]   install what is missing
#   setup.sh run <name>                                   prepare, then start the server on stdio
#   setup.sh skills                                       copy the anatomy and console-* skills to ~/.claude/skills
# Every step is skipped when it is already done. Installs go to ~/.cache/claude-mcp, outside the repo.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/claude-mcp"
CONSOLE_SKILL_URL=https://github.com/Jakeschincariol/console-skill
CONSOLE_SKILL_REV=a508929f1e8f5dd6f54afe489fd74340df3b6f74
ANATOMY_URL=https://github.com/wheresryan22/anatomy
ANATOMY_REV=1482e8469b0a9e0d8cc18ea2740a01423d29ae80
REA_VERSION=6.7.0

# Checks out <url> at <rev> into <dir>, or leaves it if it is already there
fetch_rev() {
  local url="$1" rev="$2" dir="$3"
  if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" != "$rev" ]; then
    rm -rf "$dir"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" fetch -q --depth 1 "$url" "$rev"
    git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
  fi
}

prepare_console_skill() {
  fetch_rev "$CONSOLE_SKILL_URL" "$CONSOLE_SKILL_REV" "$cache/console-skill"
}

prepare_anatomy() {
  fetch_rev "$ANATOMY_URL" "$ANATOMY_REV" "$cache/anatomy"
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

# Copies the skills that come with these servers into ~/.claude/skills, so the
# session also has their instructions (/anatomy, /console-reverse, ...)
install_skills() {
  local skills="$HOME/.claude/skills" src
  mkdir -p "$skills"
  for src in "$cache/anatomy" "$cache"/console-skill/console-*; do
    local name
    name="$(basename "$src")"
    rm -rf "${skills:?}/$name"
    cp -r "$src" "$skills/$name"
    rm -rf "$skills/$name/.git"
  done
}

prepare() {
  case "$1" in
    console-skill) prepare_console_skill ;;
    markitdown) prepare_markitdown ;;
    rea) prepare_rea ;;
    anatomy) prepare_anatomy ;;
    all) prepare_console_skill; prepare_markitdown; prepare_rea; prepare_anatomy ;;
    *) echo "unknown server: $1" >&2; exit 2 ;;
  esac
}

case "${1:-}" in
  prepare)
    prepare "${2:-all}"
    ;;
  skills)
    prepare_console_skill
    prepare_anatomy
    install_skills
    ;;
  run)
    # stdout belongs to the MCP protocol, so setup output goes to stderr
    prepare "${2:?server name}" >&2
    case "$2" in
      console-skill) exec python3 "$root/.claude/mcp/console_skill_server.py" --skills "$cache/console-skill" ;;
      markitdown) exec "$cache/markitdown-venv/bin/markitdown-mcp" ;;
      rea) exec "$cache/rea/node_modules/.bin/rea-agents" mcp ;;
      anatomy)
        # Cloud containers ship Chromium where Anatomy's browser checks do not look
        if [ -z "${CHROME_PATH:-}" ] && [ -x /opt/pw-browsers/chromium ]; then
          export CHROME_PATH=/opt/pw-browsers/chromium
        fi
        exec python3 "$root/.claude/mcp/anatomy_server.py" --anatomy "$cache/anatomy"
        ;;
    esac
    ;;
  *)
    echo "usage: setup.sh prepare [name|all] | setup.sh run <name> | setup.sh skills" >&2
    exit 2
    ;;
esac
