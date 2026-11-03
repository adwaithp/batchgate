"""FastAPI dependencies: database session, signed-in user and permission checks."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Permission, permissions_for
from app.core.security import decode_access_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

DbSession = Annotated[Session, Depends(get_db)]

_credentials_error = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Return the active user named by the bearer token, or raise 401."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _credentials_error from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(*needed: Permission):
    """Return a dependency that admits only users holding `permission`."""

    def checker(user: CurrentUser) -> User:
        """Raise 403 unless the signed-in user holds the permission."""
        granted = permissions_for(user.role)
        missing = [p for p in needed if p not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {', '.join(missing)}",
            )
        return user

    return checker
