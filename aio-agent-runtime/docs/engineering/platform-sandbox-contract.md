# Sandbox Manager / Artifact Code Contract

## 1. Scope and current boundary

Implemented paths: `services/sandbox-manager`, `services/run-executor`, platform `app/execution`, `app/workspaces`, v3–v5 migrations and authenticated upload/download/internal authorization routes. The dedicated `skill/validation` slot reuses the no-network profile, but its authority is a Skill validation Job, not an invented business Run; see [Skill contract](platform-skill-contract.md).

The approved compute role is **Python with no network and no business credentials**. Isolated knowledge parsing has a separate approved image/slot and contract. Credential-bearing MCP stdio now has its own fixed template, private authority/token boundary and no-network cells; it is not ordinary compute and its approved process can read its delegated credential. See [the stdio contract](platform-mcp-stdio-contract.md). Node, browser, additional parser profiles, controlled package/stdio egress, stronger VM runtimes and production hardening are still pending. This is not a claim that the complete enterprise platform or all security gates are finished.

## 2. Signatures

```text
SandboxManager.ensure(CellSpec) -> owned ready container binding
SandboxManager.execute(ExecuteRequest) -> bounded stdout/stderr/exit and command identity
SandboxManager.finalize(CellSpec) -> checked immutable file bundle after stopping writer
SandboxManager.stop(CellSpec) -> externally confirmed container and volume deletion
SandboxManager.reap() -> expire/revoke/quarantine owned execution targets
SandboxCoordinator.authorize(operation,payload) -> current PG run/lease/action authorization
ArtifactService.create_upload/principal upload -> private immutable attachment
ArtifactService.stage_export(...) -> staged, not yet downloadable artifacts
ArtifactService.publish(transaction,run,generation,principal) -> atomically published workspace version
```

## 3. Trust and resource contracts

- Approved dependency images add a reviewed exact wheel environment under root-owned `/opt/aio-deps`. A pure shared signature contract and separate operator public-key stores bind image and manifest; test approvals cannot authorize production. The watchdog uses Python `-I -S`; only the untrusted user process gains the fixed dependency path. See [the dependency runtime contract](platform-dependency-runtime-contract.md). This is not an online host installer or a complete supply-chain security claim.

- Docker API privileges exist only in the dedicated manager. The Agent/API/Worker does not execute Docker commands or user Python locally.
- Manager incoming service token and outgoing control-authority token are distinct credentials, never passed to compute cells.
- The control callback validates current actor, Project, Agent, Tool, generation, worker lease, exact ActionSpec code and binding spec against PostgreSQL.
- Cleanup/status can operate after actor revocation, but returning files or executing code requires current business authorization.
- For Team, the control-authority callback permits final export only in the synthesis stage, not merely because an intermediate step has a final checkpoint. New generations must not adopt live older-generation cells. The v9 private filesystem checkpoint path verifies retirement, sources and bytes before a new binding can run; incomplete handoffs still stop before another action.
- The compute image is pinned, root filesystem read-only, user code runs as UID/GID 10001, all capabilities dropped, no-new-privileges, no host mounts/sockets, network_mode=none.
- A distinct non-root UID/GID 10000 owns PID1 and a fixed-lifetime watchdog. UID10001 cannot stop/extend it. Real tests confirm idle cells expire even when the manager reaper is not running. Container/volume deletion still requires manager reconciliation.
- CPU, memory/swap, PID, file descriptors, private HOME/tmp and workspace byte/inode quotas are configured and inspected. Workspace uses an owned local-driver **tmpfs volume with size/nr_inodes**, not an unbounded ordinary named volume.
- All Docker container/volume operations check exact manager installation/spec/Run labels. Test cleanup uses a fresh verification ID and never deletes unrelated user resources.
- One manager owns its journal directory via an OS file lock. Commands and allocations are journaled; duplicate dispatches return recorded results or explicit unknown, not repeated execution.
- Lost ready cells are not silently recreated with empty state. Expired/revoked/uncertain targets are destroyed or quarantined; capacity remains occupied until known cleanup.
- A returned stdout JSON string is untrusted output and cannot approve actions or mark a lease destroyed. Runtime state is checked through the external Docker API.

## 4. Artifact and storage contracts

- Object storage root is explicit, absolute, not mounted into user cells. Objects are scoped by org and SHA-256; hash knowledge does not grant access.
- Writes are immutable with collision/integrity checks. Reads validate type, size and checksum; no caller-provided host path is opened.
- Upload slots are user/project scoped, bounded and expiring. Org/project persistent-storage quotas include pending uploads and reserved Run output, not just the per-file size.
- Before writing a blob, the upload slot is bound to an immutable content hash. A conflicting retry writes no new orphan file. Failed/interrupted uploads retain their quota hold until retry or explicit cleanup.
- Generated exports are also bound to an immutable manifest and reserved output budget before writing persistent blobs. Incomplete exports retain their accounting hold; automatic orphan/retention cleanup is still pending.
- The local object backend keeps a minimum free-space watermark, and manager retained inputs, exports and command-result payloads have a shared capacity limit. This is not a replacement for final production capacity/retention governance.
- Raw uploads are **opaque attachments**, not falsely marked malware-scanned. Preview/Office parsing is not performed in the control process. Generated output is structurally checked and also attachment-only.
- Artifact metadata/read and download permissions are distinct. Project sharing does not automatically grant a private file or Session.
- Input resources and provenance roots are reauthorized; revoking a source blocks derived reads and publication.
- Per-project writer lease prevents two different Runs from sharing a writable workspace; each uses a private cell copied from the fixed project version plus explicit inputs.
- Manager pauses the actual container before collecting workspace files through the Docker daemon. Symlinks/hardlinks/devices/escaped paths, oversized output and credential-shaped files are rejected. Sparse files are bounded by a separate collector byte budget; every archive stream is closed even on failure.
- Candidate blobs and artifact rows remain staged until Run finish checks writer lease, generation, base head CAS, confirmed cell cleanup and current source authorization in the publication transaction.
- Manager export is cached durably for retry after reply loss; published files persist independently of container destruction.

## 5. Two real runtime findings and fixes

### Direct tmpfs and Docker archive visibility

The first real container smoke test wrote a file successfully but Docker `get_archive('/workspace')` returned an empty filesystem when `/workspace` used the container's direct tmpfs mount. Treating this as a successful empty export would silently lose artifacts.

The implementation now uses an independently managed **tmpfs-backed Docker volume** with explicit size/inode options. The daemon can inspect that mounted volume, and real tests assert the generated file bytes/hash after the cell is destroyed. This is not equivalent to assuming any Docker named volume has a hard quota.

### Output-flood stop deadlock

When the bounded output queue filled, waiting for container shutdown before releasing the queue could leave the exec attachment undrained. Docker still reported the target active.

The reader stop signal is now set before waiting for termination, so the bounded queue cannot block attachment closure. The manager polls the same exact resource until termination is confirmed; it does not pretend the initial kill acknowledgement proves cleanup. A real flood regression verifies bounded returned bytes and absence of the owned container afterward.

## 6. Validation matrix

| Condition | Result |
|---|---|
| Unapproved profile/digest/privileged parameter | Reject before creating a cell |
| Duplicate dispatch with changed code/spec | COMMAND_CONFLICT, no second exec |
| Expired or revoked actor/lease/action | Deny new execution; periodic guard stops active work |
| Missing/lost ready target | CELL_LOST, no empty-state recreation |
| CPU/PID/memory/filesystem/timeout/output limits | Kernel or external manager enforces the configured bound |
| Output flood | Bounded output, terminate/reclaim the whole cell |
| Symlink/special-file export | UNSAFE_ARTIFACT, no publication |
| Failed publication/head conflict | Candidate stays private; no overwrite of committed version |
| Different user/org/source revoked | Deny download and derived access |
| No configured artifact storage or manager | Explicit unavailable; no legacy filesystem or host-shell fallback |

## 7. Verification commands

From the project root, install only into the project virtual environment:

```text
python -m pip install -r apps/local-harness/requirements-dev.txt
python -m pip install -e services/sandbox-manager
python scripts/platform/test_sandbox.py
```

`test_sandbox.py` builds the pinned compute image, records its actual digest, runs real Docker isolation tests and the full PostgreSQL/Worker/artifact integration suite, then checks and removes only resources labeled for that verification run. It leaves the built image for reproducibility, not user containers or volumes.

The compute environment is deliberately no-network. Model behavior is synthetic in the full pipeline tests; the actual user code, containers, quotas, files, database authorization and artifact publication are real. External business providers and production security certification remain unverified.

## 8. Required regression coverage

- `services/sandbox-manager/tests`: non-root/read-only/capabilities, no host mounts/network, two-user file/HOME isolation, real inputs/export, idempotent dispatch, byte and inode exhaustion, PID cap, timeout/process-tree cleanup, output flood, symlink export denial, revocation, capacity, API auth, singleton journal, lost-cell refusal and concurrent allocation.
- `tests/platform/test_artifacts.py`: immutable hashes, traversal/symlink ancestry, private uploads, repeat upload conflict, source revocation, separate metadata/download permissions, binary CSRF and attachment headers.
- `tests/platform/test_sandbox_pipeline.py`: durable Worker to authenticated manager to actual Docker compute to private persisted Artifact; platform manager-authority scope/spec checks.
- Existing Run, approval, RLS, migration, legacy Harness/Sandbox and front-end tests remain mandatory.
