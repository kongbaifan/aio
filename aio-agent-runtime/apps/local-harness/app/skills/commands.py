"""Build fixed commands; they are strings for remote cells, NEVER executed by the API/Worker."""

import json

from ..platform_errors import PlatformError
from ..runtime.actions import strict_json
from ..runtime.catalog import validate_arguments
from .catalog import file_text

RESULT_PREFIX = "AIO_SKILL_RESULT:"
CREDENTIAL_PATTERN = r"sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AIza[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"

# Only this trusted scanner interprets package source. It runs in a no-network cell.
# Structural/secret-pattern checks are NOT a malware or semantic safety certification.
SCAN_CODE = r"""
import ast, json, re
from pathlib import Path
p = json.loads(Path("package.json").read_text(encoding="utf-8"))
secret = re.compile(__CREDENTIAL_PATTERN__)
trees = {}
for f in p["files"]:
    if secret.search(f["content"]):
        raise ValueError("CREDENTIAL_SHAPED_CONTENT")
    if f["path"].endswith(".py"):
        trees[f["path"]] = ast.parse(f["content"], filename=f["path"])
for e in p["entrypoints"]:
    functions = [n for n in trees[e["path"]].body if isinstance(n, ast.FunctionDef) and n.name == "run"]
    if len(functions) != 1 or len(functions[0].args.args) != 1 or functions[0].args.posonlyargs or functions[0].args.kwonlyargs:
        raise ValueError("ENTRYPOINT_REQUIRES_RUN_PAYLOAD")
print("AIO_SKILL_RESULT:" + json.dumps({"schema_version": 1, "files": len(p["files"]), "python_files": len(trees), "entrypoints": len(p["entrypoints"]), "checks": ["bounded-text-package", "python-ast", "entrypoint-signature", "credential-patterns"]}, separators=(",", ":")))
""".strip().replace("__CREDENTIAL_PATTERN__", repr(CREDENTIAL_PATTERN))


def entrypoint(skill: dict, name: str) -> dict:
    entries = [item for item in skill["package"]["entrypoints"] if item["name"] == name]
    if len(entries) != 1:
        raise PlatformError("SKILL_ENTRYPOINT_INVALID", "Entrypoint is not declared by this version", 409)
    return entries[0]


def call_code(skill: dict, name: str, arguments: dict) -> str:
    e = entrypoint(skill, name)
    validate_arguments({"input_schema": e["input_schema"]}, arguments)
    source = file_text(skill, e["path"])
    location = "/opt/aio-skill/" + skill["digest"] + "/" + e["path"]
    # The source is embedded in the command, not loaded from a mutable workspace file.
    # A previous tool cannot replace this entrypoint by rewriting a shared scripts directory.
    code = (
        "import json\n"
        f"_ns={{'__name__':'__aio_skill__','__file__':{location!r}}}\n"
        f"exec(compile({source!r}, {location!r}, 'exec'), _ns)\n"
        f"_result=_ns['run'](json.loads({json.dumps(arguments, ensure_ascii=False, allow_nan=False)!r}))\n"
        f"print('\\n{RESULT_PREFIX}'+json.dumps(_result, ensure_ascii=False, allow_nan=False, separators=(',', ':')))\n"
    )
    if len(code.encode("utf-8")) > 65536 or "\0" in code:
        raise PlatformError(
            "SKILL_COMMAND_TOO_LARGE", "Compiled Skill invocation exceeds the remote command bound", 413
        )
    return code


def result_value(result: dict, *, output_schema: dict | None = None) -> dict:
    if result.get("error_code") or result.get("exit_code") != 0 or result.get("truncated"):
        raise PlatformError("SKILL_EXECUTION_FAILED", "Skill failed its bounded isolated execution", 422)
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > 32768:
        raise PlatformError("SKILL_RESULT_INVALID", "Skill result is outside the output bound", 422)
    markers = [line[len(RESULT_PREFIX) :] for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    if len(markers) != 1:
        raise PlatformError("SKILL_RESULT_INVALID", "Skill must return exactly one typed result", 422)
    value = strict_json(markers[0].encode("utf-8"), max_bytes=32768)
    if not isinstance(value, dict):
        raise PlatformError("SKILL_RESULT_INVALID", "Skill result must be a JSON object", 422)
    if output_schema is not None:
        validate_arguments({"input_schema": output_schema}, value)
    return value
