"""Role-based permissions. Routes check permissions, never role names."""

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    """An action a user may be allowed to take."""

    VIEW_DASHBOARD = "dashboard:view"
    VIEW_ORDERS = "orders:view"
    EDIT_ORDERS = "orders:edit"
    VIEW_ALL_CUSTOMERS = "customers:view_all"  # without it, only assigned customers
    ADD_CUSTOMERS = "customers:add"
    VIEW_SPECS = "specs:view"
    EDIT_SPECS = "specs:edit"
    VIEW_BATCHES = "batches:view"
    UPLOAD_COA = "coa:upload"
    RUN_CHECK = "check:run"
    PROPOSE_RELEASE = "batch:propose_release"
    APPROVE_RELEASE = "batch:approve_release"
    HOLD_BATCH = "batch:hold"
    REJECT_BATCH = "batch:reject"
    VIEW_AUDIT_LOG = "audit:view"
    VIEW_KNOWLEDGE = "knowledge:view"
    EDIT_KNOWLEDGE = "knowledge:edit"
    MANAGE_USERS = "users:manage"


_ANALYST = {
    Permission.VIEW_DASHBOARD,
    Permission.VIEW_ORDERS,
    Permission.VIEW_ALL_CUSTOMERS,
    Permission.VIEW_SPECS,
    Permission.VIEW_BATCHES,
    Permission.UPLOAD_COA,
    Permission.RUN_CHECK,
    Permission.PROPOSE_RELEASE,
    Permission.HOLD_BATCH,
    Permission.VIEW_KNOWLEDGE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.QC_ANALYST: frozenset(_ANALYST),
    Role.QC_MANAGER: frozenset(
        _ANALYST
        | {
            Permission.EDIT_SPECS,
            Permission.EDIT_ORDERS,
            Permission.ADD_CUSTOMERS,
            Permission.APPROVE_RELEASE,
            Permission.REJECT_BATCH,
            Permission.VIEW_AUDIT_LOG,
            Permission.EDIT_KNOWLEDGE,
        }
    ),
    # Sales enter their customers' orders but cannot change quality rules.
    Role.SALES: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_ORDERS,
            Permission.EDIT_ORDERS,
            Permission.ADD_CUSTOMERS,
            Permission.VIEW_SPECS,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}

ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Admin",
    Role.QC_MANAGER: "QC Manager",
    Role.QC_ANALYST: "QC Analyst",
    Role.SALES: "Sales / Account Manager",
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """Return the permissions granted to `role`."""
    return ROLE_PERMISSIONS.get(role, frozenset())
