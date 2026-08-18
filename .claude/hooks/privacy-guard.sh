#!/usr/bin/env bash
# privacy-guard.sh — PreToolUse hook (Read|Bash matcher)
# Blocks reads/prints of secret files: .env*, *.pem, *.key, id_rsa/id_ed25519 (+ .pub allowed), .ssh/*, credentials.json.
# Exit 2 → blocks the tool call; Claude sees stderr as the reason.
# Exit 0 → passes through.
#
# For Bash, only blocks when a read/print-style command (cat, less, head, grep, python open, etc.)
# is combined with a secret path in the same command segment — a command that merely mentions
# ".env" in an unrelated string (e.g. an echo) is not blocked.
#
# stdin JSON: { "tool_name": "Read"|"Bash", "tool_input": { "file_path": "..." | "command": "..." }, ... }

set -uo pipefail

INPUT=$(cat)

RESULT=$(printf '%s' "$INPUT" | python3 -c "
import sys, json, re

SECRET_PATTERNS = [
    r'\.env(\.|\b|$)',
    r'\.pem\b',
    r'\.key\b',
    r'id_rsa\b',
    r'id_ed25519\b',
    r'(^|/)\.ssh/',
    r'credentials\.json\b',
]
READ_CMDS = r'\b(cat|less|more|head|tail|bat|strings|xxd|hexdump|od|vim?|nano|sed|awk|grep|egrep|scp|rsync|cp|python[0-9.]*|node|curl|wget)\b'
SEGMENT_SPLIT = re.compile(r'&&|\|\||[;&|\n]')

def is_secret(text):
    if text.endswith('.pub'):
        return False
    return any(re.search(p, text) for p in SECRET_PATTERNS)

try:
    data = json.load(sys.stdin)
except Exception:
    print('OK')
    sys.exit(0)

tool_name = data.get('tool_name', '')
tool_input = data.get('tool_input', {})

if tool_name == 'Read':
    file_path = tool_input.get('file_path', '')
    if file_path and is_secret(file_path):
        print('BLOCK:' + file_path)
        sys.exit(0)
    print('OK')
    sys.exit(0)

if tool_name == 'Bash':
    cmd = tool_input.get('command', '')
    for segment in SEGMENT_SPLIT.split(cmd):
        if re.search(READ_CMDS, segment) and is_secret(segment):
            print('BLOCK:' + segment.strip())
            sys.exit(0)
    print('OK')
    sys.exit(0)

print('OK')
" 2>/dev/null) || RESULT="OK"

if [[ "$RESULT" == BLOCK:* ]]; then
  echo "privacy-guard: blocked — command/read targets a secret file (${RESULT#BLOCK:})" >&2
  exit 2
fi

exit 0
