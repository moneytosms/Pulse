# /review

Invoke the CodeReviewer agent on the current diff. Ask permission before spawning.

## Usage

- `/review` — review all changes on this branch vs `main`
- `/review staged` — review only staged changes
- `/review <sha>` — review a specific commit

## Steps

1. Determine scope from the argument (default: `main..HEAD`)
2. Run the appropriate git command to get the diff:
   - Default: `git diff main..HEAD`
   - Staged: `git diff --staged`
   - Commit: `git show <sha>`
3. Ask permission to spawn `CodeReviewer`
4. On approval, spawn `CodeReviewer` with:
   - The full diff
   - The list of changed files with context
   - A note of what the changes are intended to do (ask me if unclear)
5. Return the review report verbatim — do not edit or summarise it

## Rules

- Always ask before spawning the agent
- Do not make edits based on review findings without explicit confirmation
- If the diff is empty, stop and report — nothing to review
- If there are no commits ahead of `main`, stop and report
