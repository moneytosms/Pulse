#!/usr/bin/env bash
# log-bash.sh — PreToolUse hook (Bash matcher)
# Appends every Bash command + ISO-8601 timestamp to .claude/bash.log.
# Always exits 0 — must never block.
#
# stdin JSON: { "tool_name": "Bash", "tool_input": { "command": "..." }, ... }

set -uo pipefail

CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BASH_LOG="${CLAUDE_PROJECT_DIR}/.claude/bash.log"

INPUT=$(cat)

# Extract command from tool_input.command
CMD=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print(json.load(sys.stdin).get('tool_input', {}).get('command', '<unknown>'))
except: print('<unknown>')
" 2>/dev/null) || CMD="<unknown>"
CMD="${CMD:-<unknown>}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
touch "$BASH_LOG" 2>/dev/null
printf '[%s] %s\n' "$TIMESTAMP" "$CMD" >> "$BASH_LOG"

exit 0
