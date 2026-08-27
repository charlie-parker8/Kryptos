import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
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


class Holding(Base):
    """A user's position in a base asset (e.g. "BTC") — never a pair; a holding isn't quoted against anything."""

    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
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
        UniqueConstraint("user_id", "symbol", name="uq_holdings_user_symbol"),
        CheckConstraint("quantity >= 0", name="ck_holdings_quantity_nonnegative"),
    )


class Order(Base):
    """`symbol` is the canonical trading pair (e.g. "BTC/USD"), not a bare asset — see the market-data adapter."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    execution_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    filled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_orders_user_idempotency_key"
        ),
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        CheckConstraint("side IN ('buy', 'sell')", name="ck_orders_side_valid"),
        CheckConstraint(
            "status IN ('pending', 'filled', 'rejected')", name="ck_orders_status_valid"
        ),
        CheckConstraint("symbol LIKE '%/USD'", name="ck_orders_symbol_usd_quoted"),
        CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_orders_rejection_reason_matches_status",
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('insufficient_funds', 'insufficient_holdings', 'stale_price', 'pair_not_tradable')",
            name="ck_orders_rejection_reason_valid",
        ),
    )


Index(
    "ix_orders_user_created_id",
    Order.user_id,
    Order.created_at.desc(),
    Order.id.desc(),
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
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
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
            "entry_type IN ('order_buy', 'order_sell', 'bankruptcy_reset')",
            name="ck_ledger_entry_type_valid",
        ),
    )


Index(
    "ix_ledger_entries_user_created_id",
    LedgerEntry.user_id,
    LedgerEntry.created_at.desc(),
    LedgerEntry.id.desc(),
)
