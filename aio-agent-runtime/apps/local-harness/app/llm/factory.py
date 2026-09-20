"""按请求/会话解析模型客户端；配置只来自项目 models.json。"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Settings
from ..platform_settings import require_legacy_mode
from .base import ModelClient
from .openai_compatible import OpenAICompatibleClient
from .providers import ModelRef, ModelRegistry, parse_model_ref

logger = logging.getLogger(__name__)


class ModelService:
    """模型目录 + 客户端缓存。支持工作台按 provider/model 切换。"""

    def __init__(self, settings: Settings):
        require_legacy_mode()
        self.settings = settings
        self.registry = ModelRegistry.load(settings.models_json or None)
        self._clients: dict[str, ModelClient] = {}

        default_provider = self.registry.default_provider
        default_model = self.registry.default_model
        if settings.harness_model:
            parsed = parse_model_ref(settings.harness_model)
            if parsed:
                default_provider, default_model = parsed
        if settings.llm_provider:
            default_provider = settings.llm_provider
        if settings.llm_model:
            default_model = settings.llm_model

        if not default_provider or not default_model:
            catalog = self.registry.catalog()
            first = next((item for item in catalog if item.available), catalog[0] if catalog else None)
            if first:
                default_provider, default_model = first.provider, first.id
            else:
                raise RuntimeError(
                    "config/models.json 未配置任何模型。请添加 provider/model，并在 .env 中设置对应 API Key。"
                )

        self.default_provider = default_provider
        self.default_model = default_model
        logger.info(
            "ModelService ready source=%s default=%s/%s providers=%s",
            self.registry.source_path,
            self.default_provider,
            self.default_model,
            ",".join(self.registry.list_providers()),
        )

    def list_models(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.registry.catalog()]

    def default_selection(self) -> dict[str, str]:
        return {
            "provider": self.default_provider,
            "model": self.default_model,
            "label": f"{self.default_provider}/{self.default_model}",
        }

    def resolve_selection(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> tuple[str, str]:
        selected_provider = (provider or fallback_provider or self.default_provider or "").strip()
        selected_model = (model or fallback_model or self.default_model or "").strip()
        if not selected_provider or not selected_model:
            return self.default_provider, self.default_model
        return selected_provider, selected_model

    def get_client(self, provider: str, model_id: str) -> ModelClient:
        provider, model_id = self.resolve_selection(provider, model_id)
        cache_key = f"{provider}/{model_id}"
        cached = self._clients.get(cache_key)
        if cached is not None:
            return cached

        ref = self.registry.get_model(
            provider,
            model_id,
            max_tokens_override=self.settings.llm_max_tokens,
        )
        client = self._build_client(ref)
        self._clients[cache_key] = client
        return client

    def _build_client(self, ref: ModelRef) -> ModelClient:
        return OpenAICompatibleClient(
            ref,
            timeout=float(self.settings.llm_timeout_seconds),
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            max_retries=self.settings.llm_max_retries,
        )

    def describe_client(self, client: ModelClient) -> dict[str, str]:
        provider = getattr(client, "provider", "custom")
        model = getattr(client, "model", "unknown")
        return {"provider": str(provider), "model": str(model), "label": f"{provider}/{model}"}

    async def close(self) -> None:
        for client in self._clients.values():
            close = getattr(client, "close", None)
            if close:
                await close()
        self._clients.clear()


def create_model_service(settings: Settings) -> ModelService:
    return ModelService(settings)
