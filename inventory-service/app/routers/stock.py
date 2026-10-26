"""Stock reads and manual staff changes.

Every write locks the inventory row (SELECT ... FOR UPDATE) inside one
transaction, so concurrent adjust / set / reserve / release requests are
serialised by MySQL and no update is lost.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from smart_shared.auth import READ_ROLES, WRITE_ROLES, authorize
from .. import cache, events
from ..db import as_utc, get_db, utcnow
from ..models import Inventory, Product
from ..schemas import LowStockAlert, StockAdjustment, StockInfo, StockSet

router = APIRouter(prefix="/api/inventory", tags=["stock"])

can_read = authorize(*READ_ROLES, allow_service=True)
can_write = authorize(*WRITE_ROLES)


def _info(p: Product, inv: Inventory) -> StockInfo:
    return StockInfo(product_id=p.id, sku=p.sku, name=p.name, current_stock=inv.stock,
                     safety_stock=p.safety_stock, is_low_stock=inv.stock <= p.safety_stock,
                     updated_at=as_utc(inv.updated_at))


def _locked(db: Session, product_id: int) -> tuple[Product, Inventory]:
    inv = db.execute(select(Inventory).where(Inventory.product_id == product_id).with_for_update()).scalar_one_or_none()
    product = db.get(Product, product_id) if inv else None
    if not inv or not product:
        db.rollback()
        raise HTTPException(status_code=404, detail="Product not found")
    return product, inv


@router.post("/stock/{product_id}/adjust", response_model=StockInfo, dependencies=[Depends(can_write)])
def adjust_stock(product_id: int, body: StockAdjustment, db: Session = Depends(get_db)):
    product, inv = _locked(db, product_id)
    old = inv.stock
    new = old + body.adjustment
    if new < 0:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Insufficient stock (available: {old})")
    inv.stock = new
    inv.updated_at = utcnow()
    db.commit()
    events.stock_changed(product, old, new, source="manual_adjust", reference=body.reason)
    cache.invalidate_products()
    return _info(product, inv)


@router.post("/stock/{product_id}/set", response_model=StockInfo, dependencies=[Depends(can_write)])
def set_stock(product_id: int, body: StockSet, db: Session = Depends(get_db)):
    """Physical stock count. Serialised with reservations by the same row lock."""
    product, inv = _locked(db, product_id)
    old = inv.stock
    if body.expected_stock is not None and body.expected_stock != old:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Stock changed meanwhile (current: {old})")
    inv.stock = body.stock
    inv.updated_at = utcnow()
    db.commit()
    events.stock_changed(product, old, body.stock, source="manual_set")
    cache.invalidate_products()
    return _info(product, inv)


@router.get("/stock/{product_id}", response_model=StockInfo, dependencies=[Depends(can_read)])
def get_stock(product_id: int, db: Session = Depends(get_db)):
    row = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id) \
        .filter(Product.id == product_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return _info(*row)


@router.get("/stock", response_model=list[StockInfo], dependencies=[Depends(can_read)])
def list_all_stock(db: Session = Depends(get_db)):
    rows = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id).order_by(Product.id).all()
    return [_info(p, inv) for p, inv in rows]


@router.get("/low-stock", response_model=list[LowStockAlert], dependencies=[Depends(can_read)])
def get_low_stock_products(db: Session = Depends(get_db)):
    rows = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id) \
        .filter(Inventory.stock <= Product.safety_stock).order_by(Product.id).all()
    return [LowStockAlert(product_id=p.id, sku=p.sku, name=p.name, current_stock=inv.stock,
                          safety_stock=p.safety_stock) for p, inv in rows]
