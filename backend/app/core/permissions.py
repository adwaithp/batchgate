"""Role-based permissions.

Routes ask for a *permission*, never a role. Roles are just named bundles of permissions,
so changing who can do what is a one-line edit here instead of a hunt through the routes.
"""

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    VIEW_DASHBOARD = "dashboard:view"
    VIEW_ORDERS = "orders:view"
    VIEW_ALL_CUSTOMERS = "customers:view_all"  # without it, only assigned customers
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
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.QC_ANALYST: frozenset(_ANALYST),
    Role.QC_MANAGER: frozenset(
        _ANALYST
        | {
            Permission.EDIT_SPECS,
            Permission.APPROVE_RELEASE,
            Permission.REJECT_BATCH,
            Permission.VIEW_AUDIT_LOG,
        }
    ),
    Role.SALES: frozenset(
        {Permission.VIEW_DASHBOARD, Permission.VIEW_ORDERS, Permission.VIEW_SPECS}
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
    return ROLE_PERMISSIONS.get(role, frozenset())
