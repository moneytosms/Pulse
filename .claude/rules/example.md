# Example Rules File

This file shows the format for scoped rules in `.claude/rules/`.
**Rename this file and replace its content** with rules specific to your project domain.

Rules files are plain markdown loaded automatically into Claude's context.
They can optionally be path-gated so they only load when Claude is working in a matching directory.
See the Claude Code docs on rules for the full frontmatter syntax.

---

## How to write good rules

Rules should be short, imperative, and specific. One idea per bullet.
Tell Claude what to do, what never to do, and why in one line if the reason isn't obvious.

**Good:**
- Never log request bodies — they may contain PII
- Use `db.transaction()` for any multi-step write — never raw queries in app code
- All public API routes require the `authenticate` middleware

**Too vague:**
- Be careful with the database
- Follow security best practices

---

## Example: API rules (`api.md`)

```markdown
# API Rules

- Validate all input with Zod before processing — never trust raw req.body
- Return consistent error shapes: `{ error: string, code: string }`
- Never log request bodies or Authorization headers
- Auth middleware must be applied to every route; no unauthenticated endpoints
- Rate limiting is required on all public endpoints
- Use 422 for validation errors, 401 for auth errors, 403 for permission errors
```

## Example: database rules (`db.md`)

```markdown
# Database Rules

- All multi-step writes must use a transaction — never rely on individual queries being atomic
- Never write raw SQL in application code; use the ORM query builder
- Migrations live in `db/migrations/` — never edit a migration after it has been applied in any env
- Add an index for every foreign key column
```

## Example: infrastructure rules (`infra.md`)

```markdown
# Infrastructure Rules

- This directory is managed by Terraform — never edit generated files manually
- All secrets are injected via environment variables; never hardcode values
- Infrastructure changes require a `terraform plan` review before `terraform apply`
```

---

Delete this file and create domain-specific ones as your project structure emerges.
