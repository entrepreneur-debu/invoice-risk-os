"""Vendors and their bank accounts (history is retained; nothing is overwritten)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey
from app.db.types import enum_column
from app.models.enums import BankAccountStatus, VendorStatus


class Vendor(UUIDPrimaryKey, Timestamps, TenantOwned, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index(
            "uq_vendors_org_gstin",
            "organization_id",
            "gstin",
            unique=True,
            postgresql_where=text("gstin IS NOT NULL"),
        ),
        Index("ix_vendors_org_normalized_name", "organization_id", "normalized_name"),
    )

    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    state_code: Mapped[str | None] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VendorStatus] = mapped_column(
        enum_column(VendorStatus, "vendor_status"), default=VendorStatus.ACTIVE
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class VendorBankAccount(UUIDPrimaryKey, Timestamps, TenantOwned, Base):
    """One row per account version. A change adds a row and supersedes the old one."""

    __tablename__ = "vendor_bank_accounts"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), index=True
    )
    account_holder_name: Mapped[str] = mapped_column(String(200))
    account_number_encrypted: Mapped[str] = mapped_column(Text)
    account_last4: Mapped[str] = mapped_column(String(4))
    account_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    ifsc: Mapped[str] = mapped_column(String(11))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[BankAccountStatus] = mapped_column(
        enum_column(BankAccountStatus, "bank_account_status"),
        default=BankAccountStatus.PENDING_VERIFICATION,
    )
    is_current: Mapped[bool] = mapped_column(default=True)
    previous_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor_bank_accounts.id", ondelete="SET NULL")
    )
    change_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text)
