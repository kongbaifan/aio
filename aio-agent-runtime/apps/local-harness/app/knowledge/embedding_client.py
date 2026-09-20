"""Bounded approved embedding requests. No model credentials enter parser/compute cells."""

from decimal import Decimal, ROUND_CEILING
import math
import os
import re
from urllib.parse import urlsplit

import httpx

from ..platform_errors import PlatformError
from ..platform_settings import DeploymentMode, validate_endpoint
from ..runtime.actions import strict_json
from ..runtime.contracts import bounded_json


class EmbeddingClient:
    def __init__(self, definition, settings, *, client=None):
        config = definition["config"]
        self.definition = definition
        self.endpoint = validate_endpoint(
            config["endpoint"], "embedding endpoint", production=settings.mode is DeploymentMode.PRODUCTION
        )
        url = urlsplit(self.endpoint)
        origins = getattr(settings, "approved_model_origins", getattr(settings, "model_allowed_origins", frozenset()))
        names = getattr(settings, "approved_secret_names", getattr(settings, "model_secret_names", frozenset()))
        name = config.get("secret_env", "")
        if (
            f"{url.scheme}://{url.netloc}" not in origins
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name)
            or name not in names
        ):
            raise PlatformError(
                "EMBEDDING_ENDPOINT_DENIED", "Embedding origin and credential require operator approval", 403
            )
        self._secret = os.environ.get(name, "")
        if not self._secret or len(self._secret) > 16384 or any(ord(ch) < 32 for ch in self._secret):
            raise PlatformError("MODEL_SECRET_UNAVAILABLE", "Embedding credential is unavailable", 503)
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(45, connect=5), trust_env=False, follow_redirects=False
        )
        self.owned = client is None

    async def embed(self, texts):
        config = self.definition["config"]
        if (
            not isinstance(texts, list)
            or not 1 <= len(texts) <= config["batch_size"]
            or any(not isinstance(t, str) or len(t.encode()) > 8192 for t in texts)
        ):
            raise PlatformError("EMBEDDING_INPUT_LIMIT", "Embedding batch is outside its approved bound", 422)
        payload = bounded_json({"model": self.definition["model"], "input": texts, "encoding_format": "float"}, 524288)
        try:
            async with self.client.stream(
                "POST",
                self.endpoint,
                json=payload,
                headers={
                    "Authorization": "Bearer " + self._secret,
                    "Accept-Encoding": "identity",
                    "Accept": "application/json",
                },
                follow_redirects=False,
            ) as response:
                if response.status_code != 200 or response.headers.get("content-encoding", "identity").lower() not in {
                    "",
                    "identity",
                }:
                    raise PlatformError(
                        "EMBEDDING_RESPONSE_UNCONFIRMED", "Embedding provider did not return a confirmed result", 502
                    )
                if response.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                    raise PlatformError("EMBEDDING_PROTOCOL_INVALID", "Embedding response must be bounded JSON", 502)
                raw = bytearray()
                async for data in response.aiter_raw():
                    raw.extend(data)
                    if len(raw) > 8 * 1024 * 1024:
                        raise PlatformError(
                            "EMBEDDING_RESPONSE_LIMIT", "Embedding response exceeds its byte bound", 502
                        )
                result = strict_json(bytes(raw), max_bytes=8 * 1024 * 1024)
        except httpx.HTTPError:
            raise PlatformError(
                "EMBEDDING_RESPONSE_UNCONFIRMED",
                "Embedding response was not confirmed; do not automatically repeat a billed request",
                502,
            ) from None
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("data"), list)
            or len(result["data"]) != len(texts)
        ):
            raise PlatformError("EMBEDDING_PROTOCOL_INVALID", "Embedding result count is invalid", 502)
        vectors = [None] * len(texts)
        for item in result["data"]:
            index, vector = item.get("index"), item.get("embedding")
            if (
                type(index) is not int
                or not 0 <= index < len(texts)
                or vectors[index] is not None
                or not isinstance(vector, list)
                or len(vector) != config["dimensions"]
            ):
                raise PlatformError(
                    "EMBEDDING_DIMENSION_MISMATCH", "Embedding shape does not match its immutable model version", 502
                )
            if any(type(v) not in {int, float} or not math.isfinite(v) or abs(v) > 1e6 for v in vector) or not any(
                v != 0 for v in vector
            ):
                raise PlatformError("EMBEDDING_VECTOR_INVALID", "Embedding vector must be finite and nonzero", 502)
            vectors[index] = [float(v) for v in vector]
        usage = result.get("usage", {})
        tokens = usage.get("prompt_tokens", usage.get("total_tokens")) if isinstance(usage, dict) else None
        if tokens is not None and (type(tokens) is not int or not 0 <= tokens <= 10000000):
            raise PlatformError("EMBEDDING_USAGE_INVALID", "Embedding usage is outside its bounded contract", 502)
        amount = (
            (Decimal(tokens) * Decimal(config["input_price_per_million"]) / Decimal(1000000)).quantize(
                Decimal("0.000001"), rounding=ROUND_CEILING
            )
            if tokens is not None
            else None
        )
        if amount is not None and amount > Decimal(config["max_call_charge"]):
            raise PlatformError(
                "EMBEDDING_CHARGE_UNCONFIRMED", "Provider usage exceeds the configured charge bound", 502
            )
        return {"vectors": vectors, "input_tokens": tokens, "charge": amount}

    async def close(self):
        if self.owned:
            await self.client.aclose()


class EmbeddingFactory:
    def __init__(self, settings):
        self.settings = settings

    def create(self, definition):
        return EmbeddingClient(definition, self.settings)
