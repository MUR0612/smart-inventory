from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, Numeric, BigInteger, ForeignKey

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10,2), nullable=False, default=0.00)
    safety_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class Inventory(Base):
    __tablename__ = "inventory"
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
