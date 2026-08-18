# /plan

Scaffold a structured plan file for a task or feature.

## Steps

1. Ask (or infer from context) the plan name — short, kebab-case
2. Get today's date: `date +%Y-%m-%d`
3. Create `.claude/plans/YYYY-MM-DD-<name>.md` with the template below
4. Fill in Goal, Constraints, and Acceptance Criteria from the context given
5. Leave Unresolved Questions blank for the human to answer
6. Report the file path created

## Template

```markdown
# Plan: <name>
Date: YYYY-MM-DD

## Goal
<One paragraph: what this plan accomplishes and why.>

## Constraints
- <hard limits: time, tech choices, must-not-touch areas>

## Acceptance Criteria
- [ ] <specific, testable condition>
- [ ] <specific, testable condition>

## Unresolved Questions
- [ ] <question that must be answered before or during execution>

## Tasks
<!-- Populated as work begins -->

## Progress
<!-- DocWriter appends here at session end -->
```

## Rules

- Do not start implementing. Plan only.
- If you lack enough context to fill Goal/Constraints/AC, run `/grill-me` first.
- Plans live in `.claude/plans/` — never in the project source tree.
