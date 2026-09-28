"""Enumerations shared by models, schemas and services. Stored as VARCHAR + CHECK."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class VendorStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BankAccountStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class InvoiceStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    RISK_ANALYSIS = "risk_analysis"
    REVIEW_REQUIRED = "review_required"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    FAILED = "failed"


# States from which a human decision can be recorded.
DECIDABLE_STATUSES = frozenset({InvoiceStatus.REVIEW_REQUIRED, InvoiceStatus.PENDING_APPROVAL})
# States in which the pipeline is running; edits and decisions are blocked.
IN_FLIGHT_STATUSES = frozenset(
    {
        InvoiceStatus.UPLOADED,
        InvoiceStatus.QUEUED,
        InvoiceStatus.PROCESSING,
        InvoiceStatus.EXTRACTED,
        InvoiceStatus.RISK_ANALYSIS,
    }
)
FINAL_STATUSES = frozenset({InvoiceStatus.APPROVED, InvoiceStatus.REJECTED})


class InvoiceSource(StrEnum):
    UPLOAD = "upload"
    URL_IMPORT = "url_import"
    EMAIL = "email"


class ExtractionMethod(StrEnum):
    DOCUMENT_AI = "document_ai"
    TEXT_LAYER = "text_layer"
    MANUAL = "manual"


class ExtractionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalSource(StrEnum):
    RULE = "rule"
    AI = "ai"


class SignalResolution(StrEnum):
    OPEN = "open"
    RISK_ACCEPTED = "risk_accepted"
    DISMISSED = "dismissed"


class AIStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    DISABLED = "disabled"
    SUCCEEDED = "succeeded"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"


class ApprovalStepStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"
    EMAIL = "email"


class InboundEmailStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    REJECTED = "rejected"
    FAILED = "failed"
