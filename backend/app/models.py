import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    starting_cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False
    )
    # Free cash — USD not committed as collateral to an open position. Collateral lives on
    # the `positions` row until the position closes. Account equity is derived server-side
    # as cash_balance + Σ(open position collateral + unrealized P&L); see app.account.
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("cash_balance >= 0", name="ck_users_cash_balance_nonnegative"),
        CheckConstraint(
            "starting_cash_balance > 0", name="ck_users_starting_cash_positive"
        ),
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint(
            "char_length(username) BETWEEN 3 AND 32", name="ck_users_username_length"
        ),
    )


class Position(Base):
    """One isolated-margin leveraged position on a USD pair.

    `collateral` is USD moved out of `users.cash_balance` at open; `size` is the base-asset
    quantity the collateral controls at `leverage` (`notional = collateral * leverage`,
    `size = notional / entry_price`). Entry, mark, exit and the stored `liquidation_price`
    all price off the Kraken `last` price. A position closes exactly once — `status` goes
    `open -> closed | liquidated` under a row lock (see app.positions.close_position), which
    is what makes close/liquidation races and retries safe without a second idempotency key.
    """

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    leverage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    collateral: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    liquidation_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    open_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal(0)
    )
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    close_fee: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(12), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_positions_user_idempotency_key"
        ),
        CheckConstraint("collateral > 0", name="ck_positions_collateral_positive"),
        CheckConstraint("size > 0", name="ck_positions_size_positive"),
        CheckConstraint("entry_price > 0", name="ck_positions_entry_price_positive"),
        CheckConstraint(
            "liquidation_price > 0", name="ck_positions_liquidation_price_positive"
        ),
        CheckConstraint("leverage BETWEEN 1 AND 125", name="ck_positions_leverage_range"),
        CheckConstraint("side IN ('long', 'short')", name="ck_positions_side_valid"),
        CheckConstraint(
            "status IN ('open', 'closed', 'liquidated')",
            name="ck_positions_status_valid",
        ),
        CheckConstraint("pair LIKE '%/USD'", name="ck_positions_pair_usd_quoted"),
        CheckConstraint(
            "close_reason IS NULL OR close_reason IN ('user', 'liquidation', 'bankruptcy')",
            name="ck_positions_close_reason_valid",
        ),
        # An open position has no close data; a terminal one has all of it.
        CheckConstraint(
            "(status = 'open') = (closed_at IS NULL)",
            name="ck_positions_closed_at_matches_status",
        ),
        CheckConstraint(
            "(status = 'open') = (close_price IS NULL)",
            name="ck_positions_close_price_matches_status",
        ),
        CheckConstraint(
            "(status = 'open') = (close_reason IS NULL)",
            name="ck_positions_close_reason_matches_status",
        ),
        CheckConstraint(
            "(status = 'open') = (realized_pnl IS NULL)",
            name="ck_positions_realized_pnl_matches_status",
        ),
    )


# At most one open position per (user, pair) — enforces "no simultaneous hedged positions"
# and "one position per pair". Closed/liquidated rows are unconstrained so history keeps.
Index(
    "uq_positions_one_open_per_pair",
    Position.user_id,
    Position.pair,
    unique=True,
    postgresql_where=Position.status == "open",
)

# History pagination (GET /positions), same keyset shape as orders/ledger before it.
Index(
    "ix_positions_user_opened_id",
    Position.user_id,
    Position.opened_at.desc(),
    Position.id.desc(),
)

# The per-tick liquidation scan: "every open position on this pair".
Index(
    "ix_positions_open_by_pair",
    Position.pair,
    postgresql_where=Position.status == "open",
)


class UserSession(Base):
    """An issued login session. `token_hash` stores SHA-256(raw token) — the raw token itself
    lives only in the client's cookie and is never persisted, so a DB read alone can't forge one.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class LedgerEntry(Base):
    """Append-only record of every movement of free cash. `cash_balance_after` is the
    running `users.cash_balance` after the entry; a position round trip is
    `position_open` (−collateral) then `position_close`/`liquidation` (+collateral ± P&L),
    netting to realized P&L. A `bankruptcy_reset` entry jumps the balance to starting cash.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cash_balance_after: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity_delta: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 10), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('position_open', 'position_close', 'liquidation', "
            "'bankruptcy_reset')",
            name="ck_ledger_entry_type_valid",
        ),
    )


Index(
    "ix_ledger_entries_user_created_id",
    LedgerEntry.user_id,
    LedgerEntry.created_at.desc(),
    LedgerEntry.id.desc(),
)
