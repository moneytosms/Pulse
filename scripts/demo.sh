#!/usr/bin/env bash
# Reset to clean seed data, bring the stack up, print what to click.
# Usage: scripts/demo.sh [--no-open]
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[demo] resetting to clean seed data..."
docker compose down -v
docker compose up --build -d --wait

echo
echo "[demo] stack healthy. Open:"
echo "  Patient / Clinician login:  http://localhost/en/login"
echo "  Mailpit (dev mail catcher): http://localhost:8025"
echo
echo "[demo] seeded accounts, password Pulse@demo1 for all:"
echo "  Patient (EN)      demo.patient.en@example.com"
echo "  Patient (HI)      demo.patient.hi@example.com"
echo "  Provider staff    staff000@example.com"
echo "  Clinician         clinician0@example.com"
echo "  Administrator     admin0@example.com"
echo
echo "[demo] full click-through + narration: docs/demo.md"
echo "[demo] video shot list:                docs/video-script.md"
echo "[demo] tear down after:                docker compose down -v"

if [[ "${1:-}" != "--no-open" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost/en/login" >/dev/null 2>&1 &
  sleep 1
  xdg-open "http://localhost/en/login" >/dev/null 2>&1 &   # second window for the clinician role
  xdg-open "http://localhost:8025" >/dev/null 2>&1 &
fi
