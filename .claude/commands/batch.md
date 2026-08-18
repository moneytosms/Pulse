# /batch

Split a large task into parallelisable subtasks and delegate to subagents.

## Steps

1. Decompose the task into independent subtasks (no shared write targets between subtasks)
2. For each subtask, identify:
   - What it does
   - Which files it reads/writes (must be disjoint from other subtasks)
   - Which agent is appropriate (ReadOnly, BuildValidator, etc.)
   - What the expected output is
3. **Ask permission** before spawning any agent — list the subtasks and agents first
4. On approval, spawn one subagent per subtask with a self-contained prompt
5. Collect all outputs
6. Merge results: resolve any conflicts, integrate findings, report summary

## Rules

- Never spawn agents without explicit permission
- Subtask write scopes must be disjoint — overlapping writes will corrupt state
- Include all necessary context in each subagent prompt (they have no shared memory)
- If a subtask fails, report it without blocking others that succeeded
- Prefer 2-4 subtasks. If you need more than 6, the task decomposition is too fine-grained.

## Use cases

- Large refactors touching many files
- Multi-file migrations
- Parallel research + implementation
- Running tests while generating documentation
