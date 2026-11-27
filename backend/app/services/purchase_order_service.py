"""Purchase order drafts (CLAUDE.md Workflow 5).

Rules:
- A draft is created from an AI recommendation (PENDING_REVIEW -> ACCEPTED, at most once) or
  from explicit lines. Creating a draft never changes stock and never contacts a supplier.
- The supplier must exist and be active; every product must be active and supplied by that
  supplier (products have a single supplier; reassign the product to order elsewhere).
- Unit price defaults to the product's unit_cost. Line totals and the order total are computed
  here with Decimal arithmetic (the database also checks total_price = quantity x unit_price).

Approval (human decision, never automatic):
- Only names listed in PO_APPROVERS may approve or reject (403 otherwise; empty list = nobody).
  Matching ignores case and repeated spaces; the configured spelling is recorded.
- Only DRAFT or PENDING_APPROVAL orders can be approved or rejected; any other status -> 409.
- Approving re-checks that the supplier and every product are still active and linked (422).
- Rejecting requires a reason. Every status change is appended to the status history with the
  approver name and time. The order row is locked so concurrent decisions are serialised.
- Approval never changes stock and never contacts the supplier (SENT/RECEIVED come later).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AIRecommendation,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatusHistory,
    Supplier,
)
from app.models.ai_recommendation import RecommendationStatus
from app.models.purchase_order import PurchaseOrderStatus
from app.repositories import purchase_order_repository as repo
from app.schemas.purchase_order import (
    PurchaseOrderApprove,
    PurchaseOrderCreate,
    PurchaseOrderDetail,
    PurchaseOrderItemRead,
    PurchaseOrderRead,
    PurchaseOrderReject,
    PurchaseOrderStatusChange,
    PurchaseOrderStatusTotal,
    PurchaseOrderSummary,
    PurchaseOrderSupplier,
)
from app.core.config import get_settings
from app.services.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError

CENT = Decimal("0.01")
# total_price / total_amount are NUMERIC(14, 2)
MAX_AMOUNT = Decimal("999999999999.99")

S = PurchaseOrderStatus
DECIDABLE = {S.DRAFT.value, S.PENDING_APPROVAL.value}


@dataclass
class _Line:
    product: Product
    quantity: int
    unit_price: Decimal
    recommendation: AIRecommendation | None = None


def line_totals(lines: list[tuple[int, Decimal]]) -> tuple[list[Decimal], Decimal]:
    """(line totals, order total) for (quantity, unit_price) pairs. Exact Decimal arithmetic."""
    totals = [(price * qty).quantize(CENT) for qty, price in lines]
    return totals, sum(totals, Decimal("0.00"))


def _active_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise BusinessRuleError(f"Supplier {supplier_id} not found")
    if not supplier.is_active:
        raise BusinessRuleError(f"Supplier {supplier.name} is inactive")
    return supplier


def _orderable_product(db: Session, product_id: int, supplier: Supplier) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise BusinessRuleError(f"Product {product_id} not found")
    if not product.is_active:
        raise BusinessRuleError(f"Product {product.sku} is inactive")
    if product.supplier_id != supplier.id:
        raise BusinessRuleError(
            f"Product {product.sku} is not supplied by {supplier.name}; "
            "assign the product to this supplier first"
        )
    return product


def _lines_from_recommendation(
    db: Session, data: PurchaseOrderCreate
) -> tuple[Supplier, list[_Line]]:
    rec = repo.lock_recommendation(db, data.recommendation_id)
    if rec is None:
        raise NotFoundError(f"Recommendation {data.recommendation_id} not found")
    if rec.status != RecommendationStatus.PENDING_REVIEW.value:
        raise ConflictError(f"Recommendation {rec.id} is already {rec.status}")
    quantity = data.quantity if data.quantity is not None else rec.suggested_quantity
    if quantity <= 0:
        raise BusinessRuleError(
            f"Recommendation {rec.id} suggests no order; give a quantity to order anyway"
        )
    supplier_id = data.supplier_id or rec.product.supplier_id
    if supplier_id is None:
        raise BusinessRuleError(f"Product {rec.product.sku} has no supplier; give supplier_id")
    supplier = _active_supplier(db, supplier_id)
    product = _orderable_product(db, rec.product_id, supplier)
    price = data.unit_price if data.unit_price is not None else product.unit_cost
    return supplier, [_Line(product, quantity, price, rec)]


def _lines_from_items(db: Session, data: PurchaseOrderCreate) -> tuple[Supplier, list[_Line]]:
    supplier = _active_supplier(db, data.supplier_id)
    seen: set[int] = set()
    lines = []
    for item in data.items:
        if item.product_id in seen:
            raise BusinessRuleError(
                f"Product {item.product_id} appears twice; use one line with the total quantity"
            )
        seen.add(item.product_id)
        product = _orderable_product(db, item.product_id, supplier)
        price = item.unit_price if item.unit_price is not None else product.unit_cost
        lines.append(_Line(product, item.quantity, price))
    return supplier, lines


def create_draft(db: Session, data: PurchaseOrderCreate) -> PurchaseOrderDetail:
    try:
        if data.recommendation_id is not None:
            supplier, lines = _lines_from_recommendation(db, data)
        else:
            supplier, lines = _lines_from_items(db, data)

        line_amounts, total = line_totals([(ln.quantity, ln.unit_price) for ln in lines])
        if any(a > MAX_AMOUNT for a in line_amounts) or total > MAX_AMOUNT:
            raise BusinessRuleError("Order total is too large")

        order_id = repo.next_id(db)
        order = PurchaseOrder(
            id=order_id,
            po_number=f"PO-{datetime.now(timezone.utc):%Y}-{order_id:05d}",
            supplier_id=supplier.id,
            status=PurchaseOrderStatus.DRAFT.value,
            total_amount=total,
            items=[
                PurchaseOrderItem(
                    product_id=ln.product.id,
                    quantity=ln.quantity,
                    unit_price=ln.unit_price,
                    total_price=amount,
                    recommendation_id=ln.recommendation.id if ln.recommendation else None,
                )
                for ln, amount in zip(lines, line_amounts)
            ],
            status_history=[
                PurchaseOrderStatusHistory(
                    from_status=None,
                    to_status=S.DRAFT.value,
                    comment=f"Draft created from AI recommendation #{data.recommendation_id}"
                    if data.recommendation_id is not None
                    else "Draft created manually",
                )
            ],
        )
        db.add(order)
        for ln in lines:
            if ln.recommendation is not None:
                ln.recommendation.status = RecommendationStatus.ACCEPTED.value
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_purchase_order_items_recommendation_id" in str(exc.orig):
            raise ConflictError("This recommendation already has a purchase order") from exc
        raise
    except Exception:
        db.rollback()
        raise
    return get_order(db, order_id)


# ---------- approval ----------


def _check_still_orderable(db: Session, order: PurchaseOrder) -> None:
    """Master data may have changed since the draft was made; re-validate before approving."""
    supplier = _active_supplier(db, order.supplier_id)
    for item in order.items:
        _orderable_product(db, item.product_id, supplier)


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


def authorized_approver(name: str) -> str:
    """The configured spelling of `name` if it is an approver, else ForbiddenError.
    Error messages never list the configured approvers."""
    approvers = get_settings().po_approver_names
    if not approvers:
        raise ForbiddenError("No purchase order approvers are configured (set PO_APPROVERS)")
    wanted = _normalise(name)
    for configured in approvers:
        if _normalise(configured) == wanted:
            return configured
    raise ForbiddenError(f"{' '.join(name.split())} is not an authorized purchase order approver")


def _decide(
    db: Session, order_id: int, to_status: PurchaseOrderStatus, approver: str, comment: str | None
) -> PurchaseOrderDetail:
    approver = authorized_approver(approver)  # checked before touching the order
    try:
        order = repo.lock_order(db, order_id)
        if order is None:
            raise NotFoundError(f"Purchase order {order_id} not found")
        if order.status not in DECIDABLE:
            raise ConflictError(f"Purchase order {order.po_number} is already {order.status}")
        if to_status == S.APPROVED:
            _check_still_orderable(db, order)
        from_status = order.status
        order.status = to_status.value
        if to_status == S.APPROVED:
            order.approved_at = datetime.now(timezone.utc)
        db.add(
            PurchaseOrderStatusHistory(
                purchase_order_id=order.id,
                from_status=from_status,
                to_status=to_status.value,
                changed_by=approver,
                comment=comment or None,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_order(db, order_id)


def approve(db: Session, order_id: int, data: PurchaseOrderApprove) -> PurchaseOrderDetail:
    return _decide(db, order_id, S.APPROVED, data.approver, data.comment)


def reject(db: Session, order_id: int, data: PurchaseOrderReject) -> PurchaseOrderDetail:
    return _decide(db, order_id, S.REJECTED, data.approver, data.reason)


# ---------- reads ----------


def _to_read_fields(order: PurchaseOrder) -> dict:
    return dict(
        id=order.id,
        po_number=order.po_number,
        supplier_id=order.supplier_id,
        supplier_name=order.supplier.name,
        status=order.status,
        total_amount=order.total_amount,
        item_count=len(order.items),
        created_at=order.created_at,
        approved_at=order.approved_at,
    )


def to_detail(order: PurchaseOrder) -> PurchaseOrderDetail:
    s = order.supplier
    return PurchaseOrderDetail(
        **_to_read_fields(order),
        supplier=PurchaseOrderSupplier(
            id=s.id, name=s.name, email=s.email, phone=s.phone, lead_time_days=s.lead_time_days
        ),
        items=[
            PurchaseOrderItemRead(
                id=i.id,
                product_id=i.product_id,
                product_sku=i.product.sku,
                product_name=i.product.name,
                quantity=i.quantity,
                unit_price=i.unit_price,
                total_price=i.total_price,
                recommendation_id=i.recommendation_id,
            )
            for i in order.items
        ],
        status_history=[
            PurchaseOrderStatusChange(
                from_status=h.from_status,
                to_status=h.to_status,
                changed_by=h.changed_by,
                comment=h.comment,
                created_at=h.created_at,
            )
            for h in order.status_history
        ],
    )


def list_orders(db: Session, **filters) -> list[PurchaseOrderRead]:
    return [PurchaseOrderRead(**_to_read_fields(o)) for o in repo.list_orders(db, **filters)]


def get_order(db: Session, order_id: int) -> PurchaseOrderDetail:
    order = repo.get_order(db, order_id)
    if order is None:
        raise NotFoundError(f"Purchase order {order_id} not found")
    return to_detail(order)


def summarize(db: Session, supplier_id: int | None = None) -> PurchaseOrderSummary:
    totals = repo.totals_by_status(db, supplier_id)
    by_status = [
        PurchaseOrderStatusTotal(
            status=status.value,
            order_count=totals.get(status.value, (0, Decimal("0")))[0],
            total_amount=totals.get(status.value, (0, Decimal("0")))[1].quantize(CENT),
        )
        for status in S  # enum order = workflow order
    ]
    row = {t.status: t for t in by_status}
    waiting = [row[S.DRAFT.value], row[S.PENDING_APPROVAL.value]]
    return PurchaseOrderSummary(
        awaiting_decision_count=sum(t.order_count for t in waiting),
        awaiting_decision_amount=sum((t.total_amount for t in waiting), Decimal("0.00")),
        approved_count=row[S.APPROVED.value].order_count,
        approved_amount=row[S.APPROVED.value].total_amount,
        total_orders=sum(t.order_count for t in by_status),
        by_status=by_status,
    )
