"""Request-scoped identity passed to every service call."""

import uuid
from dataclasses import dataclass

from app.core.errors import PermissionDenied
from app.models.enums import Role
from app.modules.permissions import Permission, has_permission


@dataclass(frozen=True)
class TenantContext:
    """An authenticated user acting inside one organization (the tenant boundary)."""

    organization_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    role: Role
    request_id: str | None = None
    ip_address: str | None = None

    def can(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDenied(permission=permission.value)


@dataclass(frozen=True)
class SystemContext:
    """Background work (pipeline, email ingestion) acting inside one organization."""

    organization_id: uuid.UUID
    label: str = "system"
    request_id: str | None = None
