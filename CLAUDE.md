# Pulse

> A lifelong electronic health record platform. Patients own their medical history; providers contribute to it; clinicians read it only with the patient's consent, and every access is recorded.

Academic project, four-person team, Indian demographic, four locales. **Never touches real patient data.** Architecture is locked; Phase 1 implementation has not started.

Read [`CONTEXT.md`](CONTEXT.md) before using any domain term — Patient, Consent, Permission and Medical Entry all mean something specific here.

## Stack

Versions are pinned in [`docs/tech-stack.md`](docs/tech-stack.md), including the traps. The most important one: **pin `typescript@6.0.3`, not 7.x** — TS 7 breaks type-aware ESLint.

- **Runtime:** Python 3.13 (backend) · Node 24 LTS (frontend)
- **Framework:** FastAPI 0.141 + SQLAlchemy 2.0 async · Next.js 16 App Router + React 19 + TypeScript 6
- **Key deps:** PostgreSQL 18, Redis 8, Alembic, Pydantic 2.13, `pwdlib[argon2]`, next-intl 4, Tailwind 4, Radix UI
- **Test:** `uv run pytest` · `npm test` — integration tests need Docker (real Postgres, testcontainers)
- **Lint:** `uv run ruff check .` + `uv run mypy .` · `npm run lint` + `npx tsc --noEmit`
- **Format:** `uv run ruff format .` · `npx prettier --write`
- **Build:** `docker compose build` · `npm run build`
- **Deploy:** `docker compose up`. The demo target is a laptop; there is no staging environment.
- **RTK wrappers:** confirmed via `rtk help`. Backend → `rtk pip` / `rtk ruff` / `rtk pytest` / `rtk mypy`; frontend → `rtk npm` / `rtk npx` / `rtk next`.

**No code is scaffolded yet.** The commands above are what Phase 0 sets up — see [`docs/delivery-plan.md`](docs/delivery-plan.md). Until then this repo is documentation only, and the correct response to "run the tests" is that there are none.

## Canary

Every completed task must end with: `[Canary:Pulse:TASK_NAME]`
Can't produce it = context dropped. Stop and say so.

## Tooling

- **RTK** — Bash output auto-compressed. First layer for ALL matching commands, raw only if no wrapper exists. See **RTK wrappers** in Stack above. Full list: `rtk help`.
- **ctx7** — `npx ctx7 library <name> <query>` before touching any external API. Never rely on training data for library APIs. This project's stack moves fast and several pins in `docs/tech-stack.md` exist precisely because the obvious version is wrong.
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

```
CONTEXT.md          Glossary. Definitions only, never implementation.
docs/               All project documentation. Start at docs/README-less index below.
  architecture.md     How Pulse is built and why. Examiner-facing.
  domain-model.md     Entities, columns, indexes, relationships.
  api-conventions.md  What every endpoint looks like. Read daily.
  delivery-plan.md    Who builds what, in what order, and where the waiting is.
  tech-stack.md       Pinned versions and the traps in them.
  seed-data.md        Synthea + Indian overlay pipeline; identity gaps and how they were closed.
  design-direction.md Typography and palette options for the first frontend task.
  learnings.md        Every non-obvious pattern: what it is, why here, what it replaces.
  adr/                Decisions that were expensive enough to write down. 0001–0015.
  agents/             How agents should use this repo's issue tracker and domain docs.
  archive/            Superseded initial specs. Do not follow these.
.claude/
  rules/              Loaded into context. clinical-safety, backend, database, frontend.
  decisions.md        Decision index. The long form lives in docs/adr/.
  errors.md           Major errors only. Append, never delete.
  agents/ commands/ hooks/   Agent definitions, slash commands, lifecycle hooks.
```

Planned, not yet scaffolded — `backend/app/{core,db,modules,adapters}`, `frontend/src`, `seed/`, `compose.yaml`, `Caddyfile`. Layout is specified in `docs/delivery-plan.md` (Phase 0).

## Scoped rules

`.claude/rules/` files load by glob match. Four exist:

- **`clinical-safety.md`** — applies everywhere, no exceptions. Access rules, what never goes in JSONB, what never goes in an audit event.
- **`backend.md`** · **`database.md`** · **`frontend.md`** — per-layer.

If a rule gets in the way, that is the rule working. Escalate rather than working around it — every one of them was decided against a named alternative.

## Learned rules

- **Contracts merge before implementations.** Schemas and repository signatures first, stubs second, real code third. A person blocked waiting on someone else's implementation means a gate was skipped.
- **Enforcement tests are cheap early and unpayable late.** The route-coverage test, the entry-query lint and the cross-module import lint land against three endpoints, not sixty.
- **Write the negative test first.** A positive test passes just as happily when the access filter was never applied.
- **Never state an unverified external fact in project documentation.** Two research passes hit blocked primary sources; both are recorded as unverified rather than smoothed over. A wrong numbering-plan claim in a graded submission is worse than an admitted gap.
- **The interface is localised; clinical data is not.** This one gets violated by accident, in the direction of helpfulness.

## Agent skills

### Issue tracker

GitHub Issues on `moneytosms/Pulse`, via `gh` CLI. See `docs/agents/issue-tracker.md`.

The planning map (#1) and its 15 tickets are closed. Live work is one build-plan ticket with four per-person slice tickets beneath it.

### Triage labels

Canonical defaults, label string equals role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
