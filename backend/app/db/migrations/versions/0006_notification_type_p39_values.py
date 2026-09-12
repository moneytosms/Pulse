"""notification_type: add BREAK_GLASS_ACCESS, DAILY_DIGEST

Phase 3, P3.9 (#43). The notification service needs these two types —
break-glass access is mandatory (never a preference row); the daily
digest for "a clinician viewed your records" is read-computed, never a
scheduler (domain-model.md, "Notifications"). `notification_type` was
created in migration 0005 with only the three types known at P3.1 time.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("BREAK_GLASS_ACCESS", "DAILY_DIGEST")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for an enum type. Downgrading this one
    # would mean rebuilding notification_type from scratch (drop-and-
    # recreate, same as any enum-shrink); not worth it for a dev-only
    # rollback path, so this migration is upgrade-only.
    pass
