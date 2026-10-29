#!/bin/bash
# Installs the MCP servers from .mcp.json before a cloud session starts, so they
# connect on the first try, and copies the skills that come with them.
# setup.sh skips whatever is already installed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

"${CLAUDE_PROJECT_DIR:-.}/.claude/mcp/setup.sh" prepare all
"${CLAUDE_PROJECT_DIR:-.}/.claude/mcp/setup.sh" skills

# Anatomy's browser checks do not look where cloud containers keep Chromium
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -x /opt/pw-browsers/chromium ]; then
  echo 'export CHROME_PATH="${CHROME_PATH:-/opt/pw-browsers/chromium}"' >> "$CLAUDE_ENV_FILE"
fi
