"""Password hashing and JWT access tokens."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Return True when `password` matches the bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """Create a signed access token for a user id."""
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Return the user id from a valid token, or None."""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
