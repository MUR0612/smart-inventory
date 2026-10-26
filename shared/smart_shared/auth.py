"""Minimal, course-sized access control.

* Users log in once (inventory-service ``/api/auth/login``) and receive a
  short-lived HS256 JWT signed with ``AUTH_SECRET``. Both services verify it.
* Two roles: ``viewer`` (read only) and ``staff`` (read + write).
* Service-to-service calls (order-service -> inventory-service) use a
  separate shared ``SERVICE_TOKEN`` in the ``X-Service-Token`` header. The
  gateway strips that header from browser requests.

This is not a full IAM system: there is no user database, no token
revocation list and no MFA. See docs/SECURITY.md for the limits.
"""
import hmac
import time
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request

from .config import ConfigError, optional, require
from .passwords import hash_password, verify_password  # noqa: F401 (re-exported)

VIEWER = "viewer"
STAFF = "staff"
SERVICE = "service"
READ_ROLES = (VIEWER, STAFF)
WRITE_ROLES = (STAFF,)

_ISSUER = "smart-inventory"
_AUDIENCE = "smart-inventory-web"
# Used when the username is unknown so failed logins take similar time.
_DUMMY_HASH = hash_password("not-a-real-password", salt=b"\x00" * 16)


def parse_users(raw: str) -> dict[str, tuple[str, str]]:
    """``AUTH_USERS="alice:staff:<hash>,bob:viewer:<hash>"`` -> {name: (role, hash)}."""
    users = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        parts = entry.split(":")
        if len(parts) != 3 or parts[1] not in READ_ROLES or not parts[2].startswith("pbkdf2_sha256."):
            raise ConfigError("AUTH_USERS entries must look like username:role:pbkdf2_sha256.<...>")
        users[parts[0]] = (parts[1], parts[2])
    return users


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


class AuthSettings:
    def __init__(self):
        self.secret = require("AUTH_SECRET", min_length=32)
        self.service_token = require("SERVICE_TOKEN", min_length=24)
        self.token_ttl = int(optional("AUTH_TOKEN_TTL_SECONDS", "28800"))


_settings: AuthSettings | None = None


def settings() -> AuthSettings:
    global _settings
    if _settings is None:
        _settings = AuthSettings()
    return _settings


def reset_settings_for_tests():
    global _settings
    _settings = None


def authenticate(users: dict[str, tuple[str, str]], username: str, password: str) -> Principal | None:
    role, encoded = users.get(username, (None, _DUMMY_HASH))
    if verify_password(password, encoded) and role:
        return Principal(username, role)
    return None


def issue_token(principal: Principal) -> tuple[str, int]:
    s = settings()
    now = int(time.time())
    claims = {"sub": principal.subject, "role": principal.role, "iat": now,
              "exp": now + s.token_ttl, "iss": _ISSUER, "aud": _AUDIENCE}
    return jwt.encode(claims, s.secret, algorithm="HS256"), s.token_ttl


def _unauthorized(detail: str = "Not authenticated"):
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def decode_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, settings().secret, algorithms=["HS256"], audience=_AUDIENCE,
                            issuer=_ISSUER, options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired token")
    if claims["role"] not in READ_ROLES:
        raise _unauthorized("Invalid or expired token")
    return Principal(claims["sub"], claims["role"])


def authorize(*roles: str, allow_service: bool = False):
    """FastAPI dependency: accept a user with one of ``roles`` (and optionally the service token)."""

    def dependency(request: Request) -> Principal:
        service_token = request.headers.get("X-Service-Token")
        if service_token is not None:
            if not hmac.compare_digest(service_token.encode(), settings().service_token.encode()):
                raise _unauthorized("Invalid service token")
            if not allow_service:
                raise HTTPException(status_code=403, detail="Service token not accepted for this endpoint")
            return Principal("order-service", SERVICE)

        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized()
        principal = decode_token(token)
        if principal.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return principal

    return dependency
