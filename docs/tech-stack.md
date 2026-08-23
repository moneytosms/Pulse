# Tech Stack and Pinned Versions

What Phase 0 installs, and the version traps that would otherwise cost a day each. Verified 2026-08-22; re-verify before the scaffold lands if that is more than a few weeks later.

The stack itself was locked during planning — see [`architecture.md`](./architecture.md). This document only decides *which versions*.

## Pins

| Component | Pin | Notes |
|---|---|---|
| Python | 3.13.x | Floor is 3.10 across the dependency set. 3.14 works; 3.13 is the safer default for a team installing secondary tooling. |
| FastAPI | 0.141.1 | |
| SQLAlchemy | 2.0.52 | **Not 2.1** — still beta. |
| Alembic | 1.19.1 | |
| Pydantic | 2.13.4 | |
| pwdlib[argon2] | 0.3.1 | Actively maintained. `passlib`'s last release is still 1.7.4 from 2020 — the rejection stands. |
| redis (client) | 8.1.0 | |
| asyncpg | 0.31.0 | |
| pytest · pytest-asyncio | 9.1.1 · 1.4.0 | |
| testcontainers[postgres] | 4.15.0 | |
| ruff · mypy | 0.16.4 · 2.3.1 | |
| uv | 0.12.5 | Dependency management. `pip-tools` 7.6.1 if the team prefers it. |
| Node | 24.19.0 LTS | Floor is 20.9.0 (Next) / 20.19.0 (ESLint). |
| Next.js | 16.3.2 | |
| React · react-dom | 19.2.8 | |
| **TypeScript** | **6.0.3** | **Not 7.x.** See the first landmine — this is the most important pin here. |
| Tailwind CSS | 4.3.3 | v4: CSS-first `@theme`, no `tailwind.config.js`. |
| Radix UI | `radix-ui` 1.6.7 | The unified package, not individual `@radix-ui/react-*` installs. |
| next-intl | 4.13.7 | |
| ESLint · eslint-config-next · typescript-eslint | 10.9.0 · 16.3.2 · 8.67.0 | |
| PostgreSQL | `postgres:18.6` | |
| Redis | `redis:8.8.2` | |
| Caddy | `caddy:2.11.4` | |
| Mailpit | `axllent/mailpit:v1.31.0` | Not under Docker Hub's `library/` namespace. |

## Landmines

### TypeScript 7 breaks type-aware ESLint

npm's `typescript@latest` is 7.x — the Go-native compiler — and it removed the programmatic compiler API that type-aware lint rules depend on. `typescript-eslint@8.67.0` excludes it outright (`typescript: >=4.8.4 <6.1.0`). Angular, Vue and ESLint's own tooling are in the same position. TypeScript 7.1 is expected to restore a stable API; until then **pin 6.0.3**. Installing "latest" means type-aware linting does not run at all — and it fails at install time, not at review time, which is at least loud.

### Pydantic: `populate_by_name` is deprecated

Soft-deprecated since 2.11. The current camelCase incantation:

```python
class PulseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )
```

Every tutorial still shows the old flag.

### SQLAlchemy async + joined-table inheritance

`selectin_polymorphic()` works under `AsyncSession` and is the documented fix for the `MissingGreenlet` crash that implicit lazy-loading of subclass attributes causes in async code. `AsyncAttrs` and `expire_on_commit=False` are still worth setting for other reasons, but neither one fixes this particular trap on its own.

### next-intl must not swallow `/api`

Caddy puts Next and FastAPI on the same origin ([ADR-0012](./adr/0012-same-origin-reverse-proxy.md)), so the locale middleware has to be told to leave API paths alone:

```js
export const config = { matcher: '/((?!api|_next|_vercel|.*\\..*).*)' };
```

Without it every API call gets a locale prefix rewritten onto it, and the symptom looks nothing like the cause.

### Next.js 16.3.2: `next build` crashes on `/_global-error`

Confirmed during Phase 0 scaffolding: `next build` fails prerendering `/_global-error` with `TypeError: Cannot read properties of null (reading 'useContext')`, on a stock scaffold with no custom code. Upstream Turbopack static-generation bug — see [vercel/next.js#95741](https://github.com/vercel/next.js/issues/95741) (best-diagnosed), also #86178, #84994, #94667. No fix exists in any published `16.3.x` release; `--webpack`, `experimental.prerenderEarlyExit`, `experimental.cpus`, `output: standalone` all fail to work around it. `next dev` and `next lint`/`tsc --noEmit` are unaffected — CI and the Dockerfile (`npm run dev`) don't hit this. Re-test on every `16.3.x` patch bump; drop this note once fixed upstream.

### postgres:18 changed its data volume mount point

`postgres:18+` images store data in a `pg_ctlcluster`-compatible layout and refuse to start if a volume is mounted at the old `18-`-era path `/var/lib/postgresql/data` — confirmed during Phase 0 integration (`docker compose up` failed with `Error: in 18+, these Docker images are configured to store database data in a format which is compatible with "pg_ctlcluster"...`). Mount the volume at `/var/lib/postgresql` (no `/data` suffix) instead; Postgres places its versioned subdirectory underneath on its own. See `compose.yaml`.

### testcontainers

The PyPI package is `testcontainers` (not `testcontainers-python`); import is `from testcontainers.postgres import PostgresContainer`, and `get_connection_url(driver=...)` is how you get an asyncpg URL rather than the psycopg default.

### pg_trgm

Ships in contrib but still needs `CREATE EXTENSION pg_trgm;` per database — it belongs in the first migration alongside the two database roles. **Confirmed via live smoke test during Phase 0 integration**: `CREATE EXTENSION pg_trgm;` on `postgres:18.6` (the Debian variant compose.yaml pins) succeeds and `pg_roles`/`pg_extension` reflect it after `alembic upgrade head`. The Alpine variant remains unconfirmed — not in use here, so untested by this pass.

## What was not verified

One item from the version research remains an honest gap: the `pg_trgm` bundling in `postgres:18-alpine` specifically (not the tag this project uses — `postgres:18.6`, the Debian variant, which Phase 0 integration confirmed live). The testcontainers Postgres module is confirmed through docs and package metadata but not yet exercised against a real test run (no test suite exists yet). Both cheap to settle when either becomes load-bearing.
