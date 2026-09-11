"""consent, access_permission, audit_event, notification, notification_preference

Phase 3, P3.1 (#37). `consent` is the Patient's agreement; `access_permission`
is the *live* enforcement row derived from it, kept lean so
`accessible_entries` never joins back to `consent` — its shape (and
`notification_preference`'s) is spelled out in issue #37, resolving an
ambiguity domain-model.md leaves open on purpose. A permission row is
deleted transactionally in the same revoke call that stamps
`consent.revoked_at` — that delete *is* the "no cached permission"
mechanism (clinical-safety.md), not a TTL.

`audit_event` is append-only by GRANT, not convention (ADR-0008): the
app role gets INSERT/SELECT only, no UPDATE/DELETE.

`notification` stores `type` + `params` JSONB, never rendered text.
Mandatory notification types (break-glass, consent changes, security)
never get a `notification_preference` row — enforced as an app-layer
allowlist, not a column.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FULL_CRUD_TABLES = (
    "consent",
    "access_permission",
    "notification",
    "notification_preference",
)

# create_type=False: the `role` enum already exists (migration 0002) and is
# reused here, denormalised at write time onto audit_event.actor_role.
role_enum = postgresql.ENUM(
    "PATIENT",
    "CLINICIAN",
    "PROVIDER_STAFF",
    "ADMINISTRATOR",
    name="role",
    create_type=False,
)

consent_purpose_enum = postgresql.ENUM(
    "TREATMENT", "SECOND_OPINION", "OTHER", name="consent_purpose", create_type=False
)

audit_action_enum = postgresql.ENUM(
    "ENTRY_VIEWED",
    "DOCUMENT_VIEWED",
    "CONSENT_GRANTED",
    "CONSENT_REVOKED",
    "BREAK_GLASS_ACCESS",
    "LOGIN_SUCCESS",
    "LOGIN_FAILURE",
    name="audit_action",
    create_type=False,
)

audit_outcome_enum = postgresql.ENUM(
    "SUCCESS", "DENIED", name="audit_outcome", create_type=False
)

notification_type_enum = postgresql.ENUM(
    "CONSENT_GRANTED",
    "CONSENT_REVOKED",
    "RECORD_UPLOADED",
    name="notification_type",
    create_type=False,
)

notification_channel_enum = postgresql.ENUM(
    "EMAIL", "SMS", "IN_APP", name="notification_channel", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    consent_purpose_enum.create(bind, checkfirst=True)
    audit_action_enum.create(bind, checkfirst=True)
    audit_outcome_enum.create(bind, checkfirst=True)
    notification_type_enum.create(bind, checkfirst=True)
    notification_channel_enum.create(bind, checkfirst=True)

    op.create_table(
        "consent",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grantee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("entry_types", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("purpose", consent_purpose_enum, nullable=False),
        sa.Column("purpose_text", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(500), nullable=True),
    )
    op.create_index("ix_consent_patient_id", "consent", ["patient_id"])
    op.create_index("ix_consent_grantee_user_id", "consent", ["grantee_user_id"])

    op.create_table(
        "access_permission",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grantee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("entry_types", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_access_permission_consent_id", "access_permission", ["consent_id"], unique=True
    )
    op.create_index("ix_access_permission_patient_id", "access_permission", ["patient_id"])
    op.create_index(
        "ix_access_permission_grantee_user_id", "access_permission", ["grantee_user_id"]
    )

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_role", role_enum, nullable=False),
        sa.Column("action", audit_action_enum, nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", audit_outcome_enum, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_event_actor_user_id", "audit_event", ["actor_user_id"])
    op.create_index("ix_audit_event_patient_id", "audit_event", ["patient_id"])

    op.create_table(
        "notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notification_user_id", "notification", ["user_id"])

    op.create_table(
        "notification_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notification_type", notification_type_enum, nullable=False),
        sa.Column("channel", notification_channel_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "notification_type",
            "channel",
            name="uq_notification_preference_user_type_channel",
        ),
    )
    op.create_index(
        "ix_notification_preference_user_id", "notification_preference", ["user_id"]
    )

    for table in _FULL_CRUD_TABLES:
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "{table}" TO pulse_app;'
        )
    # ADR-0008: append-only by GRANT, never UPDATE/DELETE for the app role.
    op.execute("GRANT SELECT, INSERT ON TABLE audit_event TO pulse_app;")


def downgrade() -> None:
    op.execute("REVOKE ALL ON TABLE audit_event FROM pulse_app;")
    for table in reversed(_FULL_CRUD_TABLES):
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM pulse_app;')

    op.drop_table("notification_preference")
    op.drop_table("notification")
    op.drop_table("audit_event")
    op.drop_table("access_permission")
    op.drop_table("consent")

    bind = op.get_bind()
    notification_channel_enum.drop(bind, checkfirst=True)
    notification_type_enum.drop(bind, checkfirst=True)
    audit_outcome_enum.drop(bind, checkfirst=True)
    audit_action_enum.drop(bind, checkfirst=True)
    consent_purpose_enum.drop(bind, checkfirst=True)
