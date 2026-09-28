"""Vendor contracts. Bank account numbers are write-only: responses show last 4 digits."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import BankAccountStatus, VendorStatus


class VendorBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    gstin: str | None = Field(default=None, max_length=20)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    contact_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class VendorCreate(VendorBase):
    bank_account: "BankAccountInput | None" = None


class VendorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    gstin: str | None = Field(default=None, max_length=20)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    contact_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)
    status: VendorStatus | None = None


class BankAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_holder_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=6, max_length=34)
    ifsc: str = Field(min_length=11, max_length=11)
    bank_name: str | None = Field(default=None, max_length=200)
    change_reason: str | None = Field(default=None, max_length=1000)


class BankAccountDecision(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    account_holder_name: str
    account_number_masked: str
    ifsc: str
    bank_name: str | None
    status: BankAccountStatus
    is_current: bool
    previous_account_id: uuid.UUID | None
    change_reason: str | None
    source: str
    created_at: datetime
    created_by_email: str | None
    verified_by_email: str | None
    verified_at: datetime | None
    verification_note: str | None


class RevealedAccountNumber(BaseModel):
    account_number: str


class VendorRiskSummary(BaseModel):
    invoice_count: int
    total_invoiced: Decimal
    open_high_signals: int
    signals_last_90_days: int
    pending_bank_verification: bool
    last_bank_change_at: datetime | None
    last_invoice_date: datetime | None


class VendorResponse(BaseModel):
    id: uuid.UUID
    name: str
    gstin: str | None
    pan: str | None
    state_code: str | None
    email: str | None
    phone: str | None
    contact_name: str | None
    address: str | None
    notes: str | None
    status: VendorStatus
    created_at: datetime
    updated_at: datetime
    current_bank_account: BankAccountResponse | None


class VendorDetailResponse(VendorResponse):
    risk: VendorRiskSummary


VendorCreate.model_rebuild()
