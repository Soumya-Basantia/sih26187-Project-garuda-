"""
Authentication: password hashing (bcrypt), JWT issuance/validation,
and role-based dependency guards for FastAPI routes.
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings
from app.models.schemas import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    return {"username": payload["sub"], "role": payload["role"]}


def require_role(*allowed_roles: UserRole):
    """Usage: Depends(require_role(UserRole.ADMIN))"""
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in [r.value for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return user
    return checker


def verify_token_string(token: Optional[str]) -> dict:
    """Verifies JWT passed via WebSocket URL query or media streaming query."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required via query parameter",
        )
    return decode_token(token)


import time
from collections import defaultdict

# IP / Username sliding-window rate limiter: max 5 failed attempts per 60s
_failed_attempts: dict = defaultdict(list)


def check_login_rate_limit(identifier: str, max_attempts: int = 5, window_seconds: int = 60):
    """Raises HTTP 429 if too many failed attempts within window."""
    now = time.time()
    _failed_attempts[identifier] = [t for t in _failed_attempts[identifier] if now - t < window_seconds]
    if len(_failed_attempts[identifier]) >= max_attempts:
        retry_after = int(window_seconds - (now - _failed_attempts[identifier][0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Security Alert: Excessive failed authentication attempts. Locked out for {max(retry_after, 5)} seconds.",
            headers={"Retry-After": str(max(retry_after, 5))},
        )


def record_failed_login(identifier: str) -> int:
    """Records a failed attempt and returns count in window."""
    now = time.time()
    _failed_attempts[identifier] = [t for t in _failed_attempts[identifier] if now - t < 60]
    _failed_attempts[identifier].append(now)
    return len(_failed_attempts[identifier])


def reset_login_attempts(identifier: str):
    """Clears failed attempts on successful authentication."""
    _failed_attempts.pop(identifier, None)

