"""Vendor management and bank-account change control."""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbDep, EncryptorDep, TenantDep, verify_origin
from app.api.v1.common import Page, Pagination
from app.models import Vendor
from app.models.enums import VendorStatus
from app.modules.vendors import service
from app.modules.vendors.schemas import (
    BankAccountDecision,
    BankAccountInput,
    BankAccountResponse,
    RevealedAccountNumber,
    VendorCreate,
    VendorDetailResponse,
    VendorResponse,
    VendorUpdate,
)

router = APIRouter(prefix="/vendors", tags=["vendors"], dependencies=[Depends(verify_origin)])


def _response(db: DbDep, vendor: Vendor) -> VendorResponse:
    bank = service.current_bank_account(db, vendor)
    return VendorResponse(
        id=vendor.id,
        name=vendor.name,
        gstin=vendor.gstin,
        pan=vendor.pan,
        state_code=vendor.state_code,
        email=vendor.email,
        phone=vendor.phone,
        contact_name=vendor.contact_name,
        address=vendor.address,
        notes=vendor.notes,
        status=vendor.status,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
        current_bank_account=service.bank_account_response(db, bank) if bank else None,
    )


@router.get("", response_model=Page[VendorResponse])
def list_vendors(
    ctx: TenantDep,
    db: DbDep,
    page: Pagination = Depends(),
    q: str | None = Query(default=None, max_length=100),
    status: VendorStatus | None = None,
) -> Page[VendorResponse]:
    items, total = service.list_vendors(
        db, ctx, query=q, status=status, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[_response(db, v) for v in items], total=total, limit=page.limit, offset=page.offset
    )


@router.post("", response_model=VendorResponse, status_code=201)
def create_vendor(
    body: VendorCreate, ctx: TenantDep, db: DbDep, encryptor: EncryptorDep
) -> VendorResponse:
    return _response(db, service.create_vendor(db, ctx, encryptor, body))


@router.get("/{vendor_id}", response_model=VendorDetailResponse)
def get_vendor(vendor_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> VendorDetailResponse:
    vendor = service.get_vendor(db, ctx, vendor_id)
    base = _response(db, vendor)
    return VendorDetailResponse(**base.model_dump(), risk=service.risk_summary(db, ctx, vendor))


@router.patch("/{vendor_id}", response_model=VendorResponse)
def update_vendor(
    vendor_id: uuid.UUID, body: VendorUpdate, ctx: TenantDep, db: DbDep
) -> VendorResponse:
    return _response(db, service.update_vendor(db, ctx, vendor_id, body))


@router.get("/{vendor_id}/bank-accounts", response_model=list[BankAccountResponse])
def bank_accounts(vendor_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> list[BankAccountResponse]:
    return [service.bank_account_response(db, a) for a in service.bank_history(db, ctx, vendor_id)]


@router.post("/{vendor_id}/bank-accounts", response_model=BankAccountResponse, status_code=201)
def change_bank_account(
    vendor_id: uuid.UUID, body: BankAccountInput, ctx: TenantDep, db: DbDep, encryptor: EncryptorDep
) -> BankAccountResponse:
    account = service.change_bank_account(db, ctx, encryptor, vendor_id, body)
    return service.bank_account_response(db, account)


@router.post("/{vendor_id}/bank-accounts/{account_id}/verify", response_model=BankAccountResponse)
def verify_bank_account(
    vendor_id: uuid.UUID,
    account_id: uuid.UUID,
    body: BankAccountDecision,
    ctx: TenantDep,
    db: DbDep,
) -> BankAccountResponse:
    account = service.decide_bank_account(
        db, ctx, vendor_id, account_id, approve=True, note=body.note
    )
    return service.bank_account_response(db, account)


@router.post("/{vendor_id}/bank-accounts/{account_id}/reject", response_model=BankAccountResponse)
def reject_bank_account(
    vendor_id: uuid.UUID,
    account_id: uuid.UUID,
    body: BankAccountDecision,
    ctx: TenantDep,
    db: DbDep,
) -> BankAccountResponse:
    account = service.decide_bank_account(
        db, ctx, vendor_id, account_id, approve=False, note=body.note
    )
    return service.bank_account_response(db, account)


@router.post("/{vendor_id}/bank-accounts/{account_id}/reveal", response_model=RevealedAccountNumber)
def reveal_account(
    vendor_id: uuid.UUID, account_id: uuid.UUID, ctx: TenantDep, db: DbDep, encryptor: EncryptorDep
) -> RevealedAccountNumber:
    return RevealedAccountNumber(
        account_number=service.reveal_account_number(db, ctx, encryptor, vendor_id, account_id)
    )
