# Error Log

Major errors only. Claude appends; humans review. Never delete entries.

Format:
```
## [YYYY-MM-DD] <title>
What: <what went wrong>
Why: <root cause>
Rule: <what to do differently going forward>
```

---

<!-- Entries appended below by Claude or DocWriter agent -->

## [2026-08-23] Documentation reported as delivered while still on an unmerged branch
What: #16 reported `docs/tech-stack.md`, `docs/seed-data.md`, `docs/delivery-plan.md`, `docs/design-direction.md`, ADR-0012 to ADR-0015, the expanded `learnings.md` and the four `.claude/rules/` files as delivered. All of them existed only on `claude/project-status-check-8ok8m2`. `main` had none of them, so every issue linking those paths pointed at a 404, and the next session read the repo as if the work had been lost.
Why: The work was committed and pushed to a branch, and the ticket was resolved on the strength of the commits existing rather than on them being on `main`. Nothing verified the merge.
Rule: A ticket is resolved when its artifact is on `main`. Before closing one that claims a file exists, check the file on `main` — `git log origin/main -- <path>`, not `git log --all`. The same rule the delivery plan already states for code applies to documentation: merged, not written.
