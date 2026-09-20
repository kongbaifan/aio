import json
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.platform_errors import PlatformError
from app.runtime.catalog import validate_schema
from app.runtime.contracts import Checkpoint, ModelTurn, PlannedCall
from app.runtime.model_client import ChatModel


class Chunks(httpx.AsyncByteStream):
    def __init__(self, content, step=7):
        self.content, self.step = content, step

    async def __aiter__(self):
        for i in range(0, len(self.content), self.step):
            yield self.content[i : i + self.step]


def stream_bytes(items, *, done=True, newline="\n"):
    frames = [f"data: {json.dumps(item, ensure_ascii=False)}{newline}{newline}" for item in items]
    if done:
        frames.append(f"data: [DONE]{newline}{newline}")
    return "".join(frames).encode("utf-8")


def model(monkeypatch, content, *, status=200, secret_env="AIO_SYNTHETIC_MODEL_KEY"):
    monkeypatch.setenv("AIO_SYNTHETIC_MODEL_KEY", "synthetic-private-marker")
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(status, headers={"content-type": "text/event-stream"}, stream=Chunks(content))

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder), follow_redirects=False)
    definition = {
        "id": uuid4(),
        "provider": "test",
        "model": "test-model",
        "config": {
            "endpoint": "https://model.example.test/v1/chat/completions",
            "secret_env": secret_env,
            "max_output_tokens": 1024,
            "max_call_charge": "0.100000",
            "input_price_per_million": "1.000000",
            "output_price_per_million": "2.000000",
        },
    }
    return (
        ChatModel(
            definition,
            approved_origins=frozenset({"https://model.example.test"}),
            secret_names=frozenset({"AIO_SYNTHETIC_MODEL_KEY"}),
            production=True,
            client=client,
        ),
        client,
        requests,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
async def test_bounded_stream_accumulates_unicode_and_usage(monkeypatch, newline):
    items = [
        {"choices": [{"index": 0, "delta": {"content": "你好"}}]},
        {"choices": [{"index": 0, "delta": {"content": "世界"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
    ]
    m, client, requests = model(monkeypatch, stream_bytes(items, newline=newline))
    async with client:
        result = [x async for x in m.stream([{"role": "user", "content": "hello"}], [])]
    assert result[:-1] == ["你好", "世界"]
    assert result[-1].content == "你好世界"
    assert m.charge(result[-1]) == Decimal("0.000016")
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer synthetic-private-marker"


@pytest.mark.asyncio
async def test_tool_call_fragments_are_only_executed_after_complete_turn(monkeypatch):
    items = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "capture", "arguments": '{"value":'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "7}"}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ]
    m, client, _ = model(monkeypatch, stream_bytes(items))
    async with client:
        result = [x async for x in m.stream([{"role": "user", "content": "hello"}], [])]
    assert len(result) == 1 and result[0].tool_calls[0].arguments == {"value": 7}
    assert result[0].input_tokens is None and m.charge(result[0]) is None


@pytest.mark.asyncio
async def test_incomplete_stream_does_not_create_final_turn_or_retry(monkeypatch):
    m, client, requests = model(
        monkeypatch, stream_bytes([{"choices": [{"delta": {"content": "partial"}}]}], done=False)
    )
    chunks = []
    async with client:
        with pytest.raises(PlatformError):
            async for item in m.stream([], []):
                chunks.append(item)
    assert chunks == ["partial"]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_provider_redirect_and_error_body_are_not_followed_or_exposed(monkeypatch):
    m, client, requests = model(monkeypatch, b"synthetic-private-marker", status=302)
    async with client:
        with pytest.raises(PlatformError) as exc:
            _ = [x async for x in m.stream([], [])]
    assert len(requests) == 1
    assert "synthetic-private-marker" not in str(exc.value)


@pytest.mark.asyncio
async def test_ambiguous_tool_arguments_are_rejected(monkeypatch):
    items = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "capture", "arguments": '{"value":1,"value":2}'},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    ]
    m, client, _ = model(monkeypatch, stream_bytes(items))
    async with client:
        with pytest.raises(PlatformError):
            _ = [x async for x in m.stream([], [])]


def test_model_cannot_read_arbitrary_environment_variable(monkeypatch):
    monkeypatch.setenv("UNRELATED_PRIVATE_SECRET", "unrelated-marker")
    with pytest.raises(PlatformError) as exc:
        model(monkeypatch, b"", secret_env="UNRELATED_PRIVATE_SECRET")
    assert exc.value.code == "MODEL_SECRET_DENIED"


def test_checkpoint_keeps_model_call_ids_and_does_not_regenerate_actions():
    cp = Checkpoint(messages=({"role": "user", "content": "capture"},))
    turn = ModelTurn(
        tool_calls=(PlannedCall(id="external-id", name="capture", arguments={"value": 7}),),
        finish_reason="tool_calls",
        input_tokens=10,
        output_tokens=2,
    )
    committed = cp.with_turn(turn)
    restored = Checkpoint.model_validate_json(committed.model_dump_json())
    assert restored.digest == committed.digest
    assert restored.logical_tool_id == "turn:1:tool:0"
    with pytest.raises(PlatformError):
        restored.with_tool_result("wrong-call", {"value": 7})
    next_cp = restored.with_tool_result(restored.logical_tool_id, {"value": 7})
    assert next_cp.phase == "model" and next_cp.logical_model_id == "model:1"
    assert next_cp.messages[-1]["tool_call_id"] == "external-id"


def test_truncated_turn_never_dispatches_its_tools():
    cp = Checkpoint(messages=({"role": "user", "content": "capture"},))
    turn = ModelTurn(
        content="partial", tool_calls=(PlannedCall(id="c1", name="capture", arguments={}),), finish_reason="length"
    )
    stopped = cp.with_turn(turn)
    assert stopped.phase == "final" and not stopped.pending_calls and stopped.finish_reason == "length"


def test_checkpoint_rejects_unknown_version_and_duplicate_calls():
    with pytest.raises(ValidationError):
        Checkpoint(schema_version=2, messages=())
    with pytest.raises(ValidationError):
        ModelTurn(tool_calls=(PlannedCall(id="same", name="capture", arguments={}),) * 2, finish_reason="tool_calls")


def test_remote_schema_reference_is_not_fetched():
    with pytest.raises(PlatformError):
        validate_schema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"value": {"$ref": "https://private.example.test/schema"}},
            }
        )


def test_worker_settings_require_no_browser_idp_secret(platform_env):
    from app.platform_settings import WorkerSettings

    settings = WorkerSettings.from_env(
        {
            "HARNESS_MODE": "platform-test",
            "PLATFORM_DATABASE_URL": platform_env["PLATFORM_DATABASE_URL"],
            "PLATFORM_WORKER_ORG_ID": str(uuid4()),
            "PLATFORM_WORKER_ID": "test-worker",
            "PLATFORM_MODEL_ALLOWED_ORIGINS": "https://model.example.test",
            "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "AIO_SYNTHETIC_MODEL_KEY",
        }
    )
    assert settings.worker_id == "test-worker"
    assert not hasattr(settings, "oidc_client_secret")
    assert settings.approved_model_origins == frozenset({"https://model.example.test"})


def test_worker_settings_do_not_accept_model_urls_with_paths_or_unknown_secret_names(platform_env):
    from app.platform_settings import WorkerSettings
    from app.platform_errors import PlatformConfigurationError

    base = {
        "HARNESS_MODE": "platform-test",
        "PLATFORM_DATABASE_URL": platform_env["PLATFORM_DATABASE_URL"],
        "PLATFORM_WORKER_ORG_ID": str(uuid4()),
        "PLATFORM_MODEL_ALLOWED_ORIGINS": "https://model.example.test",
        "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "AIO_SYNTHETIC_MODEL_KEY",
    }
    for change in [
        {"PLATFORM_MODEL_ALLOWED_ORIGINS": "https://model.example.test/path"},
        {"PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "!shell"},
        {"HARNESS_MODE": "legacy-local"},
        {"PLATFORM_WORKER_ORG_ID": "not-a-uuid"},
    ]:
        with pytest.raises(PlatformConfigurationError):
            WorkerSettings.from_env({**base, **change})
