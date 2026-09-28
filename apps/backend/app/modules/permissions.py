"""Role-based access control: the single source of truth for who may do what.

Enforced server-side by `require_permission` (API) and inside services. The frontend
only uses the same matrix (via /auth/me) to decide what to show; hiding a button is
never the control. Documented in docs/security.md ("Permission matrix").
"""

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    ORG_READ = "org.read"
    ORG_MANAGE_SETTINGS = "org.manage_settings"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    VENDOR_READ = "vendor.read"
    VENDOR_WRITE = "vendor.write"
    VENDOR_BANK_VERIFY = "vendor.bank_verify"
    VENDOR_BANK_REVEAL = "vendor.bank_reveal"
    PO_READ = "po.read"
    PO_WRITE = "po.write"
    INVOICE_READ = "invoice.read"
    INVOICE_UPLOAD = "invoice.upload"
    INVOICE_EDIT = "invoice.edit"
    INVOICE_REVIEW = "invoice.review"
    INVOICE_APPROVE_FINAL = "invoice.approve_final"
    RISK_OVERRIDE = "risk.override"
    AUDIT_READ = "audit.read"
    ANALYTICS_READ = "analytics.read"
    EMAIL_INGESTION_MANAGE = "email_ingestion.manage"


_VIEWER = frozenset(
    {
        Permission.ORG_READ,
        Permission.VENDOR_READ,
        Permission.PO_READ,
        Permission.INVOICE_READ,
        Permission.ANALYTICS_READ,
    }
)
_REVIEWER = _VIEWER | {
    Permission.MEMBERS_READ,
    Permission.VENDOR_WRITE,
    Permission.PO_WRITE,
    Permission.INVOICE_UPLOAD,
    Permission.INVOICE_EDIT,
    Permission.INVOICE_REVIEW,
}
_ADMIN = _REVIEWER | {
    Permission.ORG_MANAGE_SETTINGS,
    Permission.MEMBERS_MANAGE,
    Permission.VENDOR_BANK_VERIFY,
    Permission.VENDOR_BANK_REVEAL,
    Permission.INVOICE_APPROVE_FINAL,
    Permission.RISK_OVERRIDE,
    Permission.AUDIT_READ,
    Permission.EMAIL_INGESTION_MANAGE,
}
_OWNER = _ADMIN

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: _VIEWER,
    Role.REVIEWER: frozenset(_REVIEWER),
    Role.ADMIN: frozenset(_ADMIN),
    Role.OWNER: frozenset(_OWNER),
}

# Which roles each role may grant or change. Only owners manage owners and admins.
ASSIGNABLE_ROLES: dict[Role, frozenset[Role]] = {
    Role.OWNER: frozenset(Role),
    Role.ADMIN: frozenset({Role.REVIEWER, Role.VIEWER}),
    Role.REVIEWER: frozenset(),
    Role.VIEWER: frozenset(),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def permissions_for(role: Role) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS[role])
