"""Encrypted OAuth grants and one-shot exchange/refresh journal in the gateway only."""

import base64
import hashlib
import hmac
import secrets
import time

import rfc8785

from .contracts import GatewayError, digest, strict_json


class OAuthStore:
    def __init__(self, vault):
        self.vault = vault
        with vault.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS oauth_flows(
                    flow_id TEXT PRIMARY KEY, credential_ref TEXT NOT NULL, binding BLOB NOT NULL,
                    request_digest TEXT NOT NULL, state_hash TEXT NOT NULL, state TEXT NOT NULL,
                    ciphertext BLOB, code_hash TEXT, expires_at REAL NOT NULL, error_code TEXT,
                    FOREIGN KEY(credential_ref) REFERENCES credentials(credential_ref)
                );
                CREATE TABLE IF NOT EXISTS oauth_grants(
                    credential_ref TEXT PRIMARY KEY, generation INTEGER NOT NULL, state TEXT NOT NULL,
                    expires_at REAL NOT NULL DEFAULT 0, error_code TEXT, remote_revocation TEXT,
                    FOREIGN KEY(credential_ref) REFERENCES credentials(credential_ref)
                );
            """)
            # A lost code/rotating refresh response is not permission to resend it after a restart.
            c.execute(
                "UPDATE oauth_grants SET state='reauth_required',error_code='OAUTH_EXCHANGE_UNKNOWN' WHERE credential_ref IN (SELECT credential_ref FROM oauth_flows WHERE state='exchanging')"
            )
            c.execute(
                "UPDATE oauth_grants SET state='reauth_required',error_code='OAUTH_REFRESH_UNKNOWN' WHERE state='refreshing'"
            )
            c.execute(
                "UPDATE credentials SET active=0 WHERE credential_ref IN (SELECT credential_ref FROM oauth_grants WHERE state='reauth_required')"
            )
            c.execute(
                "UPDATE oauth_flows SET state='failed',ciphertext=NULL,error_code='OAUTH_EXCHANGE_UNKNOWN' WHERE state='exchanging'"
            )
            c.execute(
                "UPDATE oauth_flows SET state='failed',ciphertext=NULL,error_code='OAUTH_FLOW_EXPIRED' WHERE expires_at<=? AND state IN ('preparing','authorizing')",
                (time.time(),),
            )

    @staticmethod
    def aad(binding):
        return b"aio-oauth-grant-v1\0" + binding.aad()

    @staticmethod
    def flow_aad(request):
        return b"aio-oauth-flow-v1\0" + request.binding.aad() + str(request.flow_id).encode("ascii")

    @staticmethod
    def request_digest(request):
        value = request.model_dump(mode="json", include={"binding", "flow_id", "ticket_id", "not_after"})
        return digest("aio-oauth-intent-v1", value)

    def _row(self, c, binding):
        row = c.execute(
            "SELECT c.*,g.generation,g.state,g.expires_at,g.error_code,g.remote_revocation FROM credentials c JOIN oauth_grants g USING(credential_ref) WHERE credential_ref=?",
            (str(binding.credential_ref),),
        ).fetchone()
        if row is None or row["kind"] != "oauth" or row["binding"] != binding.aad():
            raise GatewayError("CREDENTIAL_UNAVAILABLE", 403, not_sent=True)
        return row

    def _data(self, row, binding):
        if not row["ciphertext"]:
            return {}
        value = strict_json(self.vault._open(row["ciphertext"], self.aad(binding)), 131072)
        if not isinstance(value, dict):
            raise GatewayError("CREDENTIAL_INTEGRITY_ERROR", 503, not_sent=True)
        return value

    def _write(self, c, binding, value):
        raw = rfc8785.dumps(value)
        if len(raw) > 131072:
            raise GatewayError("OAUTH_CREDENTIAL_QUOTA", 429, not_sent=True)
        self.vault._quota(c, len(raw) + 64)
        encrypted = self.vault._seal(raw, self.aad(binding))
        fingerprint = hmac.digest(self.vault._key, self.aad(binding) + b"\0" + raw, "sha256")
        c.execute(
            "UPDATE credentials SET ciphertext=?,fingerprint=? WHERE credential_ref=?",
            (encrypted, fingerprint, str(binding.credential_ref)),
        )

    def is_oauth(self, binding):
        with self.vault.connect() as c:
            row = c.execute(
                "SELECT kind,binding FROM credentials WHERE credential_ref=?", (str(binding.credential_ref),)
            ).fetchone()
            if row and row["binding"] != binding.aad():
                raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True)
            return bool(row and row["kind"] == "oauth")

    def prepare(self, request):
        binding = request.binding
        with self.vault.connect() as c:
            row = c.execute("SELECT * FROM oauth_flows WHERE flow_id=?", (str(request.flow_id),)).fetchone()
            if row:
                if row["binding"] != binding.aad() or row["request_digest"] != self.request_digest(request):
                    raise GatewayError("OAUTH_FLOW_CONFLICT", 409, not_sent=True)
                if (
                    row["expires_at"] <= time.time()
                    or row["state"] not in {"preparing", "authorizing"}
                    or not row["ciphertext"]
                ):
                    raise GatewayError("OAUTH_FLOW_USED", 409, not_sent=True)
                return strict_json(self.vault._open(row["ciphertext"], self.flow_aad(request)), 16384)
            if request.not_after.timestamp() <= time.time() or request.not_after.timestamp() > time.time() + 605:
                raise GatewayError("OAUTH_FLOW_EXPIRED", 409, not_sent=True)
            credential = c.execute(
                "SELECT * FROM credentials WHERE credential_ref=?", (str(binding.credential_ref),)
            ).fetchone()
            if credential:
                raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True)
            if (
                c.execute("SELECT count(*) FROM oauth_flows").fetchone()[0] >= 20000
                or c.execute("SELECT count(*) FROM credentials").fetchone()[0] >= 10000
            ):
                raise GatewayError("CONNECTOR_STORAGE_QUOTA", 429, not_sent=True)
            verifier, state, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            data = {
                "verifier": verifier,
                "state": state,
                "nonce": nonce,
                "challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
                .rstrip(b"=")
                .decode("ascii"),
            }
            raw = rfc8785.dumps(data)
            self.vault._quota(c, len(raw) + 1024)
            c.execute(
                "INSERT INTO credentials(credential_ref,org_id,connection_id,revision,binding,fingerprint,ciphertext,active,kind) VALUES (?,?,?,?,?,x'',x'',1,'oauth')",
                (
                    str(binding.credential_ref),
                    str(binding.org_id),
                    str(binding.connection_id),
                    binding.credential_revision,
                    binding.aad(),
                ),
            )
            c.execute(
                "INSERT INTO oauth_grants(credential_ref,generation,state) VALUES (?,0,'pending')",
                (str(binding.credential_ref),),
            )
            c.execute(
                "INSERT INTO oauth_flows(flow_id,credential_ref,binding,request_digest,state_hash,state,ciphertext,expires_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(request.flow_id),
                    str(binding.credential_ref),
                    binding.aad(),
                    self.request_digest(request),
                    digest("aio-oauth-state-v1", state),
                    "preparing",
                    self.vault._seal(raw, self.flow_aad(request)),
                    request.not_after.timestamp(),
                ),
            )
            return data

    def authorizing(self, request):
        with self.vault.connect() as c:
            row = self._row(c, request.binding)
            if not row["active"] or row["state"] != "pending":
                raise GatewayError("OAUTH_REVOKED", 403, not_sent=True)
            changed = c.execute(
                "UPDATE oauth_flows SET state='authorizing' WHERE flow_id=? AND state IN ('preparing','authorizing') AND expires_at>?",
                (str(request.flow_id), time.time()),
            ).rowcount
            if not changed:
                raise GatewayError("OAUTH_FLOW_EXPIRED", 409, not_sent=True)

    def exchange(self, request):
        with self.vault.connect() as c:
            row = c.execute("SELECT * FROM oauth_flows WHERE flow_id=?", (str(request.flow_id),)).fetchone()
            code_hash = request.authority()["code_hash"]
            if (
                row is None
                or row["binding"] != request.binding.aad()
                or row["request_digest"] != self.request_digest(request)
                or row["state_hash"] != request.authority()["state_hash"]
            ):
                raise GatewayError("OAUTH_STATE_MISMATCH", 403, not_sent=True)
            credential = self._row(c, request.binding)
            if row["state"] == "completed" and row["code_hash"] == code_hash and credential["active"]:
                return None
            if row["state"] != "authorizing" or row["expires_at"] <= time.time() or not credential["active"]:
                raise GatewayError("OAUTH_FLOW_USED", 409, not_sent=True)
            data = strict_json(self.vault._open(row["ciphertext"], self.flow_aad(request)), 16384)
            c.execute(
                "UPDATE oauth_flows SET state='exchanging',code_hash=?,ciphertext=NULL WHERE flow_id=?",
                (code_hash, str(request.flow_id)),
            )
            return data

    def complete(self, request, tokens):
        with self.vault.connect() as c:
            row = self._row(c, request.binding)
            if not row["active"] or row["state"] != "pending":
                if row["state"] != "revoked":
                    self._remember(c, request.binding, tokens)
                return False
            flow = c.execute(
                "SELECT state,code_hash FROM oauth_flows WHERE flow_id=?", (str(request.flow_id),)
            ).fetchone()
            if flow["state"] != "exchanging" or flow["code_hash"] != request.authority()["code_hash"]:
                raise GatewayError("OAUTH_FLOW_CONFLICT", 409, not_sent=True)
            self._write(c, request.binding, tokens)
            c.execute(
                "UPDATE oauth_grants SET state='ready',generation=1,expires_at=? WHERE credential_ref=?",
                (tokens["expires_at"], str(request.binding.credential_ref)),
            )
            c.execute(
                "UPDATE oauth_flows SET state='completed',ciphertext=NULL WHERE flow_id=?", (str(request.flow_id),)
            )
            return True

    def current(self, binding, *, inactive=False):
        with self.vault.connect() as c:
            row = self._row(c, binding)
            if not inactive and (not row["active"] or row["state"] != "ready"):
                raise GatewayError("OAUTH_REAUTH_REQUIRED", 401, not_sent=True)
            return dict(row), self._data(row, binding)

    def metadata(self, binding):
        row, data = self.current(binding)
        return {
            "credential_ref": str(binding.credential_ref),
            "state": "stored",
            "authentication": "oauth2",
            "expires_at": row["expires_at"],
            "scopes": data["scopes"],
            "external_identity": {"issuer": data["issuer"], "subject": data.get("subject")},
        }

    def refreshing(self, binding, generation):
        with self.vault.connect() as c:
            row = self._row(c, binding)
            if not row["active"] or row["state"] != "ready" or row["generation"] != generation:
                raise GatewayError("OAUTH_REFRESH_CONFLICT", 409, not_sent=True)
            c.execute(
                "UPDATE oauth_grants SET state='refreshing' WHERE credential_ref=?", (str(binding.credential_ref),)
            )

    def refreshed(self, binding, generation, tokens):
        with self.vault.connect() as c:
            row = self._row(c, binding)
            if not row["active"] or row["state"] != "refreshing" or row["generation"] != generation:
                if row["state"] != "revoked":
                    self._remember(c, binding, tokens)
                return False
            old = self._data(row, binding)
            retired = [item for item in old.get("retire_tokens", []) if item.get("until", 0) > time.time()]
            if old.get("access_token") and old.get("expires_at", 0) > time.time():
                retired.append({"token": old["access_token"], "hint": "access_token", "until": old["expires_at"]})
            tokens["retire_tokens"] = retired
            self._write(c, binding, tokens)
            c.execute(
                "UPDATE oauth_grants SET state='ready',generation=generation+1,expires_at=?,error_code=NULL WHERE credential_ref=?",
                (tokens["expires_at"], str(binding.credential_ref)),
            )
            return True

    def _remember(self, c, binding, tokens=None, unknown=False):
        row = self._row(c, binding)
        data = self._data(row, binding)
        retired = list(data.get("retire_tokens", []))
        for source in (tokens or {},):
            for key in ("access_token", "refresh_token"):
                token = source.get(key)
                if (
                    isinstance(token, str)
                    and 16 <= len(token) <= 8192
                    and token.isascii()
                    and all(33 <= ord(ch) <= 126 for ch in token)
                ):
                    retired.append({"token": token, "hint": key})
        unique = {(item["token"], item["hint"]) for item in retired}
        if len(unique) > 8:
            raise GatewayError("OAUTH_CREDENTIAL_QUOTA", 429, not_sent=True)
        data["retire_tokens"] = [{"token": token, "hint": hint} for token, hint in sorted(unique)]
        data["unknown_issuance"] = bool(data.get("unknown_issuance") or unknown)
        self._write(c, binding, data)

    def fail(self, binding, code, *, tokens=None, unknown=False, flow_id=None):
        with self.vault.connect() as c:
            if self._row(c, binding)["state"] == "revoked":
                return
            c.execute("UPDATE credentials SET active=0 WHERE credential_ref=?", (str(binding.credential_ref),))
            try:
                self._remember(c, binding, tokens, unknown)
            except GatewayError:
                code = "OAUTH_CLEANUP_UNCERTAIN"
                c.execute(
                    "UPDATE oauth_grants SET remote_revocation='unknown' WHERE credential_ref=?",
                    (str(binding.credential_ref),),
                )
            c.execute(
                "UPDATE oauth_grants SET state=CASE WHEN state IN ('revoking','revoked') THEN state ELSE 'reauth_required' END,error_code=? WHERE credential_ref=?",
                (code, str(binding.credential_ref)),
            )
            if flow_id:
                c.execute(
                    "UPDATE oauth_flows SET state='failed',error_code=?,ciphertext=NULL WHERE flow_id=? AND state!='completed'",
                    (code, str(flow_id)),
                )

    def disable(self, binding):
        with self.vault.connect() as c:
            row = self._row(c, binding)
            exchanging = c.execute(
                "SELECT 1 FROM oauth_flows WHERE credential_ref=? AND state='exchanging'",
                (str(binding.credential_ref),),
            ).fetchone()
            if row["state"] == "refreshing" or exchanging:
                c.execute(
                    "UPDATE oauth_grants SET remote_revocation='unknown' WHERE credential_ref=?",
                    (str(binding.credential_ref),),
                )
            c.execute("UPDATE credentials SET active=0 WHERE credential_ref=?", (str(binding.credential_ref),))
            c.execute(
                "UPDATE oauth_flows SET state='revoked',ciphertext=NULL WHERE credential_ref=? AND state!='completed'",
                (str(binding.credential_ref),),
            )
            if row["state"] != "revoked":
                c.execute(
                    "UPDATE oauth_grants SET state='revoking' WHERE credential_ref=?", (str(binding.credential_ref),)
                )

    def revoked(self, binding, remote):
        with self.vault.connect() as c:
            self._row(c, binding)
            c.execute(
                "UPDATE credentials SET active=0,ciphertext=x'',fingerprint=x'' WHERE credential_ref=?",
                (str(binding.credential_ref),),
            )
            c.execute(
                "UPDATE oauth_grants SET state='revoked',remote_revocation=? WHERE credential_ref=?",
                (remote, str(binding.credential_ref)),
            )
        return {"credential_ref": str(binding.credential_ref), "state": "revoked", "remote_revocation": remote}
