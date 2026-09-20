"""Private encrypted credential/result store and durable effect journal; never a browser data API."""

from contextlib import contextmanager
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import rfc8785

from .contracts import Binding, CallRequest, GatewayError, strict_json


class Vault:
    def __init__(self, root: Path, key: bytes):
        if len(key) != 32:
            raise ValueError("Provide a dedicated 256-bit gateway key from approved secret storage")
        root = Path(root)
        if not root.is_absolute():
            raise ValueError("Credential storage requires an explicit absolute private root")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise ValueError("Credential root cannot be a symbolic link")
        self.root = root.resolve()
        self.path = self.root / "connector.sqlite3"
        if self.path.is_symlink() or (self.root / "connector.lock").is_symlink():
            raise ValueError("Credential state files cannot be symbolic links")
        self._key = key
        self._cipher = AESGCM(key)
        self._owner = (self.root / "connector.lock").open("a+b")
        self._owner.seek(0)
        self._owner.write(b"0")
        self._owner.flush()
        self._owner.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._owner.close()
            raise RuntimeError("Only one gateway may own a credential/effect journal") from None
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS installation(id TEXT PRIMARY KEY, key_check BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS credentials(
                    credential_ref TEXT PRIMARY KEY, org_id TEXT NOT NULL, connection_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, binding BLOB NOT NULL, fingerprint BLOB NOT NULL,
                    ciphertext BLOB NOT NULL, active INTEGER NOT NULL,
                    UNIQUE(org_id,connection_id,revision)
                );
                CREATE TABLE IF NOT EXISTS effects(
                    org_id TEXT NOT NULL, operation_key TEXT NOT NULL, effect_digest TEXT NOT NULL,
                    connection_id TEXT NOT NULL, credential_ref TEXT NOT NULL,
                    state TEXT NOT NULL, result BLOB, error_code TEXT,
                    created_at REAL NOT NULL DEFAULT (unixepoch()), updated_at REAL NOT NULL DEFAULT (unixepoch()),
                    PRIMARY KEY(org_id,operation_key)
                );
            """)
            columns = {row["name"] for row in c.execute("PRAGMA table_info(credentials)")}
            if "kind" not in columns:
                c.execute("ALTER TABLE credentials ADD COLUMN kind TEXT NOT NULL DEFAULT 'opaque'")
            row = c.execute("SELECT * FROM installation").fetchone()
            check = hmac.digest(key, b"aio-connector-vault-key-v1", "sha256")
            if row is None:
                self.installation_id = uuid4().hex
                c.execute("INSERT INTO installation VALUES (?,?)", (self.installation_id, check))
            elif not hmac.compare_digest(row["key_check"], check):
                self._owner.close()
                raise RuntimeError("Configured gateway key does not match this credential store")
            else:
                self.installation_id = row["id"]
            # Before calling there is no business request; once calling, a crash is always uncertain.
            c.execute("UPDATE effects SET state='not_sent',error_code='GATEWAY_RESTARTED' WHERE state='preparing'")
            c.execute("UPDATE effects SET state='unknown',error_code='CONNECTOR_EFFECT_UNKNOWN' WHERE state='calling'")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def _quota(c, extra=0):
        size = c.execute("PRAGMA page_count").fetchone()[0] * c.execute("PRAGMA page_size").fetchone()[0]
        if size + extra > 128 * 1024 * 1024:
            raise GatewayError("CONNECTOR_STORAGE_QUOTA", 429, not_sent=True)

    def _seal(self, data, aad):
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, data, aad)

    def _open(self, value, aad):
        try:
            return self._cipher.decrypt(value[:12], value[12:], aad)
        except Exception:
            raise GatewayError("CREDENTIAL_INTEGRITY_ERROR", 503, not_sent=True) from None

    def put(self, binding: Binding, secret: str):
        raw, aad = secret.encode("utf-8"), binding.aad()
        fingerprint = hmac.digest(self._key, aad + b"\0" + raw, "sha256")
        encrypted = self._seal(raw, aad)
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM credentials WHERE credential_ref=?", (str(binding.credential_ref),)
            ).fetchone()
            if row:
                if (
                    not row["active"]
                    or row["binding"] != aad
                    or not hmac.compare_digest(row["fingerprint"], fingerprint)
                ):
                    raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True)
                return {"credential_ref": str(binding.credential_ref), "state": "stored"}
            self._quota(c, len(encrypted))
            if c.execute("SELECT count(*) FROM credentials").fetchone()[0] >= 10000:
                raise GatewayError("CONNECTOR_STORAGE_QUOTA", 429, not_sent=True)
            try:
                c.execute(
                    "INSERT INTO credentials(credential_ref,org_id,connection_id,revision,binding,fingerprint,ciphertext,active) VALUES (?,?,?,?,?,?,?,1)",
                    (
                        str(binding.credential_ref),
                        str(binding.org_id),
                        str(binding.connection_id),
                        binding.credential_revision,
                        aad,
                        fingerprint,
                        encrypted,
                    ),
                )
            except sqlite3.IntegrityError:
                raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True) from None
        return {"credential_ref": str(binding.credential_ref), "state": "stored"}

    def secret(self, binding: Binding):
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM credentials WHERE credential_ref=?", (str(binding.credential_ref),)
            ).fetchone()
        if row is None or not row["active"] or row["binding"] != binding.aad() or row["kind"] != "opaque":
            raise GatewayError("CREDENTIAL_UNAVAILABLE", 403, not_sent=True)
        return self._open(row["ciphertext"], binding.aad()).decode("utf-8")

    def revoke(self, binding: Binding):
        with self.connect() as c:
            row = c.execute(
                "SELECT binding,kind FROM credentials WHERE credential_ref=?", (str(binding.credential_ref),)
            ).fetchone()
            if row and row["binding"] != binding.aad():
                raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True)
            if row and row["kind"] == "oauth":
                raise GatewayError("OAUTH_REVOKE_REQUIRED", 409, not_sent=True)
            if row:
                c.execute(
                    "UPDATE credentials SET active=0,ciphertext=x'',fingerprint=x'' WHERE credential_ref=?",
                    (str(binding.credential_ref),),
                )
            else:
                self._quota(c, len(binding.aad()))
                try:
                    c.execute(
                        "INSERT INTO credentials(credential_ref,org_id,connection_id,revision,binding,fingerprint,ciphertext,active) VALUES (?,?,?,?,?,x'',x'',0)",
                        (
                            str(binding.credential_ref),
                            str(binding.org_id),
                            str(binding.connection_id),
                            binding.credential_revision,
                            binding.aad(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise GatewayError("CREDENTIAL_CONFLICT", 409, not_sent=True) from None
        return {"credential_ref": str(binding.credential_ref), "state": "revoked"}

    @staticmethod
    def _effect_aad(request: CallRequest):
        return rfc8785.dumps(
            {
                "type": "connector-result-v1",
                "org_id": str(request.binding.org_id),
                "operation_key": request.operation_key,
                "effect_digest": request.effect_digest(),
            }
        )

    def begin(self, request: CallRequest):
        org, key, hashed = str(request.binding.org_id), request.operation_key, request.effect_digest()
        with self.connect() as c:
            row = c.execute("SELECT * FROM effects WHERE org_id=? AND operation_key=?", (org, key)).fetchone()
            if row:
                if row["effect_digest"] != hashed:
                    raise GatewayError("CONNECTOR_OPERATION_CONFLICT", 409, not_sent=True)
                if row["state"] == "done":
                    try:
                        return strict_json(self._open(row["result"], self._effect_aad(request)))
                    except GatewayError:
                        raise GatewayError("CONNECTOR_RESULT_INTEGRITY_ERROR", 503) from None
                if row["state"] != "not_sent":
                    raise GatewayError("CONNECTOR_EFFECT_UNKNOWN", 409)
                c.execute(
                    "UPDATE effects SET state='preparing',error_code=NULL,updated_at=unixepoch() WHERE org_id=? AND operation_key=?",
                    (org, key),
                )
            else:
                self._quota(c, 65536)
                if c.execute("SELECT count(*) FROM effects").fetchone()[0] >= 2000:
                    raise GatewayError("CONNECTOR_STORAGE_QUOTA", 429, not_sent=True)
                c.execute(
                    "INSERT INTO effects(org_id,operation_key,effect_digest,connection_id,credential_ref,state) VALUES (?,?,?,?,?,'preparing')",
                    (org, key, hashed, str(request.binding.connection_id), str(request.binding.credential_ref)),
                )
        return None

    def calling(self, request: CallRequest):
        with self.connect() as c:
            updated = c.execute(
                "UPDATE effects SET state='calling',updated_at=unixepoch() WHERE org_id=? AND operation_key=? AND effect_digest=? AND state='preparing'",
                (str(request.binding.org_id), request.operation_key, request.effect_digest()),
            ).rowcount
            if updated != 1:
                raise GatewayError("CONNECTOR_EFFECT_UNKNOWN", 409)

    def finish(self, request: CallRequest, result):
        encrypted = self._seal(rfc8785.dumps(result), self._effect_aad(request))
        with self.connect() as c:
            self._quota(c, len(encrypted))
            updated = c.execute(
                "UPDATE effects SET state='done',result=?,updated_at=unixepoch() WHERE org_id=? AND operation_key=? AND effect_digest=? AND state='calling'",
                (encrypted, str(request.binding.org_id), request.operation_key, request.effect_digest()),
            ).rowcount
            if updated != 1:
                raise GatewayError("CONNECTOR_EFFECT_UNKNOWN", 409)

    def fail(self, request: CallRequest, code):
        with self.connect() as c:
            row = c.execute(
                "SELECT state FROM effects WHERE org_id=? AND operation_key=?",
                (str(request.binding.org_id), request.operation_key),
            ).fetchone()
            if not row or row["state"] == "done":
                return False
            not_sent = row["state"] == "preparing"
            c.execute(
                "UPDATE effects SET state=?,error_code=?,updated_at=unixepoch() WHERE org_id=? AND operation_key=?",
                ("not_sent" if not_sent else "unknown", code, str(request.binding.org_id), request.operation_key),
            )
            return not_sent

    def status(self, request: CallRequest):
        with self.connect() as c:
            row = c.execute(
                "SELECT state,effect_digest,error_code FROM effects WHERE org_id=? AND operation_key=?",
                (str(request.binding.org_id), request.operation_key),
            ).fetchone()
        if row is None:
            return {"state": "not_found", "operation_key": request.operation_key}
        if row["effect_digest"] != request.effect_digest():
            raise GatewayError("CONNECTOR_OPERATION_CONFLICT", 409)
        return {
            "state": row["state"],
            "effect_digest": row["effect_digest"],
            "operation_key": request.operation_key,
            "error_code": row["error_code"],
        }

    def may_have_effect(self, request: CallRequest):
        with self.connect() as c:
            row = c.execute(
                "SELECT state FROM effects WHERE org_id=? AND operation_key=?",
                (str(request.binding.org_id), request.operation_key),
            ).fetchone()
        return bool(row and row["state"] not in {"preparing", "not_sent"})

    def close(self):
        self._owner.close()
