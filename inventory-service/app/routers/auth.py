import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from smart_shared import auth
from smart_shared.config import require

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("inventory-service.auth")

USERS = auth.parse_users(require("AUTH_USERS"))


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    role: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    principal = auth.authenticate(USERS, body.username, body.password)
    if principal is None:
        # Usernames are not logged, to keep failed-login logs free of personal data.
        logger.info("login failed")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, ttl = auth.issue_token(principal)
    return TokenOut(access_token=token, expires_in=ttl, username=principal.subject, role=principal.role)


@router.get("/me")
def me(principal: auth.Principal = Depends(auth.authorize(*auth.READ_ROLES))):
    return {"username": principal.subject, "role": principal.role}
