# [PROJECT_NAME]

> [One sentence: what this project does.]

## Stack

- **Runtime:** <!-- Node 20, Python 3.12, etc. -->
- **Framework:** <!-- Next.js 14, FastAPI, etc. -->
- **Key deps:** <!-- Prisma, Redis, etc. -->
- **Test:** <!-- pnpm test, pytest, etc. -->
- **Lint:** <!-- npm run lint, ruff check ., etc. -->
- **Format:** <!-- prettier --write, ruff format . (set as PROJECT_FMT in settings.local.json) -->
- **Build:** <!-- pnpm build, cargo build --release -->
- **Deploy:** <!-- fly deploy, vercel --prod -->
- **RTK wrappers:** confirmed via `rtk help`. Frontend (Next.js/React/TS) → `rtk npm`/`rtk npx`/`rtk next`; backend (FastAPI/Python) → `rtk pip`/`rtk ruff`/`rtk pytest`/`rtk mypy`. No code scaffolded yet (only `docs/tech_stack_initial.md`) — commands are ready for when it lands.

## Canary

Every completed task must end with: `[Canary:PROJECT_NAME:TASK_NAME]`
Can't produce it = context dropped. Stop and say so.

## Tooling

- **RTK** — Bash output auto-compressed. First layer for ALL matching commands, raw only if no wrapper exists. See **RTK wrappers** in Stack above for this project's exact commands. Full list: `rtk help`.
- **ctx7** — `npx ctx7 library <name> <query>` before touching any external API. Never rely on training data for library APIs.
- **Caveman** — `/caveman` for long sessions. `/caveman off` to disable.
- **Commands** (`.claude/commands/`) — `/plan` scaffold plan file, `/batch` split+delegate to subagents, `/review` run CodeReviewer agent on diff, `/verify` project verification suite, `/ship` lint→build→test→commit→PR, `/commit` stage+commit+push, `/pr` open PR to main, `/checkpoint` write session state before ending a session or when context runs low (use this, not `/compact`).
- **Hooks** (`.claude/hooks/`) — auto-format on Edit/Write, git-guard blocks force-push/reset --hard/rm -rf, privacy-guard on Read/Bash, pre-deploy-guard on Bash, log-bash logs commands, session-start surfaces checkpoint/errors on startup, notify on idle/permission prompts, keep-going on Stop, statusline.

## Context rules

- Flag before any phase that risks one context window.
- Running low → `/checkpoint`, then stop. SessionStart hook will surface it.
- All commands must work headless.

## Error protocol

- **Minor** (typo, wrong flag): note inline, continue.
- **Major** (wrong architecture, repeated mistake):
  1. Append to `.claude/errors.md`
  2. If pattern → create `.claude/skills/<name>.md`
  3. If approach changes → append to **Learned rules** below

## Agent output conventions

Anything we build that talks back to Claude (hooks, agent defs, skills, subagent reports) follows `.claude/rules/agent-output-conventions.md`: no silent truncation, explicit empty states, end with a concrete next command.

## Agents

Ask before spawning and spawn using appropriate model according to the task. Defined in `.claude/agents/`.
`ReadOnly` · `BuildValidator` · `LogAnalyzer` · `Researcher` · `CodeReviewer` · `DocWriter`

## Folder map

Append the reference to each major folder here and what it containts. Each major dir has a `CLAUDE.md`. Follow the route to find the sections you need.

<!-- src/ — app logic | infra/ — do not edit generated files -->

## Scoped rules

`.claude/rules/` files load by glob match. Add per-project.

<!-- api.md → src/api/** | db.md → src/db/** -->

## Learned rules

<!-- Claude appends here on major errors. Do not delete. -->

## Agent skills

### Issue tracker

GitHub Issues on `moneytosms/Pulse`, via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical defaults, label string equals role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
