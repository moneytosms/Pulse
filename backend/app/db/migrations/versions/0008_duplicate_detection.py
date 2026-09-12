"""duplicate_detection

Phase 4, P4.1 (#52). Deduplication is over Patient identities
(domain-model.md, "Duplicate detection"): a GIN trigram index on
`patient.full_name` backs the blocking query's trigram-hit rule; the
other two blocking rules (same birth year, same phone) use the existing
`date_of_birth`/`phone` columns and need no new index.

`patient.merged_into_id` tombstones the losing side of a merge — never
deleted, so audit events referencing it stay resolvable (ADR-0011).
`duplicate_review_item` records a pair's status (`PENDING` unless marked
otherwise) so a pair marked NOT_DUPLICATE is never re-flagged.
`patient_merge` is the reversal record: which patient absorbed which,
who did it, and when — reversal reads this row rather than recomputing
anything.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient",
        sa.Column(
            "merged_into_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_patient_merged_into_id", "patient", ["merged_into_id"])

    # pg_trgm extension is created in migration 0001; this is the index
    # that makes a trigram-hit blocking predicate (`full_name % :name`)
    # sargable instead of a sequential scan.
    op.execute(
        "CREATE INDEX ix_patient_full_name_trgm ON patient USING gin (full_name gin_trgm_ops)"
    )

    op.create_table(
        "duplicate_review_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id_a",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id_b",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("patient_id_a", "patient_id_b", name="uq_duplicate_review_item_pair"),
    )
    op.create_index(
        "ix_duplicate_review_item_patient_id_a", "duplicate_review_item", ["patient_id_a"]
    )
    op.create_index(
        "ix_duplicate_review_item_patient_id_b", "duplicate_review_item", ["patient_id_b"]
    )

    op.create_table(
        "patient_merge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "winner_patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column(
            "loser_patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        # Every row moved from loser to winner, so a reversal can move it
        # back without recomputing what "belonged to the loser" means.
        sa.Column("moved_entry_ids", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_patient_merge_winner_patient_id", "patient_merge", ["winner_patient_id"])
    op.create_index("ix_patient_merge_loser_patient_id", "patient_merge", ["loser_patient_id"])

    for table in ("duplicate_review_item", "patient_merge"):
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "{table}" TO pulse_app;')


def downgrade() -> None:
    for table in ("duplicate_review_item", "patient_merge"):
        op.execute(f'REVOKE ALL ON TABLE "{table}" FROM pulse_app;')
    op.drop_table("patient_merge")
    op.drop_table("duplicate_review_item")
    op.execute("DROP INDEX IF EXISTS ix_patient_full_name_trgm")
    op.drop_index("ix_patient_merged_into_id", table_name="patient")
    op.drop_column("patient", "merged_into_id")
