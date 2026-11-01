"""HTTPS collector sink for the audit archive relay.

Collector contract: ``POST <url>`` with one ``ArchiveRecord`` JSON body, ``Authorization: Bearer`` and
``Idempotency-Key: <org_id>:<audit_id>``. The collector stores each key once; 2xx or 409 (already stored)
means delivered. Response bodies are never read, stored or logged.
"""

from __future__ import annotations

import httpx

from .archive import ArchiveDeliveryError, ArchiveRecord

_RETRYABLE = frozenset({408, 425, 429})


class HttpArchiveSink:
    def __init__(self, url: str, token: str, *, timeout_seconds: float = 8, client: httpx.AsyncClient | None = None):
        self.url, self._token = url, token
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(5, timeout_seconds)),
            trust_env=False,
            follow_redirects=False,
        )
        self._owned = client is None

    async def deliver(self, record: ArchiveRecord) -> None:
        headers = {
            "Authorization": "Bearer " + self._token,
            "Idempotency-Key": record.idempotency_key,
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
        }
        try:
            # Streamed so the body is never buffered; leaving the block closes the response unread.
            async with self.client.stream("POST", self.url, content=record.model_dump_json(), headers=headers) as r:
                status = r.status_code
        except httpx.TimeoutException:
            raise ArchiveDeliveryError("ARCHIVE_TIMEOUT") from None
        except httpx.HTTPError:
            raise ArchiveDeliveryError("ARCHIVE_UNAVAILABLE") from None
        if 200 <= status < 300 or status == 409:
            return
        if status >= 500 or status in _RETRYABLE:
            raise ArchiveDeliveryError("ARCHIVE_UNAVAILABLE")
        # Redirects are never followed and other 4xx need an operator; both keep retrying with backoff.
        raise ArchiveDeliveryError("ARCHIVE_REJECTED")

    async def close(self) -> None:
        if self._owned:
            await self.client.aclose()
