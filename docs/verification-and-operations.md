# Verification and local operations

Pulse is an academic demo with synthetic data. The current implementation includes records and corrections, documents, scoped consent and emergency access, access history, notifications, analytics and administrator duplicate review.

## Reproduce the checks

```bash
cd backend
uv sync --frozen --group dev
uv run ruff check .
uv run mypy .
uv run python scripts/lint_cross_module_imports.py
uv run python scripts/lint_module_sql.py
uv run python scripts/lint_entry_query.py
uv run python scripts/lint_actor_first.py
uv run python scripts/stub_inventory.py
uv run python scripts/generate_api.py --check
uv run pytest
```

Backend integration tests start isolated real PostgreSQL/Redis containers and require Docker.

```bash
cd frontend
npm ci
npm run check:locales
npm run lint
npm run typecheck
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

From the repository root, `docker compose up --build -d --wait` starts the demo. Then `cd frontend && npm run test:e2e:live` rehearses file → grant → clinician read → patient audit → revoke → lockout against the real stack. Mocked browser tests complement that live test and do not establish server-side authorization. To check a production build with the Docker Node runtime, use `docker compose run --rm --no-deps -e NODE_ENV=production frontend npm run build`; the demo service deliberately runs with NODE_ENV=development.

## Storage and readiness

`pulse_pgdata` holds PostgreSQL and `pulse_uploads` holds documents at `/data/uploads`. Backend replacement preserves both. `docker compose down` preserves volumes; `docker compose down -v` destroys demo data. When overriding `PULSE_UPLOAD_DIR`, mount persistent storage at that same path.

`/api/v1/health` is process liveness. `/api/v1/ready` checks database SELECT 1, Redis PING and a writable/fsync-capable upload directory within a three-second budget. A failure returns a coded 503. Readiness is not a backup, restore, free-space, or delivery guarantee.

Uploads are bounded at 25 MiB in the application and 27 MB at Caddy including multipart overhead. Writes use atomic file replacement; database failure removes newly written bytes. Missing files return controlled 404; checksum mismatch fails closed. A process crash between file write and database commit can still leave an orphan, so a production storage lifecycle needs reconciliation. Database metadata and uploads must be backed up and restored as one dataset; no restore drill is claimed here.

## Deployment boundary and remaining product work

HTTP, known synthetic credentials, Mailpit and Next.js development serving are intentional local-demo choices. Before exposing the app beyond that scope, supply a separate deployment configuration with HTTPS, `PULSE_SECURE_COOKIES=1`, production frontend serving, external credentials, trusted reverse-proxy addresses, and tested database/file restores. The current IP throttle/audit observes the peer accepted by the ASGI server; behind Caddy an unconfigured forwarded-address trust policy aggregates clients under the proxy IP. Set and validate a restricted trusted-proxy policy for the deployment network. Account throttles still apply independently. Cookie-authenticated mutations reject cross-site Origin/Fetch metadata; this is not a substitute for transport security.

The application does not yet expose provider-created unclaimed-patient onboarding/claim reconciliation, credential-change or admin-role-management workflows. These require explicit product and identity-proofing policies. Nullable patient ownership remains intentional. Human review of Hindi/Tamil/Malayalam, load testing, accessibility certification, and backup/restore rehearsal remain acceptance work; automated locale checks do not certify translation quality. No compliance certification or real-patient readiness is claimed.
