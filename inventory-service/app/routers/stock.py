from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Product, Inventory
from ..cache import get_redis
from ..services.redis_pubsub import redis_pubsub
import json

router = APIRouter(prefix="/api/inventory", tags=["stock"])

class StockAdjustment(BaseModel):
    adjustment: int  # 正數為增加，負數為減少

class StockInfo(BaseModel):
    product_id: int
    sku: str
    name: str
    current_stock: int
    safety_stock: int
    is_low_stock: bool

class LowStockAlert(BaseModel):
    product_id: int
    sku: str
    name: str
    current_stock: int
    safety_stock: int

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/stock/{product_id}/adjust", response_model=StockInfo)
def adjust_stock(product_id: int, body: StockAdjustment, db: Session = Depends(get_db)):
    """調整產品庫存"""
    # 檢查產品是否存在
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # 更新庫存
    inventory = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory record not found")
    
    new_stock = inventory.stock + body.adjustment
    if new_stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    
    inventory.stock = new_stock
    db.commit()
    db.refresh(inventory)
    
    # 檢查是否低庫存並發送警告
    is_low_stock = new_stock <= product.safety_stock
    if is_low_stock:
        try:
            alert = LowStockAlert(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                current_stock=new_stock,
                safety_stock=product.safety_stock
            )
            redis_pubsub.publish_low_stock_alert(alert.dict())
        except Exception:
            pass
    
    # 發布庫存變更通知
    try:
        change_data = {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "old_stock": inventory.stock - body.adjustment,
            "new_stock": new_stock,
            "adjustment": body.adjustment,
            "is_low_stock": is_low_stock,
            "timestamp": inventory.updated_at.isoformat() if inventory.updated_at else None
        }
        redis_pubsub.publish_stock_change(change_data)
    except Exception:
        pass
    
    # 失效快取
    try:
        r = get_redis()
        r.delete("products:list:v1")
        r.delete(f"product:{product_id}:v1")
    except Exception:
        pass
    
    return StockInfo(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        current_stock=inventory.stock,
        safety_stock=product.safety_stock,
        is_low_stock=is_low_stock
    )

@router.get("/stock/{product_id}", response_model=StockInfo)
def get_stock(product_id: int, db: Session = Depends(get_db)):
    """取得產品庫存資訊"""
    inventory = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product = db.query(Product).filter(Product.id == product_id).first()
    is_low_stock = inventory.stock <= product.safety_stock
    
    return StockInfo(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        current_stock=inventory.stock,
        safety_stock=product.safety_stock,
        is_low_stock=is_low_stock
    )

@router.get("/stock", response_model=list[StockInfo])
def list_all_stock(db: Session = Depends(get_db)):
    """取得所有產品庫存資訊"""
    rows = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id).all()
    
    result = []
    for p, inv in rows:
        is_low_stock = inv.stock <= p.safety_stock
        result.append(StockInfo(
            product_id=p.id,
            sku=p.sku,
            name=p.name,
            current_stock=inv.stock,
            safety_stock=p.safety_stock,
            is_low_stock=is_low_stock
        ))
    
    return result

@router.get("/low-stock", response_model=list[LowStockAlert])
def get_low_stock_products(db: Session = Depends(get_db)):
    """取得低庫存產品清單"""
    rows = db.query(Product, Inventory).join(Inventory, Product.id == Inventory.product_id).filter(
        Inventory.stock <= Product.safety_stock
    ).all()
    
    alerts = []
    for p, inv in rows:
        alerts.append(LowStockAlert(
            product_id=p.id,
            sku=p.sku,
            name=p.name,
            current_stock=inv.stock,
            safety_stock=p.safety_stock
        ))
    
    return alerts

@router.post("/stock/{product_id}/set")
def set_stock(product_id: int, stock: int, db: Session = Depends(get_db)):
    """直接設定產品庫存數量"""
    if stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    
    inventory = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Product not found")
    
    inventory.stock = stock
    db.commit()
    
    # 檢查是否低庫存
    product = db.query(Product).filter(Product.id == product_id).first()
    if stock <= product.safety_stock:
        try:
            r = get_redis()
            alert = LowStockAlert(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                current_stock=stock,
                safety_stock=product.safety_stock
            )
            r.publish("low_stock_alerts", json.dumps(alert.dict()))
        except Exception:
            pass
    
    # 失效快取
    try:
        r = get_redis()
        r.delete("products:list:v1")
        r.delete(f"product:{product_id}:v1")
    except Exception:
        pass
    
    return {"message": f"Stock set to {stock} successfully"}