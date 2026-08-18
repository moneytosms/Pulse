# /checkpoint

Write current session state to `.claude/checkpoint.md`. Run before ending a mid-task session or when context is running low.

## Steps

1. Assess current state honestly
2. Overwrite `.claude/checkpoint.md` with the template below, filled in
3. Confirm the file was written

## Template

```markdown
## Checkpoint [YYYY-MM-DD HH:MM]
Status: <done | in-progress | blocked>
In progress: <what is currently mid-flight — be specific about file/function/step>
Next step: <exact next action to take when resuming — one line>
Blockers: <anything unresolved that prevents progress, or "none">
Context notes: <anything the next session needs to know that isn't in the code>
```

## Rules

- Be precise in "Next step" — vague checkpoints are useless
- "In progress" should name files and functions, not just describe tasks at a high level
- The SessionStart hook reads this file automatically on next session open
- If status is "done", the checkpoint is obsolete — clear it with "Status: done" and note what was completed
