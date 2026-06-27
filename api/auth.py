"""Authentication helpers for the recipe service.

Two-tier auth:
- API-key  : X-API-Key header   → verified against API_KEY_VALID env var
- JWT      : Authorization: Bearer <token> → verified with JWT_SECRET env var

Both schemes use auto_error=False so a missing header returns None instead
of a 403, allowing the OR-logic dependency to raise 401 explicitly.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Scheme declarations — auto_error=False so missing header → None (not 403)
# ---------------------------------------------------------------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Dev user fixture — one hardcoded user for the stretch
# ---------------------------------------------------------------------------
# Password is "secret" — hashed with bcrypt
_DEV_USER = {
    "username": "admin",
    "hashed_password": pwd_context.hash("admin"),
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> dict | None:
    """Return the user dict if credentials are valid, else None."""
    if username != _DEV_USER["username"]:
        return None
    if not verify_password(password, _DEV_USER["hashed_password"]):
        return None
    return {"username": username}


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(subject: str, expires_minutes: int = 60) -> str:
    """Issue a signed JWT with an exp claim."""
    secret = os.environ.get("JWT_SECRET", "")
    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, secret, algorithm=algorithm)


# ---------------------------------------------------------------------------
# Credential verifiers
# ---------------------------------------------------------------------------

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify the X-API-Key header against API_KEY_VALID env var.

    Returns the key on success; raises 401 if missing or invalid.
    """
    valid_key = os.environ.get("API_KEY_VALID", "")
    if not api_key or api_key != valid_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


def verify_jwt(token: str = Depends(oauth2_scheme)) -> dict:
    """Verify the JWT bearer token.

    Returns the decoded payload on success; raises 401 if missing,
    invalid, or expired.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    secret = os.environ.get("JWT_SECRET", "")
    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_api_key_or_jwt(
    api_key: str = Security(api_key_header),
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Accept either a valid API key OR a valid JWT.

    Raises 401 if neither credential is present or valid.
    Returns {"type": "api_key"} or the decoded JWT payload.
    """
    valid_key = os.environ.get("API_KEY_VALID", "")
    # Try API key first
    if api_key and api_key == valid_key:
        return {"type": "api_key"}
    # Try JWT
    if token:
        secret = os.environ.get("JWT_SECRET", "")
        algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        try:
            payload = jwt.decode(token, secret, algorithms=[algorithm])
            return payload
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    raise HTTPException(status_code=401, detail="Missing credentials")