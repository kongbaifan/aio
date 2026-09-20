"""Explicit synthetic/reference MCP server, executed only in its dedicated container."""

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID, uuid4

mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
if mode == "stdout-flood":
    while True:
        os.write(1, b"x" * 8192)
if mode == "stderr-flood":
    while True:
        os.write(2, b"private-stdio-error-" + os.environ.get("MCP_ACCESS_TOKEN", "").encode() + b"x" * 8192)
if mode == "invalid-protocol":
    os.write(1, b"this is not a JSON RPC frame\n")
    time.sleep(600)
if mode == "hang":
    time.sleep(600)

from mcp.server.mcpserver import MCPServer  # noqa: E402 - fault fixtures intentionally run before SDK initialization

server = MCPServer("isolated-stdio-reference", version="1", log_level="WARNING")
instance = uuid4().hex
count = 0


@server.tool()
def identity(query: str) -> dict:
    global count
    count += 1
    token = os.environ.get("MCP_ACCESS_TOKEN", "anonymous")
    return {
        "subject_digest": hashlib.sha256(token.encode()).hexdigest(),
        "instance": instance,
        "calls": count,
        "query": query,
    }


@server.tool()
def isolation_facts() -> dict:
    root_writable = False
    try:
        Path("/etc/stdio_must_not_write").write_text("x")
        root_writable = True
    except OSError:
        pass
    return {
        "uid": os.getuid(),
        "home": os.environ.get("HOME"),
        "cwd": str(Path.cwd()),
        "root_writable": root_writable,
        "interfaces": sorted(path.name for path in Path("/sys/class/net").iterdir()),
        "control_secrets": [name for name in os.environ if name.startswith(("PLATFORM_", "SANDBOX_", "CONNECTOR_"))],
        "docker_socket": Path("/var/run/docker.sock").exists(),
        "instance": instance,
    }


@server.tool()
def write_private(value: str) -> dict:
    Path("private.txt").write_text(value)
    Path("/home/runner/private.txt").write_text(value)
    return {"saved": True}


@server.tool()
def read_private() -> dict:
    return {
        "workspace": Path("private.txt").read_text() if Path("private.txt").exists() else None,
        "home": Path("/home/runner/private.txt").read_text() if Path("/home/runner/private.txt").exists() else None,
    }


@server.tool()
def list_attachments() -> dict:
    """List only the immutable input manifest imported for this synthetic Run."""
    path = Path("/workspace/attachments/manifest.json")
    return {"files": json.loads(path.read_text(encoding="utf-8"))["files"] if path.exists() else []}


@server.tool()
def read_attachment(artifact_id: str) -> dict:
    """Synthetic local-file reader: bounded text preview and digest, not an external integration."""
    id = str(UUID(artifact_id))
    record = next((item for item in list_attachments()["files"] if item["artifact_id"] == id), None)
    if record is None:
        return {"available": False}
    data = Path("/workspace/attachments", id).read_bytes()
    try:
        preview = data[:2048].decode("utf-8")
    except UnicodeError:
        preview = None
    return {
        "available": True,
        "artifact_id": id,
        "source_path": record["source_path"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "preview": preview,
        "truncated": len(data) > 2048,
    }


@server.tool()
def replace_attachment_for_test(artifact_id: str, value: str) -> dict:
    """Isolation-test-only mutator; never added to the Gateway's approved read-tool list."""
    path = Path("/workspace/attachments", str(UUID(artifact_id)))
    if not path.exists():
        return {"saved": False}
    path.write_text(value, encoding="utf-8")
    return {"saved": True}


if __name__ == "__main__":
    server.run(transport="stdio")
