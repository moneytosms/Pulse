#!/usr/bin/env bash
# auto-format.sh — PostToolUse hook (Edit|Write matcher)
# Runs $PROJECT_FMT on the file that was just written/edited.
# No-ops silently if PROJECT_FMT is unset or empty.
# Always exits 0 — formatting failures must never block Claude.
#
# stdin JSON (Write):  { "tool_name": "Write", "tool_input": { "file_path": "...", "content": "..." }, ... }
# stdin JSON (Edit):   { "tool_name": "Edit",  "tool_input": { "file_path": "...", ... }, ... }
# Note: the field is file_path (not path) for both Write and Edit tools.

set -uo pipefail

# No-op if formatter not configured
[[ -z "${PROJECT_FMT:-}" ]] && exit 0

INPUT=$(cat)

# Extract file_path from tool_input.file_path (correct field name per Claude Code docs)
FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))
except: print('')
" 2>/dev/null) || FILE_PATH=""
FILE_PATH="${FILE_PATH:-}"

[[ -z "$FILE_PATH" ]]    && exit 0
[[ ! -f "$FILE_PATH" ]]  && exit 0

# Run formatter; suppress errors so they never surface to Claude
# Use printf to safely construct the command without eval quoting pitfalls
eval "$PROJECT_FMT $(printf '%q' "$FILE_PATH")" 2>/dev/null || true

exit 0
