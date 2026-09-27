"""Invoice email ingestion.

    Email -> attachment extraction -> document storage -> invoice ingestion -> pipeline

Provider-neutral: any inbound source (SMTP relay / inbound-parse webhook, Gmail API
poller, SES -> Pub/Sub) produces raw RFC 822 bytes; `RawMimeParser` turns them into
`ParsedEmail`. V1 ships the webhook-style endpoint (`POST /api/v1/email-ingestion/inbound`,
authenticated with a per-organization token) and a CLI for local testing.
Attachments go through the same validation as manual uploads; email bodies are never
treated as instructions.
"""

import email
import email.policy
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, Conflict, InvalidInput, NotAuthenticated, ServiceUnavailable
from app.core.security import hash_token
from app.infra.storage import StorageError, StorageProvider
from app.infra.tasks import PROCESS_INBOUND_EMAIL, TaskDispatcher
from app.models import InboundEmail, Organization
from app.models.enums import ActorType, InboundEmailStatus, InvoiceSource
from app.modules.audit import service as audit
from app.modules.context import SystemContext
from app.modules.identity.service import organization_settings
from app.modules.invoices.documents import validate_document
from app.modules.invoices.service import ingest_document

logger = logging.getLogger(__name__)

MAX_ATTACHMENTS = 10


@dataclass(frozen=True)
class Attachment:
    filename: str | None
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ParsedEmail:
    message_id: str
    from_address: str | None
    subject: str | None
    attachments: tuple[Attachment, ...]


class InboundEmailParser(Protocol):
    name: str

    def parse(self, raw: bytes) -> ParsedEmail: ...


class RawMimeParser:
    name = "raw_mime"

    def parse(self, raw: bytes) -> ParsedEmail:
        try:
            message = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:  # the stdlib parser is lenient; be defensive anyway
            raise InvalidInput("Malformed email", code="malformed_email") from exc
        assert isinstance(message, EmailMessage)  # noqa: S101
        message_id = (message.get("Message-ID") or "").strip()[:255] or (
            "sha256:" + hashlib.sha256(raw).hexdigest()
        )
        attachments = []
        for part in message.iter_attachments():
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            attachments.append(Attachment(part.get_filename(), part.get_content_type(), payload))
        return ParsedEmail(
            message_id=message_id,
            from_address=str(message.get("From") or "")[:320] or None,
            subject=str(message.get("Subject") or "")[:300] or None,
            attachments=tuple(attachments[:MAX_ATTACHMENTS]),
        )


def organization_for_token(db: Session, settings: Settings, token: str | None) -> Organization:
    if not token:
        raise NotAuthenticated("Missing ingestion token", code="invalid_ingestion_token")
    org = db.scalar(
        select(Organization).where(
            Organization.inbound_email_token_hash
            == hash_token(token, settings.auth_secret.get_secret_value())
        )
    )
    if org is None:
        raise NotAuthenticated("Invalid ingestion token", code="invalid_ingestion_token")
    if not organization_settings(org).email_ingestion_enabled:
        raise AppError(
            "Email ingestion is disabled for this organization", code="email_ingestion_disabled"
        )
    return org


def receive(
    db: Session,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    org: Organization,
    raw: bytes,
    parser: InboundEmailParser,
) -> InboundEmail:
    """Stores the raw message and queues processing. Duplicate Message-IDs are rejected."""
    parsed = parser.parse(raw)
    inbound = InboundEmail(
        id=uuid.uuid4(),
        organization_id=org.id,
        message_id=parsed.message_id,
        from_address=parsed.from_address,
        subject=parsed.subject,
        provider=parser.name,
    )
    key = f"org/{org.id}/inbound-email/{inbound.id}.eml"
    inbound.storage_key = key
    db.add(inbound)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("This email was already received", code="duplicate_email") from exc
    try:
        storage.put(key, raw, "message/rfc822")
    except StorageError as exc:
        db.rollback()
        raise ServiceUnavailable("Storage unavailable", code="storage_unavailable") from exc
    audit.record(
        db,
        SystemContext(org.id, "email-ingestion"),
        "email.received",
        "inbound_email",
        inbound.id,
        {
            "message_id": parsed.message_id,
            "from": parsed.from_address,
            "attachments": len(parsed.attachments),
        },
        actor_type=ActorType.EMAIL,
    )
    db.commit()
    dispatcher.dispatch(PROCESS_INBOUND_EMAIL, inbound_email_id=str(inbound.id))
    return inbound


def process(
    db: Session,
    settings: Settings,
    storage: StorageProvider,
    dispatcher: TaskDispatcher,
    inbound_email_id: uuid.UUID,
    parser: InboundEmailParser | None = None,
) -> InboundEmail | None:
    inbound = db.get(InboundEmail, inbound_email_id)
    if inbound is None or inbound.status != InboundEmailStatus.RECEIVED:
        return inbound
    parser = parser or RawMimeParser()
    actor = SystemContext(
        inbound.organization_id, f"email:{inbound.from_address or 'unknown'}"[:320]
    )
    assert inbound.storage_key is not None  # noqa: S101
    parsed = parser.parse(storage.get(inbound.storage_key))
    created: list[str] = []
    rejected: list[dict[str, str | None]] = []
    for attachment in parsed.attachments:
        try:
            document = validate_document(
                attachment.data,
                attachment.filename,
                attachment.content_type,
                settings.max_upload_bytes,
            )
        except InvalidInput as exc:
            rejected.append({"filename": attachment.filename, "reason": exc.code})
            continue
        result = ingest_document(
            db,
            storage,
            dispatcher,
            actor,
            document,
            InvoiceSource.EMAIL,
            extra_audit={"inbound_email_id": str(inbound.id), "from": parsed.from_address},
        )
        created.append(str(result.invoice.id))
    inbound = db.get(InboundEmail, inbound_email_id)
    assert inbound is not None  # noqa: S101
    inbound.attachments_accepted = len(created)
    inbound.attachments_rejected = len(rejected)
    inbound.created_invoice_ids = ",".join(created) or None
    inbound.processed_at = datetime.now(UTC)
    inbound.status = InboundEmailStatus.PROCESSED if created else InboundEmailStatus.REJECTED
    inbound.error_code = None if created else "no_valid_attachments"
    audit.record(
        db,
        actor,
        "email.processed",
        "inbound_email",
        inbound.id,
        {"invoices_created": created, "attachments_rejected": rejected},
        actor_type=ActorType.EMAIL,
    )
    db.commit()
    return inbound
