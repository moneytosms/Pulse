# /ship

Full ship sequence: lint → build → test → commit → PR. Stops on first failure.

## Steps

1. **Check working tree** — `git status`. Must be clean (no untracked or modified files outside staged). Warn if dirty.
2. **Lint** — run lint command from CLAUDE.md. Stop on failure, report errors.
3. **Build** — run build command from CLAUDE.md. Stop on failure, report errors.
4. **Test** — run test command from CLAUDE.md. Stop on failure, report failing tests.
5. **Commit** — run `/commit` command
6. **PR** — run `/pr` command

## Rules

- Abort at first failure. Do not continue to next step.
- Print the failed command and relevant error lines before stopping.
- Do not attempt to fix failures — report and stop.
- If lint/build/test commands are not set in CLAUDE.md, skip that step and warn.
- Do not run `/ship` if you are already on `main` or `master`.
