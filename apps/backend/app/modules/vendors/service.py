"""Vendor master data and bank-account change control."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidInput, NotFound, PermissionDenied
from app.core.security import FieldEncryptor
from app.finance.gst import gstin_state_code, normalize_gstin, validate_gstin
from app.models import Invoice, RiskSignal, User, Vendor, VendorBankAccount
from app.models.enums import (
    BankAccountStatus,
    InvoiceStatus,
    Severity,
    SignalResolution,
    VendorStatus,
)
from app.modules.audit import service as audit
from app.modules.context import TenantContext
from app.modules.notifications import service as notifications
from app.modules.permissions import Permission
from app.modules.vendors.schemas import (
    BankAccountInput,
    BankAccountResponse,
    VendorCreate,
    VendorRiskSummary,
    VendorUpdate,
)

_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_LEGAL_SUFFIXES = re.compile(
    r"\b(private limited|pvt\.? ?ltd\.?|pvt|limited|ltd\.?|llp|inc\.?|co\.?|company|"
    r"corporation|corp\.?|enterprises?|industries)\b"
)


def normalize_vendor_name(name: str) -> str:
    lowered = name.lower().replace("&", " and ")
    lowered = _LEGAL_SUFFIXES.sub(" ", lowered)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def normalize_account_number(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw)


def mask_last4(last4: str) -> str:
    return f"•••• {last4}"


def _validated_gstin(raw: str | None) -> str | None:
    gstin = normalize_gstin(raw)
    if gstin is None:
        return None
    validation = validate_gstin(gstin)
    if not validation.valid:
        raise InvalidInput(f"Invalid GSTIN ({validation.reason})", code="invalid_gstin")
    return gstin


def _validated_pan(raw: str | None, gstin: str | None) -> str | None:
    pan = raw.strip().upper() if raw else (gstin[2:12] if gstin else None)
    if pan is None:
        return None
    if not _PAN.match(pan):
        raise InvalidInput("Invalid PAN format", code="invalid_pan")
    if gstin and gstin[2:12] != pan:
        raise InvalidInput("PAN does not match the PAN embedded in the GSTIN", code="pan_mismatch")
    return pan


def get_vendor(db: Session, ctx: TenantContext, vendor_id: uuid.UUID) -> Vendor:
    ctx.require(Permission.VENDOR_READ)
    vendor = db.scalar(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.organization_id == ctx.organization_id)
    )
    if vendor is None:
        raise NotFound()
    return vendor


def list_vendors(
    db: Session,
    ctx: TenantContext,
    *,
    query: str | None,
    status: VendorStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[Vendor], int]:
    ctx.require(Permission.VENDOR_READ)
    stmt = select(Vendor).where(Vendor.organization_id == ctx.organization_id)
    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Vendor.name).like(like),
                Vendor.normalized_name.like(like),
                func.lower(Vendor.gstin).like(like),
            )
        )
    if status:
        stmt = stmt.where(Vendor.status == status)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    items = list(db.scalars(stmt.order_by(Vendor.name).limit(limit).offset(offset)))
    return items, total


def current_bank_account(db: Session, vendor: Vendor) -> VendorBankAccount | None:
    return db.scalar(
        select(VendorBankAccount).where(
            VendorBankAccount.vendor_id == vendor.id,
            VendorBankAccount.organization_id == vendor.organization_id,
            VendorBankAccount.is_current.is_(True),
        )
    )


def create_vendor(
    db: Session, ctx: TenantContext, encryptor: FieldEncryptor, request: VendorCreate
) -> Vendor:
    ctx.require(Permission.VENDOR_WRITE)
    gstin = _validated_gstin(request.gstin)
    vendor = Vendor(
        organization_id=ctx.organization_id,
        name=request.name.strip(),
        normalized_name=normalize_vendor_name(request.name),
        gstin=gstin,
        pan=_validated_pan(request.pan, gstin),
        state_code=gstin_state_code(gstin),
        email=request.email,
        phone=request.phone,
        contact_name=request.contact_name,
        address=request.address,
        notes=request.notes,
        created_by_id=ctx.user_id,
    )
    db.add(vendor)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("A vendor with this GSTIN already exists", code="duplicate_gstin") from exc
    audit.record(
        db, ctx, "vendor.created", "vendor", vendor.id, {"name": vendor.name, "gstin": vendor.gstin}
    )
    if request.bank_account is not None:
        _add_bank_account(db, ctx, encryptor, vendor, request.bank_account, initial=True)
    db.commit()
    return vendor


def update_vendor(
    db: Session, ctx: TenantContext, vendor_id: uuid.UUID, request: VendorUpdate
) -> Vendor:
    ctx.require(Permission.VENDOR_WRITE)
    vendor = get_vendor(db, ctx, vendor_id)
    data = request.model_dump(exclude_unset=True)
    changes: dict[str, object] = {}
    if "gstin" in data:
        gstin = _validated_gstin(data["gstin"])
        data["gstin"] = gstin
        data["state_code"] = gstin_state_code(gstin)
        data["pan"] = _validated_pan(data.get("pan", vendor.pan if gstin is None else None), gstin)
    elif "pan" in data:
        data["pan"] = _validated_pan(data["pan"], vendor.gstin)
    if data.get("name"):
        data["name"] = data["name"].strip()
        data["normalized_name"] = normalize_vendor_name(data["name"])
    for field, value in data.items():
        if getattr(vendor, field) != value:
            old = getattr(vendor, field)
            changes[field] = {
                "from": getattr(old, "value", old),
                "to": getattr(value, "value", value),
            }
            setattr(vendor, field, value)
    if changes:
        # GSTIN changes alter vendor identity: surface them like other sensitive changes.
        action = "vendor.gstin_changed" if "gstin" in changes else "vendor.updated"
        audit.record(db, ctx, action, "vendor", vendor.id, changes)
        if "gstin" in changes:
            notifications.notify_permission(
                db,
                ctx.organization_id,
                Permission.VENDOR_BANK_VERIFY,
                kind="vendor.gstin_changed",
                severity=Severity.MEDIUM,
                title=f"GSTIN changed for {vendor.name}",
                body="A vendor's GSTIN was changed. Confirm the change with the vendor.",
                entity_type="vendor",
                entity_id=vendor.id,
                exclude_user_id=ctx.user_id,
            )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("A vendor with this GSTIN already exists", code="duplicate_gstin") from exc
    return vendor


def _add_bank_account(
    db: Session,
    ctx: TenantContext,
    encryptor: FieldEncryptor,
    vendor: Vendor,
    request: BankAccountInput,
    *,
    initial: bool,
) -> VendorBankAccount:
    number = normalize_account_number(request.account_number)
    if not number.isdigit() or not 6 <= len(number) <= 18:
        raise InvalidInput("Account number must be 6-18 digits", code="invalid_account_number")
    ifsc = request.ifsc.strip().upper()
    if not _IFSC.match(ifsc):
        raise InvalidInput("Invalid IFSC code", code="invalid_ifsc")
    previous = current_bank_account(db, vendor)
    if not initial and not (request.change_reason and request.change_reason.strip()):
        raise InvalidInput(
            "A reason is required when changing bank details", code="change_reason_required"
        )
    fingerprint = encryptor.fingerprint(number)
    if (
        previous is not None
        and previous.account_fingerprint == fingerprint
        and previous.ifsc == ifsc
    ):
        raise Conflict("This is already the current bank account", code="unchanged_bank_account")

    account_id = uuid.uuid4()
    account = VendorBankAccount(
        id=account_id,
        organization_id=ctx.organization_id,
        vendor_id=vendor.id,
        account_holder_name=request.account_holder_name.strip(),
        account_number_encrypted=encryptor.encrypt(number, associated_data=str(account_id)),
        account_last4=number[-4:],
        account_fingerprint=fingerprint,
        ifsc=ifsc,
        bank_name=request.bank_name,
        status=BankAccountStatus.PENDING_VERIFICATION,
        is_current=True,
        previous_account_id=previous.id if previous else None,
        change_reason=request.change_reason,
        created_by_id=ctx.user_id,
    )
    if previous is not None:
        previous.is_current = False
        previous.status = BankAccountStatus.SUPERSEDED
        db.flush()
    db.add(account)
    db.flush()
    details = {
        "bank_account_id": account.id,
        "previous": {
            "last4": previous.account_last4,
            "ifsc": previous.ifsc,
            "account_id": previous.id,
        }
        if previous
        else None,
        "new": {
            "last4": account.account_last4,
            "ifsc": ifsc,
            "holder": account.account_holder_name,
        },
        "reason": request.change_reason,
        "verification_state": account.status.value,
    }
    audit.record(
        db,
        ctx,
        "vendor.bank_account.added" if previous is None else "vendor.bank_account.changed",
        "vendor",
        vendor.id,
        details,
    )
    if previous is not None:
        notifications.notify_permission(
            db,
            ctx.organization_id,
            Permission.VENDOR_BANK_VERIFY,
            kind="vendor.bank_account_changed",
            severity=Severity.HIGH,
            title=f"Bank account changed for {vendor.name}",
            body=(
                f"Account ending {previous.account_last4} was replaced by an account ending "
                f"{account.account_last4}. Verify with the vendor through a known contact "
                "before paying."
            ),
            entity_type="vendor",
            entity_id=vendor.id,
            exclude_user_id=ctx.user_id,
        )
    return account


def change_bank_account(
    db: Session,
    ctx: TenantContext,
    encryptor: FieldEncryptor,
    vendor_id: uuid.UUID,
    request: BankAccountInput,
) -> VendorBankAccount:
    ctx.require(Permission.VENDOR_WRITE)
    vendor = get_vendor(db, ctx, vendor_id)
    account = _add_bank_account(
        db, ctx, encryptor, vendor, request, initial=current_bank_account(db, vendor) is None
    )
    db.commit()
    return account


def _get_account(
    db: Session, ctx: TenantContext, vendor_id: uuid.UUID, account_id: uuid.UUID
) -> VendorBankAccount:
    account = db.scalar(
        select(VendorBankAccount).where(
            VendorBankAccount.id == account_id,
            VendorBankAccount.vendor_id == vendor_id,
            VendorBankAccount.organization_id == ctx.organization_id,
        )
    )
    if account is None:
        raise NotFound()
    return account


def decide_bank_account(
    db: Session,
    ctx: TenantContext,
    vendor_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    approve: bool,
    note: str,
) -> VendorBankAccount:
    ctx.require(Permission.VENDOR_BANK_VERIFY)
    vendor = get_vendor(db, ctx, vendor_id)
    account = _get_account(db, ctx, vendor.id, account_id)
    if account.status != BankAccountStatus.PENDING_VERIFICATION:
        raise Conflict("Only pending bank accounts can be verified or rejected", code="not_pending")
    if account.created_by_id == ctx.user_id:
        raise PermissionDenied(
            "Bank details must be verified by a different person than the one who entered them",
            code="segregation_of_duties",
        )
    account.verified_by_id = ctx.user_id
    account.verified_at = datetime.now(UTC)
    account.verification_note = note
    if approve:
        account.status = BankAccountStatus.VERIFIED
    else:
        account.status = BankAccountStatus.REJECTED
        account.is_current = False
        if account.previous_account_id:
            previous = db.get(VendorBankAccount, account.previous_account_id)
            if previous is not None and previous.organization_id == ctx.organization_id:
                previous.is_current = True
                previous.status = (
                    BankAccountStatus.VERIFIED
                    if previous.verified_at
                    else BankAccountStatus.PENDING_VERIFICATION
                )
    audit.record(
        db,
        ctx,
        "vendor.bank_account.verified" if approve else "vendor.bank_account.rejected",
        "vendor",
        vendor.id,
        {"bank_account_id": account.id, "last4": account.account_last4, "note": note},
    )
    db.commit()
    return account


def reveal_account_number(
    db: Session,
    ctx: TenantContext,
    encryptor: FieldEncryptor,
    vendor_id: uuid.UUID,
    account_id: uuid.UUID,
) -> str:
    ctx.require(Permission.VENDOR_BANK_REVEAL)
    account = _get_account(db, ctx, vendor_id, account_id)
    number = encryptor.decrypt(account.account_number_encrypted, associated_data=str(account.id))
    audit.record(
        db,
        ctx,
        "vendor.bank_account.revealed",
        "vendor",
        vendor_id,
        {"bank_account_id": account.id, "last4": account.account_last4},
    )
    db.commit()
    return number


def bank_history(db: Session, ctx: TenantContext, vendor_id: uuid.UUID) -> list[VendorBankAccount]:
    vendor = get_vendor(db, ctx, vendor_id)
    return list(
        db.scalars(
            select(VendorBankAccount)
            .where(
                VendorBankAccount.vendor_id == vendor.id,
                VendorBankAccount.organization_id == ctx.organization_id,
            )
            .order_by(VendorBankAccount.created_at.desc())
        )
    )


def bank_account_response(db: Session, account: VendorBankAccount) -> BankAccountResponse:
    emails = {}
    ids = [i for i in (account.created_by_id, account.verified_by_id) if i]
    if ids:
        emails = dict(db.execute(select(User.id, User.email).where(User.id.in_(ids))).all())
    return BankAccountResponse(
        id=account.id,
        account_holder_name=account.account_holder_name,
        account_number_masked=mask_last4(account.account_last4),
        ifsc=account.ifsc,
        bank_name=account.bank_name,
        status=account.status,
        is_current=account.is_current,
        previous_account_id=account.previous_account_id,
        change_reason=account.change_reason,
        source=account.source,
        created_at=account.created_at,
        created_by_email=emails.get(account.created_by_id) if account.created_by_id else None,
        verified_by_email=emails.get(account.verified_by_id) if account.verified_by_id else None,
        verified_at=account.verified_at,
        verification_note=account.verification_note,
    )


def risk_summary(db: Session, ctx: TenantContext, vendor: Vendor) -> VendorRiskSummary:
    counted = [s for s in InvoiceStatus if s not in (InvoiceStatus.FAILED,)]
    row = db.execute(
        select(
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.total), 0),
            func.max(Invoice.created_at),
        ).where(
            Invoice.organization_id == ctx.organization_id,
            Invoice.vendor_id == vendor.id,
            Invoice.status.in_(counted),
        )
    ).one()
    since = datetime.now(UTC) - timedelta(days=90)
    signal_base = (
        select(func.count(RiskSignal.id))
        .join(Invoice, Invoice.id == RiskSignal.invoice_id)
        .where(RiskSignal.organization_id == ctx.organization_id, Invoice.vendor_id == vendor.id)
    )
    open_high = db.scalar(
        signal_base.where(
            RiskSignal.severity == Severity.HIGH,
            RiskSignal.resolution == SignalResolution.OPEN,
            Invoice.status.in_([InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.PENDING_APPROVAL]),
        )
    )
    recent = db.scalar(signal_base.where(RiskSignal.created_at >= since))
    current = current_bank_account(db, vendor)
    last_change = db.scalar(
        select(func.max(VendorBankAccount.created_at)).where(
            VendorBankAccount.vendor_id == vendor.id,
            VendorBankAccount.previous_account_id.is_not(None),
        )
    )
    return VendorRiskSummary(
        invoice_count=int(row[0] or 0),
        total_invoiced=Decimal(row[1] or 0),
        open_high_signals=int(open_high or 0),
        signals_last_90_days=int(recent or 0),
        pending_bank_verification=bool(
            current and current.status == BankAccountStatus.PENDING_VERIFICATION
        ),
        last_bank_change_at=last_change,
        last_invoice_date=row[2],
    )
