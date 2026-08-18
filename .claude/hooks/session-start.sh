#!/usr/bin/env bash
# session-start.sh — SessionStart hook
# Returns JSON with additionalContext (checkpoint + last command) and
# sessionTitle (current git branch, so the tab is always orientated).
#
# stdin: { "source": "startup"|"resume"|"clear"|"compact", ... }
# stdout: JSON — processed by Claude Code as hook output

set -uo pipefail

CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CHECKPOINT="${CLAUDE_PROJECT_DIR}/.claude/checkpoint.md"
BASH_LOG="${CLAUDE_PROJECT_DIR}/.claude/bash.log"

INPUT=$(cat)

SOURCE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('source', 'startup'))
except: print('startup')
" 2>/dev/null || echo "startup")

# Build context into a temp file (safe: handles newlines and special chars)
TMPCTX=$(mktemp)
trap 'rm -f "$TMPCTX"' EXIT

# Surface in-progress checkpoint
if [[ -f "$CHECKPOINT" ]] && grep -q "^Status: in-progress" "$CHECKPOINT" 2>/dev/null; then
  printf '=== CHECKPOINT (in-progress) ===\n' >> "$TMPCTX"
  cat "$CHECKPOINT" >> "$TMPCTX"
  printf '\n=================================\n' >> "$TMPCTX"
fi

# Surface last bash command for orientation (skip on /clear — context is gone anyway)
if [[ "$SOURCE" != "clear" ]] && [[ -f "$BASH_LOG" ]]; then
  LAST=$(grep -v '^#' "$BASH_LOG" 2>/dev/null | tail -1)
  [[ -n "$LAST" ]] && printf '\nLast command: %s\n' "$LAST" >> "$TMPCTX"
fi

# Current branch for session title (skip main/master — not informative)
BRANCH=$(git -C "$CLAUDE_PROJECT_DIR" branch --show-current 2>/dev/null || echo "")

# Emit JSON so we can set both additionalContext and sessionTitle in one response
python3 - "$SOURCE" "$BRANCH" "$TMPCTX" <<'PYEOF'
import sys, json

source  = sys.argv[1]
branch  = sys.argv[2]
tmpfile = sys.argv[3]

with open(tmpfile) as f:
    context = f.read().strip()

out = {"hookSpecificOutput": {"hookEventName": "SessionStart"}}

if context:
    out["hookSpecificOutput"]["additionalContext"] = context

# sessionTitle only on startup/resume — ignored on clear/compact per docs
if branch and branch not in ("main", "master", "") and source in ("startup", "resume"):
    out["hookSpecificOutput"]["sessionTitle"] = branch

print(json.dumps(out))
PYEOF

exit 0
