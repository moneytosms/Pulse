#!/bin/bash
# Claude Code statusLine command. Receives session JSON on stdin.
# Line 1: model | dir | git branch(dirty)
# Line 2: context %, 5h rate limit usage

input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name')
DIR=$(echo "$input" | jq -r '.workspace.current_dir')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
FIVE_H=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
WEEK=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
DIRNAME="${DIR##*[/\\]}"

BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
DIRTY=""
if [ -n "$BRANCH" ] && [ -n "$(git -C "$DIR" status --porcelain 2>/dev/null)" ]; then
  DIRTY="*"
fi

RESET=$'\033[0m'
DIM=$'\033[2m'
CYAN=$'\033[36m'
MAGENTA=$'\033[35m'

if [ "$PCT" -ge 80 ]; then CTX_COLOR=$'\033[31m'
elif [ "$PCT" -ge 50 ]; then CTX_COLOR=$'\033[33m'
else CTX_COLOR=$'\033[32m'
fi

LINE1="${CYAN}[$MODEL]${RESET} ${DIRNAME}"
if [ -n "$BRANCH" ]; then
  LINE1="$LINE1 ${MAGENTA}${BRANCH}${DIRTY}${RESET}"
fi

LINE2="${CTX_COLOR}${PCT}% ctx${RESET}"
[ -n "$FIVE_H" ] && LINE2="$LINE2 ${DIM}|${RESET} 5h:$(printf '%.0f' "$FIVE_H")%"
[ -n "$WEEK" ] && LINE2="$LINE2 ${DIM}|${RESET} 7d:$(printf '%.0f' "$WEEK")%"

printf '%s\n' "$LINE1"
printf '%s\n' "$LINE2"
