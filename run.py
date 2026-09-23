#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# ///
"""Start the Pulse stack: backend (with Postgres, Redis, Mailpit) healthy first, then frontend + Caddy.

Usage: uv run run.py [--build]
Extra args are passed to `docker compose up`. Ctrl+C stops following logs; containers keep running.
Stop with `docker compose down`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
extra = sys.argv[1:]


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True)


try:
    print("[run] backend (migrate + seed on first boot)...")
    compose("up", "-d", "--wait", *extra, "backend", "mailpit")
    print("[run] frontend + caddy...")
    compose("up", "-d", "--wait", *extra, "frontend", "caddy")
    print("[run] up: app http://localhost  |  mail http://localhost:8025")
    compose("logs", "-f", "--tail", "20", "backend", "frontend")
except subprocess.CalledProcessError as e:
    sys.exit(e.returncode)
except KeyboardInterrupt:
    print("\n[run] detached; containers still running. Stop: docker compose down")
