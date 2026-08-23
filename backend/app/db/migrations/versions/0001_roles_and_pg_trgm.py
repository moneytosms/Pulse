"""roles and pg_trgm

Two Postgres roles, established here and used for the rest of the
project (ADR-0008): `pulse_migrator` (superuser/owner — this and every
future migration runs as it, matches compose.yaml's POSTGRES_USER
`pulse`) and `pulse_app` (the FastAPI app's runtime role, matches
compose.yaml's DATABASE_URL).

`audit_event` doesn't exist yet — no models are defined in Phase 0 —
so the INSERT/SELECT-only grant on it lands in the migration that
creates the table (Phase 3, per delivery-plan.md). Not done here via
`ALTER DEFAULT PRIVILEGES` on the schema: that would apply to every
future table `pulse_migrator` creates, silently capping `pulse_app` to
INSERT/SELECT on tables that need full CRUD (patients, consents,
etc). The audit table's append-only property has to be an explicit,
table-specific GRANT, not a blanket default.

Revision ID: 0001
Revises:
Create Date: 2026-08-23

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Dev/demo password, matching compose.yaml's DATABASE_URL. This
    # project never holds real patient data (see clinical-safety.md).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pulse_app') THEN
                CREATE ROLE pulse_app LOGIN PASSWORD 'pulse_app';
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT CONNECT ON DATABASE pulse TO pulse_app;")
    op.execute("GRANT USAGE ON SCHEMA public TO pulse_app;")

    # audit_event's INSERT/SELECT-only GRANT is added in the migration
    # that creates the table.


def downgrade() -> None:
    op.execute("REVOKE USAGE ON SCHEMA public FROM pulse_app;")
    op.execute("REVOKE CONNECT ON DATABASE pulse FROM pulse_app;")
    op.execute("DROP ROLE IF EXISTS pulse_app;")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
