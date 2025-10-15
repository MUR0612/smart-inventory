from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Numeric, BigInteger, Integer, DateTime, Text
from datetime import datetime
import pytz

Base = declarative_base()

def get_aest_time():
    """Get current time in AEST timezone"""
    aest = pytz.timezone('Australia/Sydney')
    return datetime.now(aest)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    total: Mapped[float] = mapped_column(Numeric(10,2), nullable=False, default=0.00)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_aest_time)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=get_aest_time, onupdate=get_aest_time)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10,2), nullable=False)
