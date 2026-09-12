"""break_glass_access

Phase 3, P3.5/P3.7 (#41, #44). Break-glass is emergency access *without*
Consent (domain-model.md, "Break-glass") — it cannot reuse `access_permission`,
whose `consent_id` is a mandatory FK to a Patient's actual agreement. A
separate, minimal table: one row per grant, justification required,
time-boxed to exactly the granted window (`expires_at`, never open-ended).
No revoke — it simply expires.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "break_glass_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clinician_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("justification", sa.String(2000), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_break_glass_access_patient_id", "break_glass_access", ["patient_id"]
    )
    op.create_index(
        "ix_break_glass_access_clinician_user_id",
        "break_glass_access",
        ["clinician_user_id"],
    )
    # SELECT for `accessible_entries`'s rule-4 check, INSERT for the grant
    # flow (#44) — no UPDATE/DELETE, matching "no revoke, only expiry."
    op.execute("GRANT SELECT, INSERT ON TABLE break_glass_access TO pulse_app;")


def downgrade() -> None:
    op.drop_index("ix_break_glass_access_clinician_user_id", table_name="break_glass_access")
    op.drop_index("ix_break_glass_access_patient_id", table_name="break_glass_access")
    op.drop_table("break_glass_access")
