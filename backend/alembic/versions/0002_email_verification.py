"""email verification

Adds a nullable users.email_verified_at, a single-use email_verification_tokens table, and a
CHECK that emails are stored lowercased (the app normalizes on the way in). Greenfield — no
backfill; a dev DB with pre-existing mixed-case rows needs `UPDATE users SET email =
lower(email);` before this runs.

Revision ID: 0002_email_verification
Revises: 0001_initial
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_email_verification"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
    )
    op.create_check_constraint(
        "ck_users_email_lowercase", "users", "email = lower(email)"
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_constraint("ck_users_email_lowercase", "users", type_="check")
    op.drop_column("users", "email_verified_at")
