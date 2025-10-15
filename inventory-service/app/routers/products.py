from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Product, Inventory
from ..cache import get_redis
import json
from typing import Optional

router = APIRouter(prefix="/api/inventory", tags=["products"])

class ProductCreate(BaseModel):
    sku: str
    name: str
    price: float
    safety_stock: int = 0
    stock: int = 0

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    safety_stock: Optional[int] = None

class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    price: float
    safety_stock: int
    stock: int

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/products", response_model=ProductOut)
def create_product(body: ProductCreate, db: Session = Depends(get_db)):
    existing = db.query(Product).filter_by(sku=body.sku).first()
    if existing:
        raise HTTPException(status_code=409, detail="SKU already exists")
    p = Product(sku=body.sku, name=body.name, price=body.price, safety_stock=body.safety_stock)
    db.add(p); db.flush()
    inv = Inventory(product_id=p.id, stock=body.stock)
    db.add(inv); db.commit(); db.refresh(p)

    # 失效快取
    try:
        r = get_redis()
        r.delete("products:list:v1")
    except Exception:
        pass

    return ProductOut(id=p.id, sku=p.sku, name=p.name, price=float(p.price), safety_stock=p.safety_stock, stock=inv.stock)

@router.get("/products", response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db)):
    r = get_redis()
    cache_key = "products:list:v1"
    cached = r.get(cache_key)
    if cached:
        return [ProductOut(**obj) for obj in json.loads(cached)]

    rows = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id).all()
    result = [ProductOut(id=p.id, sku=p.sku, name=p.name, price=float(p.price),
                         safety_stock=p.safety_stock, stock=inv.stock) for p, inv in rows]
    try:
        r.setex(cache_key, 30, json.dumps([x.dict() for x in result]))  # TTL 30s
    except Exception:
        pass
    return result

@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    row = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id).filter(Product.id == product_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    
    p, inv = row
    return ProductOut(id=p.id, sku=p.sku, name=p.name, price=float(p.price),
                     safety_stock=p.safety_stock, stock=inv.stock)

@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # 更新產品資訊
    if body.name is not None:
        product.name = body.name
    if body.price is not None:
        product.price = body.price
    if body.safety_stock is not None:
        product.safety_stock = body.safety_stock
    
    db.commit()
    db.refresh(product)
    
    # 取得庫存資訊
    inventory = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    
    # 失效快取
    try:
        r = get_redis()
        r.delete("products:list:v1")
        r.delete(f"product:{product_id}:v1")
    except Exception:
        pass
    
    return ProductOut(id=product.id, sku=product.sku, name=product.name, 
                     price=float(product.price), safety_stock=product.safety_stock, 
                     stock=inventory.stock)

@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # 檢查是否有訂單項目引用此產品
    from sqlalchemy import text
    order_items_count = db.execute(
        text("SELECT COUNT(*) FROM order_items WHERE product_id = :pid"),
        {"pid": product_id}
    ).scalar()
    
    if order_items_count > 0:
        raise HTTPException(
            status_code=409, 
            detail=f"Cannot delete product. It is referenced by {order_items_count} order item(s). Please delete related orders first."
        )
    
    # 刪除產品 (CASCADE 會自動刪除相關的 inventory 記錄)
    db.delete(product)
    db.commit()
    
    # 失效快取
    try:
        r = get_redis()
        r.delete("products:list:v1")
        r.delete(f"product:{product_id}:v1")
    except Exception:
        pass
    
    return {"message": "Product deleted successfully"}

