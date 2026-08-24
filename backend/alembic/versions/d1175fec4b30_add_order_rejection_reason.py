"""add order rejection reason

Revision ID: d1175fec4b30
Revises: 46b2f7826645
Create Date: 2026-08-24 10:01:14.222500

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1175fec4b30"
down_revision: str | None = "46b2f7826645"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("rejection_reason", sa.String(length=30), nullable=True)
    )
    op.create_check_constraint(
        "ck_orders_rejection_reason_matches_status",
        "orders",
        "(status = 'rejected') = (rejection_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_orders_rejection_reason_valid",
        "orders",
        "rejection_reason IS NULL OR rejection_reason IN "
        "('insufficient_funds', 'insufficient_holdings', 'stale_price', 'pair_not_tradable')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_rejection_reason_valid", "orders", type_="check")
    op.drop_constraint(
        "ck_orders_rejection_reason_matches_status", "orders", type_="check"
    )
    op.drop_column("orders", "rejection_reason")
