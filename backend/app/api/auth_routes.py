from fastapi import APIRouter, HTTPException, Depends, Request
from app.database import users_col
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    require_role,
    check_login_rate_limit,
    record_failed_login,
    reset_login_attempts,
)
from app.models.schemas import UserCreate, UserLogin, Token, UserRole

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token)
async def register(user: UserCreate, _admin=Depends(require_role(UserRole.ADMIN))):
    """Only an existing admin can create new users (except the bootstrap admin, see seed script)."""
    existing = await users_col.find_one({"username": user.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    doc = {
        "username": user.username,
        "password_hash": hash_password(user.password),
        "role": user.role.value,
    }
    await users_col.insert_one(doc)
    token = create_access_token(user.username, user.role.value)
    return Token(access_token=token, role=user.role)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{credentials.username}"

    # Check rate limit before executing password verification
    check_login_rate_limit(rate_key)

    user = await users_col.find_one({"username": credentials.username})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        failed_count = record_failed_login(rate_key)
        remaining = max(5 - failed_count, 0)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid username or password. {remaining} attempt(s) remaining before temporary lockout.",
        )

    # Successful login: reset failed attempts
    reset_login_attempts(rate_key)
    token = create_access_token(user["username"], user["role"])
    return Token(access_token=token, role=UserRole(user["role"]))

