"""Request/response models. Limits mirror the DB column sizes in db/migrate.py."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_STOCK = 1_000_000

Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]  # DECIMAL(10,2); NaN/Inf rejected
Sku = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Name = Annotated[str, Field(min_length=1, max_length=255)]
StockQty = Annotated[int, Field(ge=0, le=MAX_STOCK)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductCreate(StrictModel):
    sku: Sku
    name: Name
    price: Money
    safety_stock: StockQty = 0
    stock: StockQty = 0


class ProductUpdate(StrictModel):
    name: Name | None = None
    price: Money | None = None
    safety_stock: StockQty | None = None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    price: Decimal  # serialised as a string ("19.99") so clients never lose cents
    safety_stock: int
    stock: int


class InventoryStats(BaseModel):
    total_products: int
    total_units: int
    total_value: Decimal
    in_stock: int
    low_stock: int
    out_of_stock: int


class StockAdjustment(StrictModel):
    # Negative values are valid (shrinkage, manual corrections); zero is not.
    adjustment: int = Field(ge=-MAX_STOCK, le=MAX_STOCK)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("adjustment")
    @classmethod
    def non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("adjustment must not be zero")
        return v


class StockSet(StrictModel):
    stock: StockQty
    # Optional optimistic check: reject if someone changed stock since you read it.
    expected_stock: StockQty | None = None


class StockInfo(BaseModel):
    product_id: int
    sku: str
    name: str
    current_stock: int
    safety_stock: int
    is_low_stock: bool
    updated_at: datetime | None = None


class LowStockAlert(BaseModel):
    product_id: int
    sku: str
    name: str
    current_stock: int
    safety_stock: int


class ReservationItem(StrictModel):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=10_000)


class ReservationCreate(StrictModel):
    reservation_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    items: list[ReservationItem] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def unique_products(cls, items: list[ReservationItem]) -> list[ReservationItem]:
        if len({i.product_id for i in items}) != len(items):
            raise ValueError("each product_id may appear only once; merge quantities first")
        return items


class ReservationOut(BaseModel):
    reservation_id: str
    status: str
    items: list[ReservationItem]
    replayed: bool = False
