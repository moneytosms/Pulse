# /verify

Project-specific verification suite.

**This is a placeholder. Fill in per project.**

## What to add here

Replace this file with the verification steps specific to your project. Examples:

- E2E tests: `npx playwright test`
- Type check: `tsc --noEmit`
- API contract validation: `dredd` or `schemathesis`
- Database migration dry-run
- Security scan: `npm audit`, `trivy`, `snyk`
- Lighthouse CI
- Domain-specific invariant checks

## Template

```markdown
# /verify

Run the full verification suite for this project.

## Steps

1. <step 1>
2. <step 2>
3. <step 3>

## Pass criteria

- <what "passing" means for this project>

## On failure

- <what to do when verification fails>
```

## Rules

- Verification should be read-only — no writes, no deploys
- Must be runnable headless (no browser pop-ups, no interactive prompts)
- Should complete in under 5 minutes or be broken into stages
