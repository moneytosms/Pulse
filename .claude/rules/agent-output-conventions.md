# Agent Output Conventions

House style for anything in this repo that talks back to Claude: hooks, agent definitions, skills, subagent reports, custom scripts. Adapted from AXI's agent-ergonomics principles (axi.md), scoped to what applies to a markdown/hooks-based setup.

## Truncation hints

Any hook, script, or subagent that cuts output short must say so — never truncate silently.

- Bad: dump first N lines, stop.
- Good: `showing 20/143 findings — pass --full for rest` (or equivalent escape hatch).
- Applies to: hook stdout, custom scripts, subagent summaries feeding back to main context.

## Definitive empty states

"Checked, found nothing" must be stated, never implied by silence — silence reads as "didn't run."

- `ReportFindings` with zero findings still needs one line: what was checked, that it's clean.
- Subagent reports: state explicitly when a search/check came back empty, don't just omit the section.

## Contextual disclosure (next-step suggestions)

End reports/skill runs with a concrete next command, not a generic pointer. Benchmark data (axi.md) shows this cuts follow-up turns ~30% because the agent doesn't have to ask what's next.

- Bad: "Tests are failing, you may want to investigate."
- Good: "3 tests failing in `auth.test.ts` — run `rtk test auth` to isolate."
- Applies to: skill output, subagent final summaries, ReportFindings-style tool results.
