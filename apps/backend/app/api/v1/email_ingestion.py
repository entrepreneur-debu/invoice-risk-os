"""Inbound invoice email endpoint (token-authenticated; not cookie/CSRF based)."""

import uuid

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from app.api.deps import DbDep, DispatcherDep, SettingsDep, StorageDep
from app.core.errors import InvalidInput
from app.modules.email_ingestion import service

router = APIRouter(prefix="/email-ingestion", tags=["email-ingestion"])


class InboundAccepted(BaseModel):
    inbound_email_id: uuid.UUID
    status: str


@router.post("/inbound", response_model=InboundAccepted, status_code=202)
async def receive_email(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
    dispatcher: DispatcherDep,
    x_ingestion_token: str | None = Header(default=None),
) -> InboundAccepted:
    org = service.organization_for_token(db, settings, x_ingestion_token)
    raw = await request.body()
    if not raw:
        raise InvalidInput("Empty message", code="empty_email")
    inbound = service.receive(db, storage, dispatcher, org, raw, service.RawMimeParser())
    return InboundAccepted(inbound_email_id=inbound.id, status=inbound.status.value)
