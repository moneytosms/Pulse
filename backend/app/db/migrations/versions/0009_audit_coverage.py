"""Add security and mutation actions; failed authentication has no actor role.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for action in (
            "ENTRY_CREATED",
            "ENTRY_CORRECTED",
            "DOCUMENT_UPLOADED",
            "ANALYTICS_VIEWED",
            "PATIENT_MERGED",
            "MERGE_REVERSED",
            "ACCESS_DENIED",
            "LOGOUT",
            "LOGOUT_ALL",
            "STEP_UP_SUCCESS",
            "STEP_UP_FAILURE",
        ):
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")
    op.alter_column("audit_event", "actor_role", nullable=True)
    op.create_index("ix_medical_entry_superseded_by", "medical_entry", ["superseded_by_id"])


def downgrade() -> None:
    op.drop_index("ix_medical_entry_superseded_by", "medical_entry")
    # Retain enum values and nullable historical actors: removing either would
    # destroy security history. Downgrade changes no existing audit rows.
