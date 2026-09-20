import asyncio
from dataclasses import replace
from decimal import Decimal
import json

import httpx
import pytest

from app.knowledge.embedding_client import EmbeddingClient
from app.platform_errors import PlatformError


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


def definition():
    return {
        "model": "synthetic-embedding",
        "config": {
            "endpoint": "https://embedding.example.test/v1/embeddings",
            "secret_env": "SYNTHETIC_EMBEDDING_KEY",
            "dimensions": 3,
            "batch_size": 4,
            "input_price_per_million": "100",
            "max_call_charge": "0.02",
        },
    }


def settings(platform_settings):
    return replace(
        platform_settings,
        model_allowed_origins=frozenset({"https://embedding.example.test"}),
        model_secret_names=frozenset({"SYNTHETIC_EMBEDDING_KEY"}),
    )


def test_embedding_http_preserves_indices_and_records_exact_usage(platform_settings, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-worker-only-embedding-key")
    calls = []

    def handle(request):
        calls.append(request)
        value = {
            "data": [{"index": 1, "embedding": [0, 1, 0]}, {"index": 0, "embedding": [1, 0, 0]}],
            "usage": {"prompt_tokens": 10},
        }
        return httpx.Response(
            200, headers={"content-type": "application/json"}, stream=Bytes(json.dumps(value).encode())
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = EmbeddingClient(definition(), settings(platform_settings), client=http)
            result = await client.embed(["first", "second"])
            assert result["vectors"] == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
            assert result["charge"] == Decimal("0.001000") and result["input_tokens"] == 10

    asyncio.run(run())
    assert len(calls) == 1
    assert json.loads(calls[0].content)["encoding_format"] == "float"


@pytest.mark.parametrize(
    "result",
    [
        {"data": [{"index": 0, "embedding": [1, 0]}]},
        {"data": [{"index": 0, "embedding": [0, 0, 0]}]},
        {"data": [{"index": 0, "embedding": [True, 0, 1]}]},
        {"data": [{"index": 0, "embedding": [1, 0, 0]}], "usage": {"prompt_tokens": -1}},
        {"data": [{"index": 0, "embedding": [1, 0, 0]}], "usage": {"prompt_tokens": 1000000}},
        {"data": [{"index": 1, "embedding": [1, 0, 0]}]},
    ],
)
def test_invalid_embedding_shapes_and_costs_are_never_treated_as_success(platform_settings, monkeypatch, result):
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-worker-only-key")

    def handle(request):
        return httpx.Response(
            200, headers={"content-type": "application/json"}, stream=Bytes(json.dumps(result).encode())
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            with pytest.raises(PlatformError):
                await EmbeddingClient(definition(), settings(platform_settings), client=http).embed(["text"])

    asyncio.run(run())


def test_missing_embedding_usage_remains_unknown_not_zero(platform_settings, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-worker-only-key")

    def handle(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=Bytes(b'{"data":[{"index":0,"embedding":[1,0,0]}]}'),
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await EmbeddingClient(definition(), settings(platform_settings), client=http).embed(["text"])
            assert result["charge"] is None and result["input_tokens"] is None

    asyncio.run(run())


def test_embedding_redirect_never_forwards_worker_credentials(platform_settings, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_EMBEDDING_KEY", "synthetic-worker-only-key")
    seen = []

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://unapproved.invalid/receive"}, stream=Bytes(b""))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as http:
            with pytest.raises(PlatformError):
                await EmbeddingClient(definition(), settings(platform_settings), client=http).embed(["text"])

    asyncio.run(run())
    assert seen == [definition()["config"]["endpoint"]]
