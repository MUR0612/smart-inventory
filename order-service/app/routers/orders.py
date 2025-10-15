from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, conint, EmailStr
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
from datetime import datetime
from ..db import SessionLocal
from ..models import Order, OrderItem
from ..services.order_workflow import OrderWorkflowService, OrderStatus
from ..services.inventory_client import inventory_client

router = APIRouter(prefix="/api/orders", tags=["orders"])

class OrderItemIn(BaseModel):
    product_id: int
    qty: conint(gt=0)

class OrderCreate(BaseModel):
    items: List[OrderItemIn]
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    shipping_address: Optional[str] = None
    notes: Optional[str] = None

class OrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[EmailStr] = None
    shipping_address: Optional[str] = None
    notes: Optional[str] = None

class OrderStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_sku: str
    qty: int
    unit_price: float
    subtotal: float

class OrderOut(BaseModel):
    id: int
    status: str
    total: float
    customer_name: Optional[str]
    customer_email: Optional[str]
    shipping_address: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime]
    shipped_at: Optional[datetime]
    items: List[OrderItemOut]

class OrderListOut(BaseModel):
    id: int
    status: str
    total: float
    customer_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    item_count: int

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=OrderOut)
async def create_order(body: OrderCreate, db: Session = Depends(get_db)):
    """建立新訂單"""
    if not body.items:
        raise HTTPException(400, "items cannot be empty")

    # 檢查庫存並預留
    product_info = {}
    total = 0.0
    
    try:
        # 檢查所有產品的庫存
        for item in body.items:
            stock_info = await inventory_client.check_stock(item.product_id, item.qty)
            product_info[item.product_id] = await inventory_client.get_product_info(item.product_id)
            total += product_info[item.product_id]["price"] * item.qty
        
        # 預留庫存
        for item in body.items:
            await inventory_client.reserve_stock(item.product_id, item.qty)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to process inventory: {str(e)}")

    # 建立訂單
    try:
        with db.begin():
            order = Order(
                status=OrderStatus.CREATED.value,
                total=total,
                customer_name=body.customer_name,
                customer_email=body.customer_email,
                shipping_address=body.shipping_address,
                notes=body.notes
            )
            db.add(order)
            db.flush()  # 取得 order.id

            # 建立訂單項目
            for item in body.items:
                product = product_info[item.product_id]
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    qty=item.qty,
                    unit_price=product["price"]
                )
                db.add(order_item)

        # 重新查詢完整的訂單資訊
        return await get_order(order.id, db)
        
    except Exception as e:
        # 如果訂單建立失敗，釋放已預留的庫存
        for item in body.items:
            try:
                await inventory_client.release_stock(item.product_id, item.qty)
            except:
                pass  # 記錄錯誤但不影響主要錯誤
        raise HTTPException(500, f"Failed to create order: {str(e)}")

@router.get("/", response_model=List[OrderListOut])
async def list_orders(
    skip: int = 0, 
    limit: int = 100, 
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """取得訂單列表"""
    query = db.query(Order)
    
    if status:
        query = query.filter(Order.status == status)
    
    orders = query.order_by(desc(Order.created_at)).offset(skip).limit(limit).all()
    
    result = []
    for order in orders:
        item_count = db.query(OrderItem).filter(OrderItem.order_id == order.id).count()
        result.append(OrderListOut(
            id=order.id,
            status=order.status,
            total=float(order.total),
            customer_name=order.customer_name,
            created_at=order.created_at,
            updated_at=order.updated_at,
            item_count=item_count
        ))
    
    return result

@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: Session = Depends(get_db)):
    """取得單一訂單詳情"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    # 取得訂單項目
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    
    # 取得產品資訊
    order_items = []
    for item in items:
        try:
            product_info = await inventory_client.get_product_info(item.product_id)
            order_items.append(OrderItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=product_info["name"],
                product_sku=product_info["sku"],
                qty=item.qty,
                unit_price=float(item.unit_price),
                subtotal=float(item.unit_price * item.qty)
            ))
        except:
            # 如果無法取得產品資訊，使用基本資訊
            order_items.append(OrderItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=f"Product {item.product_id}",
                product_sku="N/A",
                qty=item.qty,
                unit_price=float(item.unit_price),
                subtotal=float(item.unit_price * item.qty)
            ))
    
    return OrderOut(
        id=order.id,
        status=order.status,
        total=float(order.total),
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        shipping_address=order.shipping_address,
        notes=order.notes,
        created_at=order.created_at,
        updated_at=order.updated_at,
        paid_at=order.paid_at,
        shipped_at=order.shipped_at,
        items=order_items
    )

@router.put("/{order_id}", response_model=OrderOut)
async def update_order(order_id: int, body: OrderUpdate, db: Session = Depends(get_db)):
    """更新訂單資訊"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    if order.status not in [OrderStatus.CREATED.value]:
        raise HTTPException(400, f"Cannot update order in {order.status} status")
    
    # 更新欄位
    if body.customer_name is not None:
        order.customer_name = body.customer_name
    if body.customer_email is not None:
        order.customer_email = body.customer_email
    if body.shipping_address is not None:
        order.shipping_address = body.shipping_address
    if body.notes is not None:
        order.notes = body.notes
    
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    
    return await get_order(order_id, db)

@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(order_id: int, body: OrderStatusUpdate, db: Session = Depends(get_db)):
    """更新訂單狀態"""
    try:
        order = OrderWorkflowService.update_order_status(db, order_id, body.status, body.notes)
        return await get_order(order_id, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/{order_id}/workflow", response_model=dict)
async def get_order_workflow(order_id: int, db: Session = Depends(get_db)):
    """取得訂單工作流程資訊"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    return OrderWorkflowService.get_order_workflow_info(order)

@router.delete("/{order_id}")
async def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """取消訂單（釋放庫存）"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    if order.status not in [OrderStatus.CREATED.value, OrderStatus.PAID.value]:
        raise HTTPException(400, f"Cannot cancel order in {order.status} status")
    
    try:
        # 釋放庫存
        items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        for item in items:
            await inventory_client.release_stock(item.product_id, item.qty)
        
        # 更新訂單狀態
        OrderWorkflowService.update_order_status(
            db, order_id, OrderStatus.CANCELLED.value, 
            "Order cancelled by user"
        )
        
        return {"message": "Order cancelled successfully"}
        
    except Exception as e:
        raise HTTPException(500, f"Failed to cancel order: {str(e)}")

@router.delete("/{order_id}/delete")
async def delete_order(order_id: int, db: Session = Depends(get_db)):
    """刪除訂單"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    # 檢查訂單狀態，只有特定狀態的訂單才能被刪除
    if order.status in ["SHIPPED"]:
        raise HTTPException(400, f"Cannot delete order in {order.status} status")
    
    # 刪除訂單項目
    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete()
    
    # 刪除訂單
    db.delete(order)
    db.commit()
    
    return {"message": "Order deleted successfully"}

