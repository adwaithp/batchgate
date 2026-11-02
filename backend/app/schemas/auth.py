from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CustomerRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role
    role_label: str
    permissions: list[str]
    customers: list[CustomerRef]


class DemoAccount(BaseModel):
    email: EmailStr
    full_name: str
    role: Role
    role_label: str
    description: str


class DemoAccounts(BaseModel):
    enabled: bool
    password: str | None = None
    accounts: list[DemoAccount] = []
