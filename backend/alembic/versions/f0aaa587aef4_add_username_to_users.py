"""add username to users

Revision ID: f0aaa587aef4
Revises: d1175fec4b30
Create Date: 2026-08-27 00:38:08.239808

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0aaa587aef4"
down_revision: str | None = "d1175fec4b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable first, backfill any pre-existing rows from the email local-part plus a
    # short id suffix (keeps it unique), then enforce NOT NULL + the constraints.
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE users SET username = "
        "left(split_part(email, '@', 1), 24) || '-' || left(id::text, 4) "
        "WHERE username IS NULL"
    )
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_check_constraint(
        "ck_users_username_length",
        "users",
        "char_length(username) BETWEEN 3 AND 32",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_username_length", "users", type_="check")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "username")
