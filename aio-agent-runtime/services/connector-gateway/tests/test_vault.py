from dataclasses import replace
import secrets
import sqlite3
from uuid import uuid4

import pytest

from aio_connector_gateway.contracts import CredentialPut, GatewayError
from aio_connector_gateway.vault import Vault
from helpers import TOKEN_A, TOKEN_B, binding, call_request, endpoint


def test_credentials_and_results_are_encrypted_and_bound_to_exact_identity(tmp_path):
    root = tmp_path / "vault"
    v = Vault(root, secrets.token_bytes(32))
    a, b = binding(), binding()
    try:
        v.put(a, TOKEN_A)
        v.put(b, TOKEN_B)
        assert v.secret(a) == TOKEN_A and v.secret(b) == TOKEN_B
        with pytest.raises(GatewayError):
            v.secret(a.model_copy(update={"org_id": b.org_id}))
        request = call_request(a)
        assert v.begin(request) is None
        v.calling(request)
        v.finish(request, {"content": "synthetic private business output"})
        assert v.begin(request) == {"content": "synthetic private business output"}
        for file in root.glob("connector.sqlite3*"):
            data = file.read_bytes()
            assert TOKEN_A.encode() not in data and TOKEN_B.encode() not in data
            assert b"synthetic private business output" not in data
    finally:
        v.close()


def test_revoked_binding_tombstone_cannot_be_resurrected_by_late_upload(tmp_path):
    v = Vault(tmp_path / "vault", secrets.token_bytes(32))
    b = binding()
    try:
        v.revoke(b)
        with pytest.raises(GatewayError) as late:
            v.put(b, TOKEN_A)
        assert late.value.code == "CREDENTIAL_CONFLICT"
        with pytest.raises(GatewayError):
            v.secret(b)
    finally:
        v.close()


def test_idempotent_credential_writes_cannot_replace_contents_or_destination(tmp_path):
    key = secrets.token_bytes(32)
    v = Vault(tmp_path / "vault", key)
    b = binding()
    try:
        assert v.put(b, TOKEN_A) == v.put(b, TOKEN_A)
        with pytest.raises(GatewayError):
            v.put(b, TOKEN_B)
        other_endpoint = replace(endpoint(), url="http://127.0.0.1:9998/mcp")
        with pytest.raises(GatewayError):
            v.secret(b.model_copy(update={"endpoint_digest": other_endpoint.digest}))
    finally:
        v.close()


def test_wrong_key_and_parallel_owners_are_rejected(tmp_path):
    key = secrets.token_bytes(32)
    root = tmp_path / "vault"
    v = Vault(root, key)
    with pytest.raises(RuntimeError):
        Vault(root, key)
    v.close()
    with pytest.raises(RuntimeError):
        Vault(root, secrets.token_bytes(32))
    restored = Vault(root, key)
    restored.close()


def test_crash_windows_recover_only_proven_pre_call_work(tmp_path):
    root, key = tmp_path / "vault", secrets.token_bytes(32)
    v = Vault(root, key)
    safe, unsafe = call_request(), call_request()
    v.begin(safe)
    v.begin(unsafe)
    v.calling(unsafe)
    v.close()
    v = Vault(root, key)
    try:
        assert v.status(safe)["state"] == "not_sent"
        assert v.begin(safe) is None
        with pytest.raises(GatewayError) as rejected:
            v.begin(unsafe)
        assert rejected.value.code == "CONNECTOR_EFFECT_UNKNOWN" and not rejected.value.not_sent
        assert v.status(unsafe)["state"] == "unknown"
    finally:
        v.close()


def test_ciphertext_copy_and_result_corruption_never_return_plaintext_or_retry_permission(tmp_path):
    v = Vault(tmp_path / "vault", secrets.token_bytes(32))
    a, b = binding(), binding()
    try:
        v.put(a, TOKEN_A)
        v.put(b, TOKEN_B)
        with sqlite3.connect(v.path) as c:
            blob = c.execute(
                "SELECT ciphertext FROM credentials WHERE credential_ref=?", (str(a.credential_ref),)
            ).fetchone()[0]
            c.execute("UPDATE credentials SET ciphertext=? WHERE credential_ref=?", (blob, str(b.credential_ref)))
        with pytest.raises(GatewayError):
            v.secret(b)
        request = call_request(a)
        v.begin(request)
        v.calling(request)
        v.finish(request, {"ok": True})
        with sqlite3.connect(v.path) as c:
            c.execute("UPDATE effects SET result=x'00' WHERE operation_key=?", (request.operation_key,))
        with pytest.raises(GatewayError) as corrupt:
            v.begin(request)
        assert not corrupt.value.not_sent
    finally:
        v.close()


def test_secret_never_appears_in_contract_repr_or_authority_payload():
    request = CredentialPut(binding=binding(), ticket_id=uuid4(), secret=TOKEN_A)
    assert TOKEN_A not in repr(request)
    assert TOKEN_A not in str(request.authority())
