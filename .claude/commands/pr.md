# /pr

Create a pull request from current branch to main.

## Steps

1. Confirm not on `main` or `master`: `git branch --show-current`
2. Get commits since branch split: `git log main..HEAD --oneline`
3. Read the diff: `git diff main..HEAD`
4. Generate PR title (max 72 chars, imperative mood) and body:
   - **What**: one paragraph describing the change
   - **Why**: one paragraph on motivation
   - **Testing**: how this was verified
   - **Notes**: any caveats, follow-ups, or migration steps
5. Run: `gh pr create --title "<title>" --body "<body>"`
6. Report the PR URL

## Rules

- Do not squash or rebase commits before creating PR
- Do not include issue numbers unless the human specified them
- The body should be useful to a reviewer, not a summary of commits
- If the branch has no commits ahead of main, stop and report
