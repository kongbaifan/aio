# AIO Sandbox Manager (trusted execution management service)

This package owns Docker privileges; do **not** install it inside user compute cells or expose its private port to employees. The platform Worker uses its HTTP API and the manager calls the platform's narrow `/internal/v1/sandbox/authorize` endpoint to revalidate current Run/action permissions. No control database credential or business/model Secret is sent into compute cells.

## Current implementation

Python compute, isolated document parsing, and separately approved MCP stdio cells: no network, untrusted UID10001 separated from the non-root UID10000 PID1 lifetime watchdog, read-only image, fixed capabilities/limits, owned tmpfs-backed workspace volume with byte/inode quotas, bounded output, hard deadlines, externally frozen artifact collection and verified container/volume removal. A state directory can be owned by only one live manager process. Compute and stdio share the Manager's admission limits, not each other's workspace or identity.

Read-only HTTP MCP credentials live in the separate connector gateway; document parsing uses its own approved profile and authority slot. MCP stdio uses a distinct fixed image/startup/dependency template and private `/v1/stdio/open`, `/rpc`, `/stop` API. Gateway hands a scoped credential through transient Docker exec stdin, never Docker Config.Env/Cmd or a Manager transcript. The credential-bearing process can read its own credential; it must not be treated as credential-free compute. There is no API/Worker/Gateway host subprocess fallback.

One Run + generation + connection reuses one stdio process. Discovery has its own short-lived cell; different users/Runs do not share HOME, workspace, pipes or tokens. Manager restart/process loss does not silently recreate/replay that session. Repeated RPC identities are rejected, and only digests/lifecycle facts enter the stdio journal; known business results remain encrypted in Gateway. See [the stdio contract](../../docs/engineering/platform-mcp-stdio-contract.md). Controlled stdio egress, browser and additional runtime profiles remain pending.

An explicitly approved `input_policy=run_attachments` template may receive at most 32 selected Run attachments totaling 4 MiB, only when the user also opted in for that Run. A v2 metadata-only spec binds UUID-derived destinations and checksums; raw bytes are transient first-open data, never journaled. The Manager checks all files before allocation, copies them before starting MCP, and rejects re-injection into a ready process. Copies can be changed by the process without changing the original Artifact; they are not a shared or host-mounted filesystem. Input-enabled profiles require at least 8 MiB workspace. See [the attachment contract](../../docs/engineering/platform-mcp-stdio-input-contract.md); default no-input v1 digests are preserved.

The private `/v1/cells/checkpoint` operation exports only under an exact platform-approved approval boundary, confirms writer destruction and binds its purpose in the journal. A checkpoint export cannot be reused as a final publication. After durable platform confirmation, `/v1/cells/acknowledge` purges retained input/export/result payloads. These operations preserve files, not process memory. See the [filesystem handoff contract](../../docs/engineering/platform-workspace-checkpoint-contract.md); deploy compatible v11 API, Worker, Gateway and Manager together. Suspending a Run stops its stdio processes rather than claiming to checkpoint their memory.

## Install and start

From `aio-agent-runtime`:

```text
python -m pip install -e packages/runtime-policy -e services/sandbox-manager
python -m aio_sandbox_manager.main
```

Required environment:

- `SANDBOX_MANAGER_STATE_ROOT`: explicit absolute private manager journal root.
- `SANDBOX_MANAGER_PROFILES`: absolute path to operator-approved profile JSON. Each profile has an ID and a pinned local image ID (`sha256:...`); bounds may be narrowed by the operator.
- `SANDBOX_RUNTIME_TRUST_KEYS`: optional explicit absolute public-key JSON for signed dependency profiles; required if a profile includes `runtime_approval`. No signing private key is passed to this service. Test-purpose approvals require the explicit test Manager mode and are rejected by production consumers.
- `SANDBOX_MANAGER_TOKEN`: strong incoming Worker service token, at least 32 ASCII characters.
- `SANDBOX_STDIO_PROFILES`: optional absolute path to a bounded approved stdio template JSON (1–8 distinct profiles). Profile IDs must not overlap compute IDs; local image/dependency/template digests must agree.
- `SANDBOX_CONNECTOR_TOKEN`: required when stdio is configured; dedicated incoming Gateway token, distinct from the ordinary Manager and control tokens. Neither incoming token can call the other role's API.
- `SANDBOX_CONTROL_URL`: approved HTTPS control API origin; default production behavior forbids HTTP.
- `SANDBOX_CONTROL_TOKEN`: distinct outgoing control-authority token; match platform `PLATFORM_MANAGER_CONTROL_TOKEN`.
- `SANDBOX_MANAGER_HOST` / `SANDBOX_MANAGER_PORT`: default `127.0.0.1:8094`; any remote deployment requires an approved private TLS proxy and network ACLs.
- `SANDBOX_MANAGER_MODE=test`: permits loopback HTTP only for isolated integration testing, not remote plain HTTP.

Never put real values in git or user-readable Skill files. The service inherits Docker client endpoint configuration from the operator environment, not from requests.

Signed offline-wheel environments are supported in ordinary compute/Skill cells. The Manager verifies the independent signing trust and immutable image/manifest labels; only the user process adds `/opt/aio-deps`. PID1 uses fixed Python `-I -S` and a different UID, never the dependency environment. All old hard limits/cleanup rules remain in force; signatures are not a malware or zero-vulnerability guarantee. See [the dependency runtime contract](../../docs/engineering/platform-dependency-runtime-contract.md) and the separate operator-only `build_runtime.py` / `approve_runtime.py` / `export_runtime_profile.py` workflow. Do not run company image builds on API/Worker nodes.

The platform API and Worker both need the same trusted persistent `PLATFORM_ARTIFACT_ROOT` storage service/root for the current local-blob backend. Do not bind this directory into compute cells. A multi-node deployment should use a properly permissioned shared/object-storage backend rather than assume one machine's directory is globally durable.

## Verification

```text
python scripts/platform/test_sandbox.py
```

This generates `var/verification/sandbox-profile.json`, `document-profile.json`, `stdio-profile.json` with the exact locally built image digests and JUnit reports. `python scripts/platform/test_stdio.py` runs the isolated stdio slice alone. All inputs are synthetic and all test resources have an isolated verification label. The stdio reference server uses the official MCP SDK but is not a production company integration.

See [the platform sandbox code contract](../../docs/engineering/platform-sandbox-contract.md) and [current implementation status](../../docs/implementation/README.md) for the verified scope and remaining work. A green basic container test is not a full production isolation/HA approval.
