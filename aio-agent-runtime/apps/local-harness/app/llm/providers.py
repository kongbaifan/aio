"""项目内模型注册表（结构参考 pi-ai，配置仅来自本仓库）。

唯一配置源：
  1. <project>/config/models.json
  2. 可选 HARNESS_MODELS_JSON 覆盖路径
  3. 可选 config/models.local.json 覆盖（本机）

不读取 ~/.pi；不提供演示模型。
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import models_json_path, models_local_json_path


class ModelConfigError(ValueError):
    """配置无法解析成可用模型时抛出。"""


@dataclass(frozen=True)
class ModelRef:
    """一次 LLM 调用所需的连接信息。"""

    provider: str
    id: str
    name: str
    base_url: str
    api: str
    api_key: str
    headers: dict[str, str] = field(default_factory=dict)
    max_tokens: int | None = None
    context_window: int | None = None
    reasoning: bool = False
    # 推理强度（low / medium / high）。配了它、且 compat 打开
    # supportsReasoningEffort 时，才会作为 reasoning_effort 下发。
    reasoning_effort: str = ""
    # 绝大多数 OpenAI 兼容网关只认 system，默认关闭；只有明确要求 developer
    # 角色的模型（o1 系等）才在 compat 里打开。此前默认 True，方向是反的——
    # 只因为当时这个开关是空转的才没出问题。
    supports_developer_role: bool = False
    supports_reasoning_effort: bool = False
    max_tokens_field: str = "max_tokens"
    # 流式请求是否带 stream_options.include_usage。OpenAI 兼容接口普遍支持，
    # 个别网关会因为不认这个字段直接 400，遇到就在 compat 里关掉。
    supports_stream_usage: bool = True

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.id}"


@dataclass(frozen=True)
class ModelCatalogItem:
    provider: str
    id: str
    name: str
    available: bool
    reason: str = ""
    reasoning: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "id": self.id,
            "name": self.name,
            "label": f"{self.provider}/{self.id}",
            "available": self.available,
            "reason": self.reason,
            "reasoning": self.reasoning,
            "description": self.description,
        }


def default_models_json_path() -> Path:
    return models_json_path()


def default_models_local_path() -> Path:
    return models_local_json_path()


def _looks_like_env_name(value: str) -> bool:
    if not value or value.startswith("sk-") or value.startswith("key-"):
        return False
    if len(value) > 64:
        return False
    return value.replace("_", "").isalnum() and value.upper() == value


def _resolve_secret_value(raw: str | None) -> str:
    """解析 apiKey，对齐 pi models.json 的三种写法：

    1. 字面量密钥（最常见，与 pi 一致）: "sk-xxxx"
    2. 环境变量名: "DEEPSEEK_API_KEY"（全大写+下划线）
    3. Shell 命令: "!op read op://..."
    """
    if raw is None:
        return ""
    value = str(raw).strip()
    if not value:
        return ""
    if value.startswith("!"):
        try:
            completed = subprocess.run(
                value[1:],
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired as exc:
            # 此前没捕获，TimeoutExpired 会以原始异常逃逸出配置解析层。
            raise ModelConfigError(f"apiKey 命令超时（15s）: {value[1:]!r}") from exc
        except OSError as exc:
            raise ModelConfigError(f"apiKey 命令无法执行: {value[1:]!r} — {exc}") from exc
        if completed.returncode != 0:
            # 带上 stderr：原来直接丢弃，用户拿不到任何诊断信息
            #（op 未登录、命令拼错都长一个样）。
            detail = (completed.stderr or "").strip()[:200]
            raise ModelConfigError(
                f"apiKey 命令执行失败: {value[1:]!r}" + (f" — {detail}" if detail else "")
            )
        return completed.stdout.strip()
    # 仅当整段像 ENV 名时才替换；sk- / 普通字符串一律当字面量（与 pi 行为一致）
    if _looks_like_env_name(value):
        return os.environ.get(value, "").strip()
    return value


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelConfigError(f"无法读取模型配置 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelConfigError(f"模型配置必须是 JSON 对象: {path}")
    return data


def _models_as_map(raw: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                result[str(item["id"])] = dict(item)
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict):
                entry = dict(item)
                entry.setdefault("id", key)
                result[str(entry["id"])] = entry
            else:
                result[str(key)] = {"id": str(key), "name": str(key)}
    return result


def _extract_providers(data: dict[str, Any]) -> dict[str, Any]:
    """取出 provider 表，允许省略 providers 外层（扁平写法）。

    扁平时要排除 default / $schema 这类顶层元数据键，否则它们会被当成
    provider 名混进来。
    """
    nested = data.get("providers")
    if isinstance(nested, dict):
        return nested
    return {
        key: value
        for key, value in data.items()
        if isinstance(value, dict) and key not in {"default", "$schema"}
    }


def _local_override_path(primary: Path) -> Path:
    """主配置对应的本机覆盖文件：a/b/models.json -> a/b/models.local.json。"""
    return primary.with_name(f"{primary.stem}.local{primary.suffix}")


def _deep_merge_providers(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for name, cfg in overlay.items():
        if not isinstance(cfg, dict):
            continue
        if name not in merged or not isinstance(merged.get(name), dict):
            normalized = dict(cfg)
            normalized["models"] = _models_as_map(cfg.get("models"))
            merged[name] = normalized
            continue
        current = dict(merged[name])
        for key, value in cfg.items():
            if key == "models":
                # 逐个 model 做字段合并，而不是整体替换：local 里只想改
                # maxTokens 时，不该把 contextWindow 和 model 级 compat 一起丢掉。
                model_map = _models_as_map(current.get("models"))
                for model_id, overlay_model in _models_as_map(value).items():
                    base_model = model_map.get(model_id)
                    if isinstance(base_model, dict):
                        merged_model = dict(base_model)
                        for mk, mv in overlay_model.items():
                            # model 级 compat 同样是字段合并。
                            if mk == "compat" and isinstance(mv, dict):
                                merged_compat = dict(base_model.get("compat") or {})
                                merged_compat.update(mv)
                                merged_model["compat"] = merged_compat
                            else:
                                merged_model[mk] = mv
                        model_map[model_id] = merged_model
                    else:
                        model_map[model_id] = overlay_model
                current["models"] = model_map
            elif key in {"compat", "headers"} and isinstance(value, dict):
                # headers 之前是整体替换：overlay 里加一个 HTTP-Referer，
                # base 里的 X-Title 等就全没了。和 compat 一样按字段合并。
                base_map = dict(current.get(key) or {})
                base_map.update(value)
                current[key] = base_map
            else:
                current[key] = value
        if not isinstance(current.get("models"), dict):
            current["models"] = _models_as_map(current.get("models"))
        merged[name] = current
    return merged


@dataclass
class ModelRegistry:
    """只加载本项目 models.json 的注册表。"""

    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    default_provider: str = ""
    default_model: str = ""
    source_path: str = ""

    @classmethod
    def load(cls, models_json: str | Path | None = None) -> "ModelRegistry":
        paths: list[Path] = []
        if models_json:
            paths.append(Path(models_json).expanduser())
        else:
            env_path = os.environ.get("HARNESS_MODELS_JSON", "").strip()
            if env_path:
                paths.append(Path(env_path).expanduser())
            else:
                paths.append(default_models_json_path())

        # 本机覆盖文件跟随主配置：<主配置>.local.json，而不是永远指向
        # <project>/config/models.local.json。否则用 HARNESS_MODELS_JSON 指向
        # 另一套配置时，项目里的本机覆盖仍会污染进来；测试也会因为开发者
        # 本地建了 config/models.local.json 而莫名其妙地红。
        local_path = _local_override_path(paths[0])
        providers: dict[str, dict[str, Any]] = {}
        default_provider = ""
        default_model = ""
        source = ""
        loaded_any = False

        for path in paths:
            if not path.is_file():
                continue
            data = _load_json_file(path)
            source = str(path)
            raw_providers = _extract_providers(data)
            if isinstance(raw_providers, dict):
                providers = _deep_merge_providers(providers, raw_providers)
            default = data.get("default") if isinstance(data.get("default"), dict) else {}
            if default.get("provider"):
                default_provider = str(default["provider"]).strip()
            if default.get("model"):
                default_model = str(default["model"]).strip()
            loaded_any = True
            break

        if local_path.is_file():
            data = _load_json_file(local_path)
            # 与主配置同样的宽容度：允许省略 providers 外层。此前 local 走的是
            # `else {}`，照着主文件写成扁平格式会被静默完全忽略，覆盖不生效
            # 也不报错。同一套格式在两个文件里语义必须一致。
            raw_providers = _extract_providers(data)
            if isinstance(raw_providers, dict) and raw_providers:
                providers = _deep_merge_providers(providers, raw_providers)
            default = data.get("default") if isinstance(data.get("default"), dict) else {}
            if default.get("provider"):
                default_provider = str(default["provider"]).strip()
            if default.get("model"):
                default_model = str(default["model"]).strip()
            source = f"{source}+{local_path}" if source else str(local_path)
            loaded_any = True

        if not loaded_any or not providers:
            raise ModelConfigError(
                f"未找到可用的模型配置。请创建 {default_models_json_path()} 并登记至少一个 provider。"
            )

        for name, cfg in list(providers.items()):
            if not isinstance(cfg, dict):
                continue
            cfg = dict(cfg)
            cfg["models"] = _models_as_map(cfg.get("models"))
            providers[name] = cfg

        if not default_provider or not default_model:
            for provider_name, cfg in sorted(providers.items()):
                models = cfg.get("models") or {}
                if isinstance(models, dict) and models:
                    first_id = next(iter(models))
                    default_provider = default_provider or provider_name
                    default_model = default_model or str(first_id)
                    break

        return cls(
            providers=providers,
            default_provider=default_provider,
            default_model=default_model,
            source_path=source,
        )

    def list_providers(self) -> list[str]:
        return sorted(self.providers)

    def peek_api_key(self, provider: str) -> str:
        cfg = self.providers.get(provider) or {}
        return self._resolve_api_key(provider, cfg, required=False)

    def _resolve_api_key(self, provider: str, provider_cfg: dict[str, Any], *, required: bool) -> str:
        if provider_cfg.get("apiKey"):
            key = _resolve_secret_value(str(provider_cfg["apiKey"]))
            if key:
                return key
        env_name = provider_cfg.get("apiKeyEnv")
        if env_name:
            key = os.environ.get(str(env_name), "").strip()
            if key:
                return key
        # 这里曾经回落到全局 LLM_API_KEY。去掉了：那意味着 A 家的密钥会被当 Bearer
        # 发给 B 家的 baseUrl（只要 B 的专属 key 没配），而且 catalog() 会把所有
        # provider 都标成 available，界面上完全看不出来。密钥必须按 provider 显式配置。
        default = provider_cfg.get("apiKeyDefault")
        if default:
            return str(default)
        if required:
            raise ModelConfigError(
                f"provider {provider!r} 未配置 API Key。"
                f"请在 config/models.json 该 provider 下设置 apiKey（可写 sk- 字面量，与 pi 相同；"
                f"或写环境变量名如 DEEPSEEK_API_KEY）。"
            )
        return ""

    def catalog(self) -> list[ModelCatalogItem]:
        items: list[ModelCatalogItem] = []
        for provider_name, cfg in sorted(self.providers.items()):
            models = cfg.get("models") or {}
            if not isinstance(models, dict):
                continue
            key = self._resolve_api_key(provider_name, cfg, required=False)
            available = bool(key)
            reason = ""
            if not available:
                raw = str(cfg.get("apiKey") or "").strip()
                if not raw:
                    reason = "缺少 apiKey（在 models.json 的 provider 上填写 sk-... 或环境变量名）"
                elif _looks_like_env_name(raw):
                    reason = f"环境变量 {raw} 未设置"
                else:
                    reason = "apiKey 无效或为空"
            for model_id, model_cfg in models.items():
                if not isinstance(model_cfg, dict):
                    model_cfg = {"id": model_id, "name": str(model_id)}
                items.append(
                    ModelCatalogItem(
                        provider=provider_name,
                        id=str(model_cfg.get("id") or model_id),
                        name=str(model_cfg.get("name") or model_id),
                        available=available,
                        reason=reason,
                        reasoning=bool(model_cfg.get("reasoning", False)),
                        description=str(model_cfg.get("description") or ""),
                    )
                )
        return items

    def get_model(
        self,
        provider: str,
        model_id: str,
        *,
        max_tokens_override: int | None = None,
    ) -> ModelRef:
        provider = (provider or "").strip()
        model_id = (model_id or "").strip()
        if not provider or not model_id:
            raise ModelConfigError("provider 与 model id 不能为空")

        provider_cfg = self.providers.get(provider)
        if provider_cfg is None:
            raise ModelConfigError(
                f"未知 provider {provider!r}。请在 config/models.json 中登记，"
                f"当前可用: {', '.join(self.list_providers()) or '(无)'}"
            )

        models = provider_cfg.get("models") or {}
        if isinstance(models, dict) and model_id in models:
            model_cfg = dict(models[model_id]) if isinstance(models[model_id], dict) else {"id": model_id}
        else:
            # 此前这里静默兜底成 {"id": model_id}。配合 resolve_selection 的
            # 「只给 provider 就填全局默认 model」，会拼出 deepseek + gpt-5.5
            # 这种跨 provider 组合发给上游，只能拿到一个看不出根因的 400；
            # model id 打错字同理。不如在本地就说清楚。
            available = ", ".join(sorted(models)) if isinstance(models, dict) and models else "(无)"
            raise ModelConfigError(
                f"provider {provider!r} 下没有登记模型 {model_id!r}。"
                f"当前可用: {available}"
            )

        api = str(model_cfg.get("api") or provider_cfg.get("api") or "openai-completions")
        if api not in {"openai-completions", "openai"}:
            raise ModelConfigError(f"当前仅支持 openai-completions，收到 api={api!r}")

        base_url = str(provider_cfg.get("baseUrl") or "").rstrip("/")
        if not base_url:
            raise ModelConfigError(f"provider {provider!r} 缺少 baseUrl")

        api_key = self._resolve_api_key(provider, provider_cfg, required=True)

        compat = dict(provider_cfg.get("compat") or {})
        if isinstance(model_cfg.get("compat"), dict):
            compat.update(model_cfg["compat"])

        headers: dict[str, str] = {}
        raw_headers = provider_cfg.get("headers")
        if isinstance(raw_headers, dict):
            for hk, hv in raw_headers.items():
                headers[str(hk)] = _resolve_secret_value(str(hv))

        max_tokens = max_tokens_override
        if max_tokens is None:
            for key in ("maxTokens", "max_tokens"):
                if key in model_cfg and model_cfg[key] is not None:
                    max_tokens = int(model_cfg[key])
                    break

        context_window = None
        for key in ("contextWindow", "context_window"):
            if key in model_cfg and model_cfg[key] is not None:
                context_window = int(model_cfg[key])
                break

        return ModelRef(
            provider=provider,
            id=str(model_cfg.get("id") or model_id),
            name=str(model_cfg.get("name") or model_id),
            base_url=base_url,
            api="openai-completions",
            api_key=api_key,
            headers=headers,
            max_tokens=max_tokens,
            context_window=context_window,
            reasoning=bool(model_cfg.get("reasoning", False)),
            reasoning_effort=str(model_cfg.get("reasoningEffort") or ""),
            supports_developer_role=bool(compat.get("supportsDeveloperRole", False)),
            supports_reasoning_effort=bool(compat.get("supportsReasoningEffort", False)),
            max_tokens_field=str(compat.get("maxTokensField") or "max_tokens"),
            supports_stream_usage=bool(compat.get("supportsStreamUsage", True)),
        )


def get_model(
    provider: str,
    model_id: str,
    *,
    registry: ModelRegistry | None = None,
    max_tokens: int | None = None,
) -> ModelRef:
    reg = registry or ModelRegistry.load()
    return reg.get_model(provider, model_id, max_tokens_override=max_tokens)


def parse_model_ref(value: str) -> tuple[str, str] | None:
    """解析 'provider/model'；model id 内可再含 /。"""
    text = (value or "").strip()
    if not text or "/" not in text:
        return None
    provider, model = text.split("/", 1)
    provider = provider.strip()
    model = model.strip()
    if not provider or not model:
        return None
    return provider, model
