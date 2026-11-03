"""Authentication schemas."""

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import Role
from app.schemas.common import Ref


class Token(BaseModel):
    """An access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    """The signed-in user with permissions and assigned customers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role
    role_label: str
    permissions: list[str]
    customers: list[Ref]


class DemoAccount(BaseModel):
    """A one-click demo login."""

    email: EmailStr
    full_name: str
    role: Role
    role_label: str
    description: str


class DemoAccounts(BaseModel):
    """Demo logins shown on the sign-in page."""

    enabled: bool
    password: str | None = None
    accounts: list[DemoAccount] = []
