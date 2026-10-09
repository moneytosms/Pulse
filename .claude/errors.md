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

## [2026-09-12] Security review caught a missing authorization that no lint and no test flagged
What: P4.2's `identity_data_quality_flags` read Patient identity fields (DOB presence, phone, claim status) with no `actor` parameter at all. The commit security review flagged missing-authorization; none of the three enforcement lints, nor the 192 passing tests, said anything — the tests even quietly assumed the correct policy (owner-self and Administrator reads) without ever asserting the denial.
Why: The actor-first rule is worded around Medical Entries ("no function returning Medical Entries takes less than an actor") and its lint only scans `records/{service,repository}.py`. Identity data is not clinical data, so it slipped past the letter of the rule and its tooling — but a bare `patient_id` is still a capability, and a docstring naming the intended consumer is not authorization.
Rule: Any function that reads personal data — not just clinical data — takes an `actor` and gates on it, and the negative case (denied actor) gets a test, not an assumption. When P4.3 opens the admin module, extend `scripts/lint_actor_first.py` beyond `records/` so this is enforced by CI instead of by review luck.

## [2026-10-08] Edit scripts used repository paths from a package directory
What: Several frontend-review edit scripts failed before their intended writes because repository-relative paths were evaluated from frontend/ or backend/.
Why: File edits and package-specific verification were mixed in commands with different working directories.
Rule: Run repository-relative file edits from the repository root. Run package verification in separate commands with an explicit package directory; inspect each exit code.
