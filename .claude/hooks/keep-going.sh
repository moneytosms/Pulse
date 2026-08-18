#!/usr/bin/env bash
# keep-going.sh — Stop hook
# Prevents Claude from stopping when a task is genuinely mid-flight.
# Returns additionalContext (not decision:block) to give feedback without
# showing a hook error in the transcript.
#
# Decision order:
#   1. stop_hook_active=true  → exit 0 (prevents infinite loop — Claude Code
#                               sets this after already-continuing via a hook)
#   2. Canary in last_assistant_message → exit 0 (task complete, allow stop)
#   3. checkpoint shows in-progress    → output additionalContext, exit 0
#   4. default                         → exit 0 (allow stop)
#
# stdin JSON: { "stop_hook_active": bool, "last_assistant_message": "...", ... }
# stdout: JSON with hookSpecificOutput.additionalContext (or empty → allow stop)

set -uo pipefail

CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CHECKPOINT="${CLAUDE_PROJECT_DIR}/.claude/checkpoint.md"
CLAUDE_MD="${CLAUDE_PROJECT_DIR}/CLAUDE.md"

INPUT=$(cat)

# 1. Infinite-loop guard — Claude Code sets stop_hook_active=true after
#    this hook already fired once this turn. Never block again if set.
STOP_ACTIVE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print('true' if json.load(sys.stdin).get('stop_hook_active', False) else 'false')
except: print('false')
" 2>/dev/null || echo "false")
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

# 2. Canary check — if present in last message, task completed cleanly
LAST_MSG=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print(json.load(sys.stdin).get('last_assistant_message', ''))
except: print('')
" 2>/dev/null || echo "")

CANARY_PREFIX=$(grep -o '\[Canary:[^:]*:' "$CLAUDE_MD" 2>/dev/null | head -1)
if [[ -n "$CANARY_PREFIX" ]] && printf '%s' "$LAST_MSG" | grep -qF "$CANARY_PREFIX"; then
  exit 0  # canary found → task done, allow stop
fi

# 3. Checkpoint check — nudge only if an in-progress task is recorded
if [[ -f "$CHECKPOINT" ]] && grep -q "^Status: in-progress" "$CHECKPOINT" 2>/dev/null; then
  NEXT=$(grep "^Next step:" "$CHECKPOINT" 2>/dev/null | sed 's/^Next step:[[:space:]]*//' | head -1)
  NEXT="${NEXT:-see .claude/checkpoint.md}"

  # Return additionalContext so Claude continues without a hook-error notice
  python3 - "$NEXT" <<'PYEOF'
import sys, json
next_step = sys.argv[1]
msg = (
  "Task is still in progress per .claude/checkpoint.md. "
  f"Next step: {next_step}. "
  "Continue from that step. Run /checkpoint to update status when done."
)
print(json.dumps({
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "additionalContext": msg
  }
}))
PYEOF
  exit 0
fi

# 4. Default — allow stop
exit 0
