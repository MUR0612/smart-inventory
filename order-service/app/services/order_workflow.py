"""Order state machine and the cross-service stock bookkeeping.

There is no transaction spanning MySQL and an HTTP call, so every inventory
side effect is recorded first and executed second:

1. Change the order row (status + ``inventory_sync = *_PENDING``) and commit.
2. Call inventory-service. Reserve/release/commit are idempotent per
   ``reservation_id``, so they can be retried safely.
3. Mark the step done with a compare-and-set on ``inventory_sync``.

If step 2 or 3 fails the order stays ``*_PENDING`` with ``sync_error`` set,
and ``reconcile_once`` (background loop + admin endpoint) finishes it later.

Business rules:
* CREATED -> CANCELLED : cancel before payment, stock returns.
* PAID    -> REFUNDED  : refund before shipment, goods never left, stock returns.
* PAID    -> SHIPPED   : reservation is committed and can no longer be released.
* SHIPPED -> REFUNDED  : money back only. Returned goods are inspected and
                         restocked manually (stock adjust); no automatic restock.
* PAID    -> CANCELLED is not allowed: a paid order must be refunded.
"""
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smart_shared.observability import log_fields
from ..db import as_utc, utcnow
from ..models import Order, OrderItem
from .inventory_client import InventoryClient, InventoryError, InventoryRejected, InventoryUnavailable

logger = logging.getLogger("order-service.workflow")


class OrderStatus(str, Enum):
    PENDING = "PENDING"      # stock reservation in progress
    CREATED = "CREATED"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"        # never became a valid order; any reservation released


class InventorySync(str, Enum):
    NONE = "NONE"
    RESERVE_PENDING = "RESERVE_PENDING"
    RESERVED = "RESERVED"
    RELEASE_PENDING = "RELEASE_PENDING"
    RELEASED = "RELEASED"
    COMMIT_PENDING = "COMMIT_PENDING"
    COMMITTED = "COMMITTED"


S, I = OrderStatus, InventorySync
RELEASE, COMMIT = "release", "commit"

# target status -> inventory side effect (None = no stock change)
TRANSITIONS: dict[OrderStatus, dict[OrderStatus, str | None]] = {
    S.CREATED: {S.PAID: None, S.CANCELLED: RELEASE},
    S.PAID: {S.SHIPPED: COMMIT, S.REFUNDED: RELEASE},
    S.SHIPPED: {S.REFUNDED: None},
}
USER_TARGETS = (S.PAID, S.SHIPPED, S.CANCELLED, S.REFUNDED)
PENDING_SYNC = (I.RESERVE_PENDING.value, I.RELEASE_PENDING.value, I.COMMIT_PENDING.value)
DELETABLE = (S.CANCELLED.value, S.REFUNDED.value, S.FAILED.value)


class OrderError(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def valid_transitions(status: str) -> list[str]:
    try:
        return [t.value for t in TRANSITIONS.get(OrderStatus(status), {})]
    except ValueError:
        return []


def _cas(db: Session, order_id: int, expected_sync: str, **values) -> bool:
    """Update the order only if inventory_sync is still what we expect."""
    result = db.execute(update(Order).where(Order.id == order_id, Order.inventory_sync == expected_sync)
                        .values(updated_at=utcnow(), **values))
    db.commit()
    return result.rowcount == 1


def _record_sync_failure(db: Session, order_id: int, expected_sync: str, reason: str):
    _cas(db, order_id, expected_sync, sync_error=reason[:255], sync_attempts=Order.sync_attempts + 1)
    logger.warning("inventory sync pending", extra=log_fields(order_id=order_id, state=expected_sync, reason=reason))


def _append_note(order: Order, note: str):
    line = f"[{as_utc(utcnow()).isoformat()}] {note}"
    order.notes = f"{order.notes}\n{line}" if order.notes else line


# ---------------------------------------------------------------- status changes

def begin_transition(db: Session, order_id: int, target: str, note: str | None, actor: str) -> str | None:
    """Validate and persist a status change (step 1). Returns the side effect to run."""
    order = db.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if order is None:
        db.rollback()
        raise OrderError(404, "Order not found")
    try:
        allowed = TRANSITIONS.get(OrderStatus(order.status), {})
        target_status = OrderStatus(target)
    except ValueError:
        allowed, target_status = {}, None
    if target_status not in allowed:
        current, valid = order.status, valid_transitions(order.status)
        db.rollback()
        hint = " Paid orders must be refunded instead." if current == S.PAID and target == S.CANCELLED else ""
        raise OrderError(409, f"Cannot change status from {current} to {target}. Valid: {valid}.{hint}")

    action = allowed[target_status]
    now = utcnow()
    order.status = target_status.value
    order.updated_at = now
    if target_status == S.PAID:
        order.paid_at = now
    elif target_status == S.SHIPPED:
        order.shipped_at = now
    if action and not order.reservation_id:
        # Should not happen after migration (legacy orders get reservations); never guess stock.
        order.sync_error = "No reservation recorded; adjust stock manually"
        logger.error("order without reservation", extra=log_fields(order_id=order_id))
        action = None
    elif action == RELEASE:
        order.inventory_sync = I.RELEASE_PENDING.value
    elif action == COMMIT:
        order.inventory_sync = I.COMMIT_PENDING.value
    _append_note(order, f"{actor}: status -> {target_status.value}" + (f" ({note})" if note else ""))
    db.commit()
    return action


async def sync_inventory(db: Session, order_id: int, client: InventoryClient) -> bool:
    """Run (or retry) the pending inventory side effect of one order (steps 2 and 3)."""
    db.expire_all()
    order = db.get(Order, order_id)
    if order is None or order.inventory_sync not in PENDING_SYNC:
        return True
    state, rid = order.inventory_sync, order.reservation_id
    try:
        if state == I.COMMIT_PENDING:
            await client.commit(rid)
            values = {"inventory_sync": I.COMMITTED.value}
        else:
            # RELEASE_PENDING, or RESERVE_PENDING abandoned by its request -> give stock back.
            await client.release(rid)
            values = {"inventory_sync": I.RELEASED.value}
            if state == I.RESERVE_PENDING:
                values["status"] = S.FAILED.value
    except InventoryRejected as exc:
        _record_sync_failure(db, order_id, state, f"inventory rejected ({exc.status_code}); needs review")
        return False
    except InventoryUnavailable:
        _record_sync_failure(db, order_id, state, "inventory unavailable; will retry")
        return False
    return _cas(db, order_id, state, sync_error=None, **values)


async def reconcile_once(db: Session, client: InventoryClient, reserve_grace_seconds: int = 60) -> dict:
    """Retry pending side effects. Safe to run concurrently on several replicas."""
    cutoff = utcnow() - timedelta(seconds=reserve_grace_seconds)
    ids = db.execute(
        select(Order.id).where(or_(
            Order.inventory_sync.in_([I.RELEASE_PENDING.value, I.COMMIT_PENDING.value]),
            (Order.inventory_sync == I.RESERVE_PENDING.value) & (Order.created_at < cutoff),
        )).order_by(Order.id).limit(50)
    ).scalars().all()
    done = 0
    for order_id in ids:
        if await sync_inventory(db, order_id, client):
            done += 1
    if ids:
        logger.info("reconcile finished", extra=log_fields(checked=len(ids), completed=done))
    return {"checked": len(ids), "completed": done, "still_pending": len(ids) - done}


# ---------------------------------------------------------------- order creation

@dataclass
class CreateResult:
    order_id: int
    replayed: bool


def merge_items(items) -> dict[int, int]:
    merged: dict[int, int] = {}
    for item in items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.qty
    if any(qty > 10_000 for qty in merged.values()):
        raise OrderError(422, "Quantity per product must not exceed 10000")
    return merged


def fingerprint(merged: dict[int, int], body) -> str:
    canonical = {"items": sorted(merged.items()), "customer_name": body.customer_name,
                 "customer_email": body.customer_email, "shipping_address": body.shipping_address,
                 "notes": body.notes}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode()).hexdigest()


async def create_order(db: Session, client: InventoryClient, body, idempotency_key: str | None,
                       actor: str) -> CreateResult:
    merged = merge_items(body.items)
    request_hash = fingerprint(merged, body)
    if idempotency_key:
        existing = db.query(Order).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing:
            return await _resume(db, client, existing, request_hash)

    products = {}
    for product_id in merged:
        try:
            products[product_id] = await client.get_product(product_id)
        except InventoryRejected as exc:
            raise OrderError(404 if exc.status_code == 404 else 409,
                             f"Product {product_id} not found" if exc.status_code == 404 else exc.detail)
        except InventoryUnavailable:
            raise OrderError(503, "Inventory service unavailable; order not created")
    total = sum((Decimal(str(products[pid]["price"])) * qty for pid, qty in merged.items()), Decimal("0"))

    # Record the intent before touching stock, so every reservation has an owner.
    order = Order(status=S.PENDING.value, inventory_sync=I.RESERVE_PENDING.value, reservation_id=uuid.uuid4().hex,
                  idempotency_key=idempotency_key, request_hash=request_hash, total=total.quantize(Decimal("0.01")),
                  customer_name=body.customer_name, customer_email=body.customer_email,
                  shipping_address=body.shipping_address, notes=body.notes)
    try:
        db.add(order)
        db.flush()
        db.add_all(OrderItem(order_id=order.id, product_id=pid, qty=qty,
                             unit_price=Decimal(str(products[pid]["price"])),
                             product_name=products[pid]["name"], product_sku=products[pid]["sku"])
                   for pid, qty in merged.items())
        _append_note(order, f"{actor}: order created")
        db.commit()
    except IntegrityError:
        db.rollback()  # same Idempotency-Key raced us
        existing = db.query(Order).filter_by(idempotency_key=idempotency_key).one_or_none() if idempotency_key else None
        if existing is None:
            raise
        return await _resume(db, client, existing, request_hash)
    return await _reserve(db, client, order.id, order.reservation_id, merged)


async def _reserve(db: Session, client: InventoryClient, order_id: int, reservation_id: str,
                   merged: dict[int, int]) -> CreateResult:
    items = [{"product_id": pid, "qty": qty} for pid, qty in sorted(merged.items())]
    try:
        await client.reserve(reservation_id, items)
    except InventoryRejected as exc:
        # Definite rejection: inventory applied nothing, so the draft order is removed.
        _discard_draft(db, order_id)
        detail = exc.detail or "Inventory rejected the reservation"
        raise OrderError(exc.status_code if exc.status_code in (404, 409, 422) else 409, detail)
    except InventoryUnavailable:
        # Outcome unknown (maybe applied, response lost). Release is idempotent and
        # leaves a tombstone, so a late-arriving reserve cannot deduct afterwards.
        try:
            await client.release(reservation_id)
            _cas(db, order_id, I.RESERVE_PENDING.value, status=S.FAILED.value,
                 inventory_sync=I.RELEASED.value, sync_error="reservation outcome unknown; released")
        except InventoryError:
            _record_sync_failure(db, order_id, I.RESERVE_PENDING.value, "reserve outcome unknown; release pending")
        raise OrderError(503, {"message": "Inventory service unavailable; order not created", "order_id": order_id})

    if not _cas(db, order_id, I.RESERVE_PENDING.value, status=S.CREATED.value, inventory_sync=I.RESERVED.value):
        db.expire_all()
        current = db.get(Order, order_id)
        if current is not None and current.status == S.CREATED:
            # A concurrent retry with the same Idempotency-Key finished it first.
            return CreateResult(order_id, replayed=True)
        raise OrderError(409, {"message": "Order was abandoned and released by recovery; please retry",
                               "order_id": order_id})
    return CreateResult(order_id, replayed=False)


def _discard_draft(db: Session, order_id: int):
    still_draft = db.execute(select(Order.id).where(Order.id == order_id,
                                                    Order.inventory_sync == I.RESERVE_PENDING.value)
                             .with_for_update()).scalar_one_or_none()
    if still_draft:
        db.execute(delete(OrderItem).where(OrderItem.order_id == order_id))
        db.execute(delete(Order).where(Order.id == order_id))
    db.commit()


async def _resume(db: Session, client: InventoryClient, order: Order, request_hash: str) -> CreateResult:
    if order.request_hash and order.request_hash != request_hash:
        raise OrderError(422, "Idempotency-Key was already used for a different request")
    if order.status == S.PENDING and order.inventory_sync == I.RESERVE_PENDING:
        items = db.query(OrderItem).filter_by(order_id=order.id).all()
        return await _reserve(db, client, order.id, order.reservation_id, {i.product_id: i.qty for i in items})
    if order.status == S.FAILED:
        raise OrderError(409, {"message": "The earlier attempt with this Idempotency-Key failed; use a new key",
                               "order_id": order.id})
    return CreateResult(order.id, replayed=True)
