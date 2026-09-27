"""Purchase orders and their lines."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Quantity, Rate, TenantOwned, Timestamps, UUIDPrimaryKey
from app.db.types import enum_column
from app.models.enums import PurchaseOrderStatus


class PurchaseOrder(UUIDPrimaryKey, Timestamps, TenantOwned, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("organization_id", "po_number", name="org_po_number"),)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="RESTRICT"), index=True
    )
    po_number: Mapped[str] = mapped_column(String(64))
    issue_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        enum_column(PurchaseOrderStatus, "po_status"), default=PurchaseOrderStatus.OPEN
    )
    subtotal: Mapped[Decimal]
    tax_total: Mapped[Decimal]
    total: Mapped[Decimal]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.line_no",
    )


class PurchaseOrderLine(UUIDPrimaryKey, TenantOwned, Base):
    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    sku: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit_price: Mapped[Decimal]
    tax_rate: Mapped[Decimal] = mapped_column(Rate)
    amount: Mapped[Decimal]

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
