#!/usr/bin/env bash
# notify.sh — Notification hook (idle_prompt | permission_prompt)
# Sends a desktop alert so you know when Claude needs attention.
# Runs async — never blocks Claude.
#
# stdin: { "notification_type": "...", "message": "...", "title": "..." }
# Supports: macOS (osascript), Linux (notify-send), WSL (powershell.exe)

set -uo pipefail

INPUT=$(cat)

MESSAGE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:    print(json.load(sys.stdin).get('message', 'Claude Code needs your attention'))
except: print('Claude Code needs your attention')
" 2>/dev/null || echo "Claude Code needs your attention")

TITLE="Claude Code"

# Sanitize: strip quotes and limit length so shell interpolation is safe
MESSAGE=$(printf '%s' "$MESSAGE" | head -c 200 | tr "'" ' ' | tr '"' ' ')

# macOS
if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\"" 2>/dev/null || true

# Linux with a notification daemon (GNOME, KDE, etc.)
elif command -v notify-send >/dev/null 2>&1; then
  notify-send --urgency=normal --expire-time=4000 "$TITLE" "$MESSAGE" 2>/dev/null || true

# WSL — call PowerShell toast notification
elif command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -NonInteractive -Command "
    [void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
    \$n = New-Object System.Windows.Forms.NotifyIcon
    \$n.Icon = [System.Drawing.SystemIcons]::Information
    \$n.Visible = \$true
    \$n.ShowBalloonTip(4000, '$TITLE', '$MESSAGE', 'Info')
    Start-Sleep -Milliseconds 4500
    \$n.Dispose()
  " 2>/dev/null &
fi

exit 0
