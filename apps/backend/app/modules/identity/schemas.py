"""Request/response contracts for auth, organizations and members."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import MembershipStatus, RiskLevel, Role


class OrganizationSettings(BaseModel):
    """Per-tenant control configuration. Every value has a safe default."""

    model_config = ConfigDict(extra="forbid")

    # Approval policy
    high_value_threshold: Decimal = Field(default=Decimal("500000"), ge=0)
    second_approval_risk_levels: list[RiskLevel] = Field(default_factory=lambda: [RiskLevel.HIGH])
    require_po_above: Decimal | None = Field(default=Decimal("100000"), ge=0)
    # Matching tolerances (deterministic)
    price_tolerance_percent: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    quantity_tolerance_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    amount_tolerance_absolute: Decimal = Field(default=Decimal("1.00"), ge=0)
    # Risk rule parameters
    duplicate_window_days: int = Field(default=180, ge=1, le=3650)
    unusual_amount_multiplier: Decimal = Field(default=Decimal("3"), gt=1)
    price_increase_alert_percent: Decimal = Field(default=Decimal("10"), gt=0)
    split_invoice_window_days: int = Field(default=7, ge=1, le=90)
    new_vendor_days: int = Field(default=30, ge=0, le=365)
    bank_change_alert_days: int = Field(default=90, ge=0, le=3650)
    # AI (data-sharing controls)
    ai_assistance_enabled: bool = True
    ai_document_extraction_enabled: bool = True
    # Ingestion
    email_ingestion_enabled: bool = False
    # Retention (policy foundation; automated purging is not implemented in V1)
    document_retention_days: int = Field(default=2920, ge=365)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SwitchOrganizationRequest(BaseModel):
    organization_id: uuid.UUID


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: Role


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    organization: OrganizationSummary | None
    organizations: list[OrganizationSummary]
    permissions: list[str]
    csrf_token: str
    session_expires_at: datetime


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    gstin: str | None
    state_code: str | None
    settings: OrganizationSettings
    inbound_email_address: str | None
    email_ingestion_configured: bool


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    gstin: str | None = Field(default=None, max_length=20)
    settings: OrganizationSettings | None = None


class MemberResponse(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: Role
    status: MembershipStatus
    joined_at: datetime


class MemberUpdate(BaseModel):
    role: Role | None = None
    status: MembershipStatus | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime
    accepted_at: datetime | None
    # Returned once at creation so an admin can share it (no email delivery in V1).
    invitation_url: str | None = None


class InvitationPreview(BaseModel):
    organization_name: str
    email: str
    role: Role
    existing_user: bool


class InvitationAccept(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    password: str = Field(min_length=1, max_length=128)


class EmailIngestionTokenResponse(BaseModel):
    inbound_email_address: str
    # Shown once; only its hash is stored.
    ingestion_token: str
