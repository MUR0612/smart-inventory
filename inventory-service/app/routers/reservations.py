"""Idempotent stock reservations used by order-service (service token only).

* reserve  : all items in ONE transaction -> all-or-nothing, no partial deduction.
             Re-sending the same reservation_id returns the stored result and
             never deducts twice.
* release  : returns stock exactly once. Releasing an unknown id stores a
             RELEASED tombstone, so a reserve request that arrives late (e.g.
             after a client timeout) can no longer deduct stock.
* commit   : goods shipped; the reservation can no longer be released.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smart_shared.auth import authorize
from .. import cache, events
from ..db import get_db, utcnow
from ..models import Inventory, Product, StockReservation, StockReservationItem
from ..schemas import ReservationCreate, ReservationItem, ReservationOut

router = APIRouter(prefix="/api/inventory/reservations", tags=["reservations"])
service_only = authorize(allow_service=True)

RESERVED, RELEASED, COMMITTED = "RESERVED", "RELEASED", "COMMITTED"
ReservationId = Path(pattern=r"^[A-Za-z0-9-]{8,64}$")


def _items(db: Session, rid: str) -> list[ReservationItem]:
    rows = db.query(StockReservationItem).filter_by(reservation_id=rid).order_by(StockReservationItem.product_id).all()
    return [ReservationItem(product_id=r.product_id, qty=r.qty) for r in rows]


def _lock_inventory(db: Session, product_ids) -> dict[int, Inventory]:
    # Fixed lock order (by product_id) prevents deadlocks between reservations.
    rows = db.execute(select(Inventory).where(Inventory.product_id.in_(list(product_ids)))
                      .order_by(Inventory.product_id).with_for_update()).scalars().all()
    return {r.product_id: r for r in rows}


def _publish(db: Session, changes: list[tuple[int, int, int]], source: str, rid: str):
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([c[0] for c in changes]))}
    for product_id, old, new in changes:
        events.stock_changed(products[product_id], old, new, source=source, reference=rid)
    cache.invalidate_products()


def _replay(db: Session, existing: StockReservation, body: ReservationCreate, response: Response) -> ReservationOut:
    if existing.status == RELEASED:
        raise HTTPException(status_code=409, detail="Reservation already released")
    stored = _items(db, existing.id)
    if {i.product_id: i.qty for i in stored} != {i.product_id: i.qty for i in body.items}:
        raise HTTPException(status_code=409, detail="reservation_id was already used with different items")
    response.status_code = 200
    return ReservationOut(reservation_id=existing.id, status=existing.status, items=stored, replayed=True)


def _reserve_new(db: Session, body: ReservationCreate) -> ReservationOut:
    wanted = {i.product_id: i.qty for i in body.items}
    inventory = _lock_inventory(db, wanted)
    missing = sorted(set(wanted) - set(inventory))
    if missing:
        db.rollback()
        raise HTTPException(status_code=404, detail={"message": "Unknown product", "product_ids": missing})
    short = [{"product_id": pid, "requested": qty, "available": inventory[pid].stock}
             for pid, qty in wanted.items() if inventory[pid].stock < qty]
    if short:
        db.rollback()
        raise HTTPException(status_code=409, detail={"message": "Insufficient stock", "items": short})

    changes = []
    for pid, qty in sorted(wanted.items()):
        inv = inventory[pid]
        changes.append((pid, inv.stock, inv.stock - qty))
        inv.stock -= qty
        inv.updated_at = utcnow()
    db.add(StockReservation(id=body.reservation_id, status=RESERVED))
    db.flush()  # duplicate reservation_id from a concurrent request fails here
    db.add_all(StockReservationItem(reservation_id=body.reservation_id, product_id=pid, qty=qty)
               for pid, qty in wanted.items())
    db.commit()
    _publish(db, changes, "reservation", body.reservation_id)
    return ReservationOut(reservation_id=body.reservation_id, status=RESERVED,
                          items=sorted(body.items, key=lambda i: i.product_id))


@router.post("", response_model=ReservationOut, status_code=201, dependencies=[Depends(service_only)])
def reserve(body: ReservationCreate, response: Response, db: Session = Depends(get_db)):
    for _ in range(2):
        existing = db.get(StockReservation, body.reservation_id)
        if existing:
            return _replay(db, existing, body, response)
        try:
            return _reserve_new(db, body)
        except IntegrityError:
            # A concurrent request with the same id committed first; our
            # deductions were rolled back. Loop once to return its result.
            db.rollback()
            db.expire_all()
    raise HTTPException(status_code=409, detail="Concurrent reservation conflict; retry")


@router.get("/{reservation_id}", response_model=ReservationOut, dependencies=[Depends(service_only)])
def get_reservation(reservation_id: str = ReservationId, db: Session = Depends(get_db)):
    res = db.get(StockReservation, reservation_id)
    if not res:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return ReservationOut(reservation_id=res.id, status=res.status, items=_items(db, res.id))


@router.post("/{reservation_id}/release", dependencies=[Depends(service_only)])
def release(reservation_id: str = ReservationId, db: Session = Depends(get_db)):
    if db.get(StockReservation, reservation_id) is None:
        try:
            db.add(StockReservation(id=reservation_id, status=RELEASED))
            db.commit()
            return {"reservation_id": reservation_id, "status": RELEASED, "released_now": False}
        except IntegrityError:
            db.rollback()  # the reservation appeared concurrently; release it below
            db.expire_all()

    res = db.execute(select(StockReservation).where(StockReservation.id == reservation_id)
                     .with_for_update()).scalar_one()
    if res.status == RELEASED:
        db.rollback()
        return {"reservation_id": reservation_id, "status": RELEASED, "released_now": False}
    if res.status == COMMITTED:
        db.rollback()
        raise HTTPException(status_code=409, detail="Reservation already committed (goods shipped)")

    items = _items(db, reservation_id)
    inventory = _lock_inventory(db, [i.product_id for i in items])
    changes = []
    for item in items:
        inv = inventory[item.product_id]
        changes.append((item.product_id, inv.stock, inv.stock + item.qty))
        inv.stock += item.qty
        inv.updated_at = utcnow()
    res.status = RELEASED
    res.updated_at = utcnow()
    db.commit()
    if changes:
        _publish(db, changes, "release", reservation_id)
    return {"reservation_id": reservation_id, "status": RELEASED, "released_now": True}


@router.post("/{reservation_id}/commit", dependencies=[Depends(service_only)])
def commit(reservation_id: str = ReservationId, db: Session = Depends(get_db)):
    res = db.execute(select(StockReservation).where(StockReservation.id == reservation_id)
                     .with_for_update()).scalar_one_or_none()
    if res is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Reservation not found")
    if res.status == RELEASED:
        db.rollback()
        raise HTTPException(status_code=409, detail="Reservation already released")
    if res.status == RESERVED:
        res.status = COMMITTED
        res.updated_at = utcnow()
    db.commit()
    return {"reservation_id": reservation_id, "status": COMMITTED}
