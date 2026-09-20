"""BFF 登录状态：随机 opaque Cookie 仅存 hash，后台 Run 与浏览器 logout 分离。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update

from ..db import schema as s
from ..db.engine import Database
from ..platform_errors import PlatformError
from ..platform_settings import PlatformSettings
from ..policy.repository import current_facts, db_now
from .principal import Principal


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_token(session_token: str) -> str:
    return hmac.new(session_token.encode("utf-8"), b"aio-browser-csrf-v1", hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class LoginStart:
    state: str
    binding: str
    nonce: str
    challenge: str


@dataclass(frozen=True)
class LoginAttempt:
    org_id: UUID
    code_verifier: str
    nonce_hash: str


class AuthService:
    def __init__(self, database: Database, settings: PlatformSettings):
        self.database, self.settings = database, settings

    def begin_login(self, org_id: UUID) -> LoginStart:
        state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        )
        with self.database.bootstrap() as c:
            now = db_now(c)
            c.execute(
                insert(s.login_attempts).values(
                    state_hash=token_hash(state),
                    binding_hash=token_hash(binding),
                    org_id=org_id,
                    nonce_hash=token_hash(nonce),
                    code_verifier=verifier,
                    expires_at=now + timedelta(seconds=self.settings.login_ttl_seconds),
                )
            )
        return LoginStart(state, binding, nonce, challenge)

    def consume_login(self, state: str, binding: str) -> LoginAttempt:
        if not 32 <= len(state) <= 128 or not 32 <= len(binding) <= 128:
            raise PlatformError("LOGIN_INVALID", "Login request is invalid or expired", 401)
        with self.database.bootstrap() as c:
            now = db_now(c)
            row = (
                c.execute(
                    select(s.login_attempts).where(s.login_attempts.c.state_hash == token_hash(state)).with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None or row["consumed_at"] is not None or row["expires_at"] <= now:
                raise PlatformError("LOGIN_INVALID", "Login request is invalid or expired", 401)
            if not hmac.compare_digest(row["binding_hash"], token_hash(binding)):
                raise PlatformError("LOGIN_INVALID", "Login request is invalid or expired", 401)
            c.execute(
                update(s.login_attempts)
                .where(s.login_attempts.c.state_hash == row["state_hash"])
                .values(consumed_at=now, code_verifier="")
            )
            return LoginAttempt(row["org_id"], row["code_verifier"], row["nonce_hash"])

    def create_session(self, org_id: UUID, issuer: str, subject: str) -> tuple[str, Principal]:
        # Users and memberships are provisioned by administrators, never from untrusted login claims.
        with self.database.bootstrap() as c:
            user = (
                c.execute(
                    select(s.users).where(
                        s.users.c.issuer == issuer, s.users.c.subject == subject, s.users.c.active.is_(True)
                    )
                )
                .mappings()
                .first()
            )
        if user is None:
            raise PlatformError("ACCOUNT_NOT_PROVISIONED", "Account is not enabled for this organization", 403)
        with self.database.scoped(org_id, user["id"]) as c:
            member = (
                c.execute(
                    select(s.memberships).where(s.memberships.c.org_id == org_id, s.memberships.c.user_id == user["id"])
                )
                .mappings()
                .first()
            )
            if member is None or not member["active"]:
                raise PlatformError("ACCOUNT_NOT_PROVISIONED", "Account is not enabled for this organization", 403)
            session_id = uuid4()
            principal = Principal(org_id, user["id"], member["revision"], session_id)
            current_facts(c, principal, lock=True)
            token = secrets.token_urlsafe(32)
            c.execute(
                insert(s.auth_sessions).values(
                    id=session_id,
                    token_hash=token_hash(token),
                    org_id=org_id,
                    user_id=user["id"],
                    expires_at=db_now(c) + timedelta(seconds=self.settings.session_ttl_seconds),
                )
            )
        return token, principal

    def authenticate(self, raw_token: str | None) -> Principal:
        if not raw_token or not 32 <= len(raw_token) <= 128:
            raise PlatformError("AUTH_REQUIRED", "Authentication is required", 401)
        with self.database.bootstrap() as c:
            row = (
                c.execute(
                    select(s.auth_sessions).where(
                        s.auth_sessions.c.token_hash == token_hash(raw_token),
                        s.auth_sessions.c.revoked_at.is_(None),
                        s.auth_sessions.c.expires_at > db_now(c),
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise PlatformError("AUTH_REQUIRED", "Authentication is required", 401)
        with self.database.scoped(row["org_id"], row["user_id"]) as c:
            member = (
                c.execute(
                    select(s.memberships).where(
                        s.memberships.c.org_id == row["org_id"], s.memberships.c.user_id == row["user_id"]
                    )
                )
                .mappings()
                .first()
            )
            if member is None:
                raise PlatformError("AUTH_REQUIRED", "Authentication is required", 401)
            principal = Principal(row["org_id"], row["user_id"], member["revision"], row["id"])
            current_facts(c, principal)
        return principal

    def logout(self, principal: Principal) -> None:
        with self.database.transaction(principal) as c:
            c.execute(
                update(s.auth_sessions)
                .where(
                    s.auth_sessions.c.id == principal.auth_session_id,
                    s.auth_sessions.c.user_id == principal.user_id,
                    s.auth_sessions.c.org_id == principal.org_id,
                )
                .values(revoked_at=db_now(c))
            )
