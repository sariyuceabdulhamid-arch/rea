#!/bin/bash
# Clone the reference repositories next to this checkout in Claude Code cloud
# sessions, so every session can read them without asking for them again.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REFERENCE_REPOS=(
  anthropics/anthropic-quickstarts
  continuedev/continue
)

root="$(dirname "${CLAUDE_PROJECT_DIR:-$PWD}")"
available=()
for repo in "${REFERENCE_REPOS[@]}"; do
  target="$root/$repo"
  if ! git -C "$target" rev-parse --git-dir >/dev/null 2>&1; then
    mkdir -p "$(dirname "$target")"
    # Public repositories only; LFS objects are not served to anonymous reads.
    if ! GIT_LFS_SKIP_SMUDGE=1 GIT_TERMINAL_PROMPT=0 git clone --quiet --depth 1 \
      "https://github.com/$repo" "$target" >&2; then
      echo "Could not clone $repo; continuing without it." >&2
      continue
    fi
  fi
  available+=("$target")
done

# SessionStart stdout is added to Claude's context.
if [ "${#available[@]}" -gt 0 ]; then
  echo "Read-only reference repositories cloned for this session:"
  printf -- '- %s\n' "${available[@]}"
fi
