"""Authentication API: access tokens, the current user and demo accounts."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.permissions import ROLE_LABELS, permissions_for
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.auth import DemoAccount, DemoAccounts, Token, UserOut
from app.seed import DEMO_USERS
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def to_user_out(user: User) -> UserOut:
    """Build the API view of a user, including their permissions."""
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        role_label=ROLE_LABELS[user.role],
        permissions=sorted(permissions_for(user.role)),
        customers=user.customers,
    )


@router.post("/token", response_model=Token)
def login(db: DbSession, form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    """Issue an access token (OAuth2 password flow; the username is the email)."""
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(user.id, user.role.value)
    audit.record(db, actor=user, action="login", entity_type="user", entity_id=user.id)
    db.commit()
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Return the signed-in user."""
    return to_user_out(user)


@router.get("/demo-accounts", response_model=DemoAccounts)
def demo_accounts(db: DbSession) -> DemoAccounts:
    """List the one-click demo accounts (disabled outside demo mode)."""
    settings = get_settings()
    if not settings.demo_mode:
        return DemoAccounts(enabled=False)

    emails = [u["email"] for u in DEMO_USERS]
    users = {u.email: u for u in db.scalars(select(User).where(User.email.in_(emails)))}
    accounts = [
        DemoAccount(
            email=spec["email"],
            full_name=users[spec["email"]].full_name,
            role=users[spec["email"]].role,
            role_label=ROLE_LABELS[users[spec["email"]].role],
            description=spec["description"],
        )
        for spec in DEMO_USERS
        if spec["email"] in users
    ]
    return DemoAccounts(enabled=True, password=settings.demo_password, accounts=accounts)
