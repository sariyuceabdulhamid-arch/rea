#!/bin/bash
# Installs the MCP servers from .mcp.json before a cloud session starts,
# so they connect on the first try. setup.sh skips whatever is already installed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

"${CLAUDE_PROJECT_DIR:-.}/.claude/mcp/setup.sh" prepare all
