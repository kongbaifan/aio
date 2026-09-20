"""Non-secret stdio template references approved by the deployment operator."""

import re
from ..runtime.actions import canonical_digest


def stdio_policy(raw, url, authentication):
    required = {"profile_id", "image_digest", "template_digest"}
    if (
        not isinstance(raw, dict)
        or not required <= set(raw)
        or set(raw) - required - {"credential_env", "network_profile", "input_policy"}
    ):
        raise ValueError("Stdio endpoints reference approved templates only")
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", raw["profile_id"])
        or url != "stdio://" + raw["profile_id"]
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", raw["image_digest"])
        or not re.fullmatch(r"[0-9a-f]{64}", raw["template_digest"])
        or raw.get("network_profile", "none") != "none"
        or raw.get("input_policy", "none") not in {"none", "run_attachments"}
    ):
        raise ValueError("Stdio image/template identity must be pinned")
    env = raw.get("credential_env")
    if env and (
        not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", env)
        or env in {"PATH", "HOME", "TMPDIR", "USER", "SHELL", "LANG"}
        or env.startswith(("PYTHON", "LD_", "DYLD_", "NODE_", "PLATFORM_", "SANDBOX_", "CONNECTOR_"))
    ):
        raise ValueError("Stdio credentials cannot override execution or platform configuration")
    if authentication not in {"none", "bearer"} or bool(env) != (authentication == "bearer"):
        raise ValueError("Stdio credential policy must match its explicit template")
    return {**raw, "config_digest": canonical_digest("aio-stdio-endpoint-v1", raw)}
