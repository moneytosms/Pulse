# /commit

Stage all changes, generate a concise commit message, commit, and push.

## Steps

1. Run `git status` to confirm there are changes to commit
2. Run `git diff --staged` and `git diff` to see what changed
3. Stage all: `git add -A`
4. Generate a commit message from the diff:
   - Imperative mood, present tense ("Add X" not "Added X")
   - Subject line max 50 chars, no trailing punctuation
   - Body only if genuinely useful (not a summary of the subject)
   - No co-author lines, no AI attribution
5. Commit: `git commit -m "<message>"`
6. Push: `git push`
   - If the branch has no upstream yet: `git push -u origin HEAD`

## Rules

- Never use `--force`
- If nothing staged after `git add -A`, stop and report
- If push fails (diverged), stop and report — do not rebase automatically
- The canary line from CLAUDE.md does NOT go in commit messages
