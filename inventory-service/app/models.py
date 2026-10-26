"""ORM mapping only. The schema itself is owned by db/migrate.py (single source)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from .db import utcnow

Base = declarative_base()

# BIGINT in MySQL, INTEGER in SQLite so unit tests get autoincrement.
Id = BigInteger().with_variant(Integer, "sqlite")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Id, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    safety_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=utcnow)


class Inventory(Base):
    __tablename__ = "inventory"
    product_id: Mapped[int] = mapped_column(Id, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=utcnow, onupdate=utcnow)


class StockReservation(Base):
    """One reservation per order; makes reserve/release/commit idempotent."""
    __tablename__ = "stock_reservations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # RESERVED | RELEASED | COMMITTED
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class StockReservationItem(Base):
    __tablename__ = "stock_reservation_items"
    reservation_id: Mapped[str] = mapped_column(String(64), ForeignKey("stock_reservations.id", ondelete="CASCADE"),
                                                primary_key=True)
    product_id: Mapped[int] = mapped_column(Id, ForeignKey("products.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
