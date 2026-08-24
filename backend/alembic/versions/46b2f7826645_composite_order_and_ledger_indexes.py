"""composite order and ledger indexes

Revision ID: 46b2f7826645
Revises: b452d76da4e3
Create Date: 2026-08-22 21:16:00.846082

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "46b2f7826645"
down_revision: str | None = "b452d76da4e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Composite indexes support the "most recent orders/ledger entries for a
    # user" queries (ORDER BY created_at DESC, id DESC LIMIT n) directly, so
    # the single-column user_id indexes below become redundant (user_id is
    # still their leading column, so equality filtering on it isn't lost).
    op.execute(
        "CREATE INDEX ix_orders_user_created_id "
        "ON orders (user_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_ledger_entries_user_created_id "
        "ON ledger_entries (user_id, created_at DESC, id DESC)"
    )
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_index("ix_ledger_entries_user_id", table_name="ledger_entries")
    # uq_holdings_user_symbol UNIQUE(user_id, symbol) already covers user_id
    # lookups as its leading column.
    op.drop_index("ix_holdings_user_id", table_name="holdings")


def downgrade() -> None:
    op.create_index("ix_holdings_user_id", "holdings", ["user_id"], unique=False)
    op.create_index(
        "ix_ledger_entries_user_id", "ledger_entries", ["user_id"], unique=False
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)
    op.execute("DROP INDEX ix_ledger_entries_user_created_id")
    op.execute("DROP INDEX ix_orders_user_created_id")
