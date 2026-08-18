# Workflows

Workflows are JavaScript scripts that Claude can write and save here. Each file becomes a `/<name>` slash command automatically.

Unlike commands (which are static markdown prompts), workflows are dynamic — they can branch, loop, call tools, and compose other commands based on conditions.

## When to use a workflow vs a command

| Use a command when... | Use a workflow when... |
|---|---|
| The steps are always the same | Steps depend on conditions or prior results |
| It's a prompt / instruction set | It needs to branch or iterate |
| Simple, < 10 steps | Complex, multi-phase automation |

## How to create one

Ask Claude:
> "Create a workflow called `sync-schema` that pulls the latest DB schema, runs typegen, and reports any breaking changes."

Claude writes the script to `.claude/workflows/sync-schema.js` and it immediately becomes available as `/sync-schema`.

## Examples of good workflows

- `/sync-schema` — pull schema → run typegen → diff types → report
- `/seed-dev` — reset dev DB → run migrations → seed fixtures → confirm
- `/release-prep` — bump version → update changelog → `/ship`
- `/triage` — list open issues → group by label → suggest priorities

## Files here

This directory starts empty. Workflows are created by Claude as the project develops.
