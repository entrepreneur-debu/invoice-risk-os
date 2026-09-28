"""Purchase order contracts. Amounts are computed server-side from quantity x price."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PurchaseOrderStatus


class POLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    sku: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    tax_rate: Decimal = Field(default=Decimal("18"), ge=0, le=100, decimal_places=3)


class POCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: uuid.UUID
    po_number: str = Field(min_length=1, max_length=64)
    issue_date: date | None = None
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=5000)
    status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN
    lines: list[POLineInput] = Field(min_length=1, max_length=500)


class POUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    status: PurchaseOrderStatus | None = None
    lines: list[POLineInput] | None = Field(default=None, min_length=1, max_length=500)


class POLineResponse(BaseModel):
    id: uuid.UUID
    line_no: int
    description: str
    sku: str | None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    amount: Decimal
    invoiced_quantity: Decimal


class POResponse(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str
    po_number: str
    issue_date: date | None
    currency: str
    status: PurchaseOrderStatus
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    invoiced_total: Decimal
    notes: str | None
    created_at: datetime
    lines: list[POLineResponse]
    linked_invoice_ids: list[uuid.UUID]
