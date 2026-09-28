"""Organization settings, members, invitations and email-ingestion configuration."""

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import DbDep, SettingsDep, TenantDep, verify_origin
from app.api.v1.common import Message
from app.core.config import Settings
from app.models import Organization
from app.modules.identity import service
from app.modules.identity.schemas import (
    EmailIngestionTokenResponse,
    InvitationCreate,
    InvitationResponse,
    MemberResponse,
    MemberUpdate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.modules.permissions import Permission

router = APIRouter(
    prefix="/organization", tags=["organization"], dependencies=[Depends(verify_origin)]
)


def _org_response(settings: Settings, org: Organization) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        gstin=org.gstin,
        state_code=org.state_code,
        settings=service.organization_settings(org),
        inbound_email_address=service.inbound_email_address(settings, org),
        email_ingestion_configured=org.inbound_email_token_hash is not None,
    )


@router.get("", response_model=OrganizationResponse)
def get_organization(ctx: TenantDep, db: DbDep, settings: SettingsDep) -> OrganizationResponse:
    ctx.require(Permission.ORG_READ)
    return _org_response(settings, service.get_organization(db, ctx))


@router.patch("", response_model=OrganizationResponse)
def update_organization(
    body: OrganizationUpdate, ctx: TenantDep, db: DbDep, settings: SettingsDep
) -> OrganizationResponse:
    return _org_response(settings, service.update_organization(db, ctx, body))


@router.post("/email-ingestion/token", response_model=EmailIngestionTokenResponse)
def rotate_ingestion_token(
    ctx: TenantDep, db: DbDep, settings: SettingsDep
) -> EmailIngestionTokenResponse:
    token = service.rotate_ingestion_token(db, settings, ctx)
    org = service.get_organization(db, ctx)
    return EmailIngestionTokenResponse(
        inbound_email_address=service.inbound_email_address(settings, org), ingestion_token=token
    )


@router.get("/members", response_model=list[MemberResponse])
def list_members(ctx: TenantDep, db: DbDep) -> list[MemberResponse]:
    return [
        MemberResponse(
            membership_id=m.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            status=m.status,
            joined_at=m.created_at,
        )
        for m, u in service.list_members(db, ctx)
    ]


@router.patch("/members/{membership_id}", response_model=Message)
def update_member(
    membership_id: uuid.UUID, body: MemberUpdate, ctx: TenantDep, db: DbDep
) -> Message:
    service.update_member(db, ctx, membership_id, body.role, body.status)
    return Message(message="Member updated")


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(ctx: TenantDep, db: DbDep) -> list[InvitationResponse]:
    return [
        InvitationResponse(
            id=i.id, email=i.email, role=i.role, expires_at=i.expires_at, accepted_at=i.accepted_at
        )
        for i in service.list_invitations(db, ctx)
    ]


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    body: InvitationCreate, ctx: TenantDep, db: DbDep, settings: SettingsDep
) -> InvitationResponse:
    invitation, url = service.create_invitation(db, settings, ctx, body)
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        accepted_at=None,
        invitation_url=url,
    )


@router.delete("/invitations/{invitation_id}", response_model=Message)
def revoke_invitation(invitation_id: uuid.UUID, ctx: TenantDep, db: DbDep) -> Message:
    service.revoke_invitation(db, ctx, invitation_id)
    return Message(message="Invitation revoked")
