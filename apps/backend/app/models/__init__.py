"""Importing this package registers every table on `Base.metadata`."""

from app.models.audit import AuditEvent
from app.models.email import InboundEmail
from app.models.identity import Invitation, Membership, Organization, User, UserSession
from app.models.invoices import (
    Invoice,
    InvoiceDocument,
    InvoiceExtraction,
    InvoiceLine,
    InvoiceStatusChange,
)
from app.models.notifications import Notification
from app.models.purchasing import PurchaseOrder, PurchaseOrderLine
from app.models.review import ApprovalStep, Review
from app.models.risk import RiskAssessment, RiskSignal
from app.models.vendors import Vendor, VendorBankAccount

__all__ = [
    "ApprovalStep",
    "AuditEvent",
    "InboundEmail",
    "Invitation",
    "Invoice",
    "InvoiceDocument",
    "InvoiceExtraction",
    "InvoiceLine",
    "InvoiceStatusChange",
    "Membership",
    "Notification",
    "Organization",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "Review",
    "RiskAssessment",
    "RiskSignal",
    "User",
    "UserSession",
    "Vendor",
    "VendorBankAccount",
]
