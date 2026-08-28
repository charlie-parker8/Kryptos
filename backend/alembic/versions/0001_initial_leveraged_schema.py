"""initial leveraged-position schema

The one and only migration. Kryptos trades isolated-margin long/short positions; there is
no prior spot schema to migrate from (see docs/leverage-model.md). Upgrades cleanly from an
entirely empty database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "starting_cash_balance", sa.Numeric(precision=20, scale=2), nullable=False
        ),
        sa.Column("cash_balance", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint(
            "cash_balance >= 0", name="ck_users_cash_balance_nonnegative"
        ),
        sa.CheckConstraint(
            "starting_cash_balance > 0", name="ck_users_starting_cash_positive"
        ),
        sa.CheckConstraint(
            "char_length(username) BETWEEN 3 AND 32", name="ck_users_username_length"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("pair", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("leverage", sa.SmallInteger(), nullable=False),
        sa.Column("collateral", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("size", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "liquidation_price", sa.Numeric(precision=20, scale=8), nullable=False
        ),
        sa.Column("open_fee", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("close_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("close_fee", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("close_reason", sa.String(length=12), nullable=True),
        sa.Column(
            "opened_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column("closed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint("collateral > 0", name="ck_positions_collateral_positive"),
        sa.CheckConstraint("size > 0", name="ck_positions_size_positive"),
        sa.CheckConstraint(
            "entry_price > 0", name="ck_positions_entry_price_positive"
        ),
        sa.CheckConstraint(
            "liquidation_price > 0", name="ck_positions_liquidation_price_positive"
        ),
        sa.CheckConstraint(
            "leverage BETWEEN 1 AND 125", name="ck_positions_leverage_range"
        ),
        sa.CheckConstraint(
            "side IN ('long', 'short')", name="ck_positions_side_valid"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'liquidated')",
            name="ck_positions_status_valid",
        ),
        sa.CheckConstraint("pair LIKE '%/USD'", name="ck_positions_pair_usd_quoted"),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('user', 'liquidation', 'bankruptcy')",
            name="ck_positions_close_reason_valid",
        ),
        sa.CheckConstraint(
            "(status = 'open') = (closed_at IS NULL)",
            name="ck_positions_closed_at_matches_status",
        ),
        sa.CheckConstraint(
            "(status = 'open') = (close_price IS NULL)",
            name="ck_positions_close_price_matches_status",
        ),
        sa.CheckConstraint(
            "(status = 'open') = (close_reason IS NULL)",
            name="ck_positions_close_reason_matches_status",
        ),
        sa.CheckConstraint(
            "(status = 'open') = (realized_pnl IS NULL)",
            name="ck_positions_realized_pnl_matches_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_positions_user_idempotency_key"
        ),
    )
    op.create_index(
        "uq_positions_one_open_per_pair",
        "positions",
        ["user_id", "pair"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_positions_user_opened_id",
        "positions",
        ["user_id", sa.text("opened_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_positions_open_by_pair",
        "positions",
        ["pair"],
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "user_sessions",
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
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("cash_delta", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column(
            "cash_balance_after", sa.Numeric(precision=20, scale=2), nullable=False
        ),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("quantity_delta", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=_NOW,
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('position_open', 'position_close', 'liquidation', "
            "'bankruptcy_reset')",
            name="ck_ledger_entry_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"], ["positions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ledger_entries_position_id",
        "ledger_entries",
        ["position_id"],
        unique=False,
    )
    op.create_index(
        "ix_ledger_entries_user_created_id",
        "ledger_entries",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_table("ledger_entries")
    op.drop_table("user_sessions")
    op.drop_index("ix_positions_open_by_pair", table_name="positions")
    op.drop_index("ix_positions_user_opened_id", table_name="positions")
    op.drop_index("uq_positions_one_open_per_pair", table_name="positions")
    op.drop_table("positions")
    op.drop_table("users")
