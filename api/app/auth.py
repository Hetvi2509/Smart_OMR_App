"""Password hashing and bearer-token auth."""
from __future__ import annotations

import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

_bearer = HTTPBearer(auto_error=False)

# Every request resolves its bearer token to a user row, which used to cost
# its own ~1s round-trip to Neon before the endpoint's own queries even
# started -- on a request that is itself one query, this lookup was half the
# total latency. The resolved user is cached briefly per token; a change to
# the account (institution, name, deletion) becomes visible within this
# window, which is an acceptable trade for cutting a request's fixed cost
# roughly in half.
_USER_CACHE_TTL = 15.0
_user_cache: dict[str, tuple[float, dict]] = {}
# bcrypt silently truncates at 72 bytes, so a longer password would make
# everything past byte 72 irrelevant.  Reject instead of quietly ignoring it.
MAX_PASSWORD_BYTES = 72


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed hash in the row must read as "wrong password", never as
        # an exception that leaks a 500 on the login path.
        return False


def make_token(user_id: int) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "iat": now,
                       "exp": now + config.JWT_TTL_SECONDS},
                      config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Resolve the bearer token to a user row, or 401."""
    if cred is None or not cred.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    try:
        payload = jwt.decode(cred.credentials, config.JWT_SECRET,
                             algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session.")

    token = cred.credentials
    cached = _user_cache.get(token)
    now = time.time()
    if cached is not None and now - cached[0] < _USER_CACHE_TTL:
        return cached[1]

    user = db.one(
        "SELECT u.id, u.email, u.full_name, u.role, u.institution_id,"
        " i.name AS institution_name"
        " FROM users u LEFT JOIN institutions i ON i.id = u.institution_id"
        " WHERE u.id = %s", (int(payload["sub"]),))
    if user is None:
        # Token validly signed but the account is gone.
        _user_cache.pop(token, None)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found.")

    _user_cache[token] = (now, user)
    # Unbounded growth is bounded in practice (one entry per active session,
    # evicted after _USER_CACHE_TTL), but a very long-lived process with many
    # distinct tokens should not accumulate forever.
    if len(_user_cache) > 10_000:
        _user_cache.clear()
    return user
