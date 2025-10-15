from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session
import pytz
from ..models import Order

def get_aest_time():
    """Get current time in AEST timezone"""
    aest = pytz.timezone('Australia/Sydney')
    return datetime.now(aest)

class OrderStatus(str, Enum):
    CREATED = "CREATED"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

class OrderWorkflowService:
    """訂單工作流程服務"""
    
    # 定義狀態轉換規則
    VALID_TRANSITIONS = {
        OrderStatus.CREATED: [OrderStatus.PAID, OrderStatus.CANCELLED],
        OrderStatus.PAID: [OrderStatus.SHIPPED, OrderStatus.REFUNDED],
        OrderStatus.SHIPPED: [OrderStatus.REFUNDED],
        OrderStatus.CANCELLED: [],  # 取消後不能轉換到其他狀態
        OrderStatus.REFUNDED: []    # 退款後不能轉換到其他狀態
    }
    
    @classmethod
    def can_transition(cls, current_status: str, target_status: str) -> bool:
        """檢查是否可以從當前狀態轉換到目標狀態"""
        current = OrderStatus(current_status)
        target = OrderStatus(target_status)
        return target in cls.VALID_TRANSITIONS.get(current, [])
    
    @classmethod
    def get_valid_transitions(cls, current_status: str) -> list[str]:
        """取得當前狀態可以轉換到的所有狀態"""
        current = OrderStatus(current_status)
        return [status.value for status in cls.VALID_TRANSITIONS.get(current, [])]
    
    @classmethod
    def update_order_status(cls, db: Session, order_id: int, new_status: str, 
                          notes: Optional[str] = None) -> Order:
        """更新訂單狀態"""
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        if not cls.can_transition(order.status, new_status):
            valid_transitions = cls.get_valid_transitions(order.status)
            raise ValueError(f"Cannot transition from {order.status} to {new_status}. "
                           f"Valid transitions: {valid_transitions}")
        
        # 更新狀態
        old_status = order.status
        order.status = new_status
        order.updated_at = get_aest_time()
        
        # 根據狀態設定相應的時間戳
        if new_status == OrderStatus.PAID.value:
            order.paid_at = get_aest_time()
        elif new_status == OrderStatus.SHIPPED.value:
            order.shipped_at = get_aest_time()
        
        # 更新備註
        if notes:
            if order.notes:
                order.notes += f"\n[{get_aest_time().isoformat()}] {notes}"
            else:
                order.notes = f"[{get_aest_time().isoformat()}] {notes}"
        
        db.commit()
        db.refresh(order)
        
        return order
    
    @classmethod
    def get_order_workflow_info(cls, order: Order) -> dict:
        """取得訂單工作流程資訊"""
        return {
            "id": order.id,
            "status": order.status,
            "current_status": order.status,
            "valid_transitions": cls.get_valid_transitions(order.status),
            "timeline": {
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None
            },
            "notes": order.notes
        }


