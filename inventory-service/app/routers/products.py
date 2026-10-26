from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smart_shared.auth import READ_ROLES, WRITE_ROLES, authorize
from .. import cache
from ..db import get_db
from ..models import Inventory, Product
from ..schemas import InventoryStats, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/api/inventory", tags=["products"])

can_read = authorize(*READ_ROLES, allow_service=True)
can_write = authorize(*WRITE_ROLES)


def _out(p: Product, inv: Inventory) -> ProductOut:
    return ProductOut(id=p.id, sku=p.sku, name=p.name, price=p.price, safety_stock=p.safety_stock, stock=inv.stock)


def _joined(db: Session):
    return db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id)


@router.post("/products", response_model=ProductOut, status_code=201, dependencies=[Depends(can_write)])
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    if db.query(Product.id).filter_by(sku=body.sku).first():
        raise HTTPException(status_code=409, detail="SKU already exists")
    p = Product(sku=body.sku, name=body.name, price=body.price, safety_stock=body.safety_stock)
    try:
        db.add(p)
        db.flush()
        inv = Inventory(product_id=p.id, stock=body.stock)
        db.add(inv)
        db.commit()
    except IntegrityError:
        # Two concurrent creates with the same SKU: the unique index decides.
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists")
    cache.invalidate_products()
    return _out(p, inv)


@router.get("/products", response_model=list[ProductOut], dependencies=[Depends(can_read)])
def list_products(response: Response, db: Session = Depends(get_db)):
    gen = cache.current_generation()  # read before MySQL; see cache.py
    if gen is not None:
        cached = cache.get_products(gen)
        if cached is not None:
            response.headers["X-Cache"] = "hit"
            return cached
    result = [_out(p, inv) for p, inv in _joined(db).order_by(Product.id).all()]
    if gen is not None:
        cache.store_products(gen, [r.model_dump(mode="json") for r in result])
    response.headers["X-Cache"] = "miss" if gen is not None else "bypass"
    return result


@router.get("/stats", response_model=InventoryStats, dependencies=[Depends(can_read)])
def inventory_stats(db: Session = Depends(get_db)):
    """Aggregates computed in SQL with DECIMAL arithmetic (no client-side float sums)."""
    stock, safety = Inventory.stock, Product.safety_stock
    row = db.execute(
        select(
            func.count(Product.id),
            func.coalesce(func.sum(stock), 0),
            func.coalesce(func.sum(Product.price * stock), 0),
            func.coalesce(func.sum(case((stock > safety, 1), else_=0)), 0),
            func.coalesce(func.sum(case(((stock > 0) & (stock <= safety), 1), else_=0)), 0),
            func.coalesce(func.sum(case((stock == 0, 1), else_=0)), 0),
        ).select_from(Product).join(Inventory, Product.id == Inventory.product_id)
    ).one()
    return InventoryStats(total_products=row[0], total_units=row[1],
                          total_value=Decimal(row[2]).quantize(Decimal("0.01")),
                          in_stock=row[3], low_stock=row[4], out_of_stock=row[5])


@router.get("/products/{product_id}", response_model=ProductOut, dependencies=[Depends(can_read)])
def get_product(product_id: int, db: Session = Depends(get_db)):
    row = _joined(db).filter(Product.id == product_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return _out(*row)


@router.put("/products/{product_id}", response_model=ProductOut, dependencies=[Depends(can_write)])
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update")
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    cache.invalidate_products()
    return _out(product, db.get(Inventory, product_id))


@router.delete("/products/{product_id}", dependencies=[Depends(can_write)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        # FKs from order_items / stock_reservation_items protect history. This is
        # the shared-database coupling documented in docs/architecture.md.
        db.rollback()
        raise HTTPException(status_code=409, detail="Product is referenced by orders or reservations")
    cache.invalidate_products()
    return {"message": "Product deleted"}
