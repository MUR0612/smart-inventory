"""ORM mapping only. The schema itself is owned by db/migrate.py (single source).

All timestamps are stored as UTC (naive DATETIME/TIMESTAMP with the session
time zone forced to UTC) and returned with an explicit +00:00 offset.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from .db import utcnow

Base = declarative_base()
Id = BigInteger().with_variant(Integer, "sqlite")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cross-service consistency bookkeeping (see services/order_workflow.py)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    inventory_sync: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    sync_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sync_error: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Id, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(Id, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Snapshot at order time, so order details need no extra inventory calls.
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
