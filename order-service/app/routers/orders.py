from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from smart_shared.auth import READ_ROLES, WRITE_ROLES, Principal, authorize
from ..db import as_utc, get_db
from ..models import Order, OrderItem
from ..services import order_workflow as wf
from ..services.inventory_client import InventoryClient, get_inventory_client
from ..services.redis_subscriber import redis_subscriber

router = APIRouter(prefix="/api/orders", tags=["orders"])

can_read = authorize(*READ_ROLES)
can_write = authorize(*WRITE_ROLES)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrderItemIn(StrictModel):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=10_000)


class OrderCreate(StrictModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: EmailStr | None = Field(default=None, max_length=255)
    shipping_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class OrderUpdate(StrictModel):
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: EmailStr | None = Field(default=None, max_length=255)
    shipping_address: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class OrderStatusUpdate(StrictModel):
    status: Literal["PAID", "SHIPPED", "CANCELLED", "REFUNDED"]
    notes: str | None = Field(default=None, max_length=500)


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_sku: str
    qty: int
    unit_price: Decimal
    subtotal: Decimal


class OrderOut(BaseModel):
    id: int
    status: str
    total: Decimal
    customer_name: str | None
    customer_email: str | None
    shipping_address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    inventory_sync: str
    sync_error: str | None
    valid_transitions: list[str]
    items: list[OrderItemOut]


class OrderListItem(BaseModel):
    id: int
    status: str
    total: Decimal
    customer_name: str | None
    created_at: datetime
    updated_at: datetime
    item_count: int
    inventory_sync: str


class CustomerTotal(BaseModel):
    customer_name: str
    orders: int
    total: Decimal


class OrderStats(BaseModel):
    scope: str
    total_orders: int
    by_status: dict[str, int]
    revenue: Decimal
    revenue_orders: int
    average_order_value: Decimal
    top_customers: list[CustomerTotal]
    pending_inventory_sync: int


class OrderPage(BaseModel):
    items: list[OrderListItem]
    total: int
    skip: int
    limit: int


def _raise(exc: wf.OrderError):
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def order_out(db: Session, order_id: int) -> OrderOut:
    db.expire_all()
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    items = db.query(OrderItem).filter_by(order_id=order_id).order_by(OrderItem.id).all()
    return OrderOut(
        id=order.id, status=order.status, total=order.total, customer_name=order.customer_name,
        customer_email=order.customer_email, shipping_address=order.shipping_address, notes=order.notes,
        created_at=as_utc(order.created_at), updated_at=as_utc(order.updated_at),
        paid_at=as_utc(order.paid_at), shipped_at=as_utc(order.shipped_at),
        inventory_sync=order.inventory_sync, sync_error=order.sync_error,
        valid_transitions=wf.valid_transitions(order.status),
        items=[OrderItemOut(id=i.id, product_id=i.product_id,
                            # Legacy rows (before the snapshot columns existed) have no name.
                            product_name=i.product_name or f"Product {i.product_id}",
                            product_sku=i.product_sku or "N/A", qty=i.qty, unit_price=i.unit_price,
                            subtotal=i.unit_price * i.qty) for i in items])


IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9-]{8,64}$")]


@router.post("", response_model=OrderOut, status_code=201)
@router.post("/", response_model=OrderOut, status_code=201, include_in_schema=False)
async def create_order(body: OrderCreate, response: Response, idempotency_key: IdempotencyKey = None,
                       db: Session = Depends(get_db), client: InventoryClient = Depends(get_inventory_client),
                       principal: Principal = Depends(can_write)):
    """Create an order and reserve its stock. Send an ``Idempotency-Key`` header to make retries safe."""
    try:
        result = await wf.create_order(db, client, body, idempotency_key, principal.subject)
    except wf.OrderError as exc:
        _raise(exc)
    # Built after the reservation is final: a failure here never releases stock.
    if result.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    response.headers["Location"] = f"/api/orders/{result.order_id}"
    return order_out(db, result.order_id)


@router.get("", response_model=OrderPage, dependencies=[Depends(can_read)])
@router.get("/", response_model=OrderPage, dependencies=[Depends(can_read)], include_in_schema=False)
def list_orders(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                status: wf.OrderStatus | None = None, db: Session = Depends(get_db)):
    """Paginated list; ``total`` is the full count so clients never infer it from one page."""
    filters = [Order.status == status.value] if status else []
    total = db.execute(select(func.count(Order.id)).where(*filters)).scalar_one()
    counts = select(OrderItem.order_id, func.count(OrderItem.id).label("n")).group_by(OrderItem.order_id).subquery()
    rows = db.execute(
        select(Order, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.order_id == Order.id)
        .where(*filters).order_by(Order.created_at.desc(), Order.id.desc()).offset(skip).limit(limit)
    ).all()
    return OrderPage(total=total, skip=skip, limit=limit, items=[
        OrderListItem(id=o.id, status=o.status, total=o.total, customer_name=o.customer_name,
                      created_at=as_utc(o.created_at), updated_at=as_utc(o.updated_at), item_count=n,
                      inventory_sync=o.inventory_sync) for o, n in rows])


@router.get("/stats", response_model=OrderStats, dependencies=[Depends(can_read)])
def order_stats(db: Session = Depends(get_db)):
    """Report numbers over ALL orders, computed in SQL with DECIMAL arithmetic.

    revenue = totals of PAID and SHIPPED orders (refunded/cancelled/failed excluded).
    """
    by_status = dict(db.execute(select(Order.status, func.count(Order.id)).group_by(Order.status)).all())
    earning = Order.status.in_([wf.S.PAID.value, wf.S.SHIPPED.value])
    revenue, revenue_orders = db.execute(
        select(func.coalesce(func.sum(case((earning, Order.total), else_=0)), 0),
               func.coalesce(func.sum(case((earning, 1), else_=0)), 0))).one()
    revenue = Decimal(revenue).quantize(Decimal("0.01"))
    top = db.execute(
        select(Order.customer_name, func.count(Order.id), func.sum(Order.total))
        .where(earning, Order.customer_name.is_not(None))
        .group_by(Order.customer_name).order_by(func.sum(Order.total).desc()).limit(5)).all()
    pending_sync = db.execute(select(func.count(Order.id)).where(Order.inventory_sync.in_(wf.PENDING_SYNC))).scalar_one()
    return {
        "scope": "all orders",
        "total_orders": sum(by_status.values()),
        "by_status": by_status,
        "revenue": revenue,
        "revenue_orders": int(revenue_orders),
        "average_order_value": (revenue / revenue_orders).quantize(Decimal("0.01")) if revenue_orders else Decimal("0.00"),
        "top_customers": [{"customer_name": n, "orders": c, "total": Decimal(t).quantize(Decimal("0.01"))}
                          for n, c, t in top],
        "pending_inventory_sync": pending_sync,
    }


@router.get("/events/recent", dependencies=[Depends(can_read)])
def recent_events():
    """Last events seen by this replica's Redis subscriber (demo visibility only)."""
    return {"connected": redis_subscriber.connected, "events": list(redis_subscriber.recent)}


@router.post("/admin/reconcile", dependencies=[Depends(can_write)])
async def reconcile(db: Session = Depends(get_db), client: InventoryClient = Depends(get_inventory_client)):
    """Retry pending inventory side effects now (the background loop also does this)."""
    return await wf.reconcile_once(db, client)


@router.get("/{order_id}", response_model=OrderOut, dependencies=[Depends(can_read)])
def get_order(order_id: int, db: Session = Depends(get_db)):
    return order_out(db, order_id)


@router.put("/{order_id}", response_model=OrderOut, dependencies=[Depends(can_write)])
def update_order(order_id: int, body: OrderUpdate, db: Session = Depends(get_db)):
    order = db.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != wf.S.CREATED.value:
        db.rollback()
        raise HTTPException(409, f"Cannot edit an order in {order.status} status")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(order, field, value)
    db.commit()
    return order_out(db, order_id)


async def _change_status(db: Session, client: InventoryClient, order_id: int, target: str, note: str | None,
                         actor: str) -> OrderOut:
    """The single entry point for every status change (PATCH /status and POST /cancel)."""
    try:
        action = wf.begin_transition(db, order_id, target, note, actor)
    except wf.OrderError as exc:
        _raise(exc)
    if action:
        # If inventory is unreachable the order shows inventory_sync=*_PENDING and
        # the reconcile loop finishes it; the status change itself is final.
        await wf.sync_inventory(db, order_id, client)
    return order_out(db, order_id)


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(order_id: int, body: OrderStatusUpdate, db: Session = Depends(get_db),
                              client: InventoryClient = Depends(get_inventory_client),
                              principal: Principal = Depends(can_write)):
    return await _change_status(db, client, order_id, body.status, body.notes, principal.subject)


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: int, db: Session = Depends(get_db),
                       client: InventoryClient = Depends(get_inventory_client),
                       principal: Principal = Depends(can_write)):
    """Cancel an unpaid order (same rules and side effects as PATCH status=CANCELLED)."""
    return await _change_status(db, client, order_id, wf.S.CANCELLED.value, "cancelled", principal.subject)


@router.get("/{order_id}/workflow", dependencies=[Depends(can_read)])
def get_order_workflow(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return {
        "id": order.id,
        "current_status": order.status,
        "valid_transitions": wf.valid_transitions(order.status),
        "inventory_sync": order.inventory_sync,
        "timeline": {k: (as_utc(getattr(order, k)).isoformat() if getattr(order, k) else None)
                     for k in ("created_at", "paid_at", "shipped_at", "updated_at")},
    }


@router.delete("/{order_id}", dependencies=[Depends(can_write)])
def delete_order(order_id: int, db: Session = Depends(get_db)):
    """Only closed orders without pending stock work can be deleted (no orphaned reservations)."""
    order = db.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in wf.DELETABLE or order.inventory_sync in wf.PENDING_SYNC:
        db.rollback()
        raise HTTPException(409, f"Only {', '.join(wf.DELETABLE)} orders without pending stock work can be "
                                 f"deleted; cancel or refund first")
    db.query(OrderItem).filter_by(order_id=order_id).delete()
    db.delete(order)
    db.commit()
    return {"message": "Order deleted"}
