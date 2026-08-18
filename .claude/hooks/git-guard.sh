#!/usr/bin/env bash
# git-guard.sh — PreToolUse hook (Bash matcher)
# Explains *why* a destructive git/fs command is blocked and what to do instead,
# rather than relying on settings.json's deny list (silent, no reason surfaced).
# Exit 2 → blocks the tool call; Claude sees stderr as the reason.
# Exit 0 → passes through.
#
# stdin JSON: { "tool_name": "Bash", "tool_input": { "command": "..." }, ... }

set -uo pipefail

INPUT=$(cat)

CMD=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))
except: print('')
" 2>/dev/null) || CMD=""

[[ -z "$CMD" ]] && exit 0

# Strip quoted string literals (commit messages, echo text, etc.) so prose
# mentioning a dangerous pattern isn't mistaken for an actual invocation.
CMD=$(printf '%s' "$CMD" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")

[[ -z "$CMD" ]] && exit 0

block() {
  echo "git-guard: blocked — $1" >&2
  echo "next: $2" >&2
  exit 2
}

if echo "$CMD" | grep -qE '(^|[; ])git push[^|;&]*(--force([^-]|$)|-f\b)'; then
  block "force-push rewrites remote history, can wipe teammates' work" \
        "use 'git push --force-with-lease' after confirming with the user, or resolve via merge/rebase"
fi

if echo "$CMD" | grep -qE '(^|[; ])git reset[^|;&]*--hard'; then
  block "reset --hard discards uncommitted changes with no recovery path" \
        "run 'git status' first; stash ('git stash -u') if anything should be kept"
fi

if echo "$CMD" | grep -qE '(^|[; ])git clean[^|;&]*-[a-zA-Z]*[fx]'; then
  block "git clean -f/-x permanently deletes untracked files" \
        "run 'git clean -n' first to preview what would be removed"
fi

if echo "$CMD" | grep -qE '(^|[; ])rm[^|;&]*-[a-zA-Z]*r[a-zA-Z]*f|(^|[; ])rm[^|;&]*-[a-zA-Z]*f[a-zA-Z]*r'; then
  block "rm -rf permanently deletes files/dirs, no trash/recovery" \
        "confirm the exact path with the user, or move to a temp location instead of deleting"
fi

exit 0
