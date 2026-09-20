"""Compatibility declarations are not install instructions or permission grants."""

import json

from aio_runtime_policy import RuntimeManifest

from ..platform_errors import PlatformError


def compatible(package, profile):
    if package.get("schema_version", 1) == 1:
        return
    runtime = profile.get("runtime") if profile else None
    if not isinstance(runtime, dict):
        raise PlatformError("SKILL_RUNTIME_REQUIRED", "This Skill requires an approved signed dependency runtime", 403)
    manifest = RuntimeManifest.model_validate(runtime["manifest"])
    if manifest.digest != runtime["manifest_digest"] or manifest.digest != package["runtime_manifest_digest"]:
        raise PlatformError("SKILL_RUNTIME_MISMATCH", "Skill environment must match the exact approved manifest", 409)
    installed = {item.name: item.version for item in manifest.packages}
    if any(installed.get(item["name"]) != item["version"] for item in package["dependencies"]):
        raise PlatformError(
            "SKILL_DEPENDENCY_MISMATCH", "Required package versions are not installed in this approved image", 409
        )


def runtime_report(package):
    return {
        "schema_version": 1,
        "runtime_manifest_digest": package["runtime_manifest_digest"],
        "dependencies": {item["name"]: item["version"] for item in package["dependencies"]},
    }


def runtime_check_code(package):
    expected = runtime_report(package)
    return (
        "import hashlib,json,sys\nfrom pathlib import Path\nfrom importlib.metadata import version\n"
        f"expected=json.loads({json.dumps(expected, sort_keys=True)!r})\n"
        "manifest=json.loads(Path('/opt/aio-runtime/manifest.json').read_text(encoding='utf-8'))\n"
        "digest=hashlib.sha256(b'aio-runtime-manifest-v1\\0'+json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()\n"
        "assert digest==expected['runtime_manifest_digest'] and sys.version_info[:2]==(3,12)\n"
        "assert all(version(name)==value for name,value in expected['dependencies'].items())\n"
        "print('AIO_SKILL_RESULT:'+json.dumps(expected,separators=(',',':')))\n"
    )
