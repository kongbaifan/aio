# Fixed offline-wheel runtime builder

This is an operator/CI image template, **not** a Web tool or a Worker-side package installer. The fixed base, wheel bytes/hashes, recipe, package versions and resulting image are immutable inputs to independent Ed25519 approval. Run environments remain non-root, no-network, read-only and quota-limited.

Wheel archive interpretation and installation happen only inside the non-root build stage. Final dependencies are root-owned under `/opt/aio-deps`, separate from the trusted interpreter; no `.pth` or startup-module override is allowed. Inventory and functional probes run in separate bounded cells. The Manager only adds the fixed dependency directory to its untrusted user process, never PID1 or the control host.

From the project root, install trusted management dependencies with `python -m pip install -e packages/runtime-policy -e services/sandbox-manager`. Then see `scripts/platform/build_runtime.py`, `approve_runtime.py` and `export_runtime_profile.py`. The reference lock is `config/runtime-locks/analytics-python.json`; the matching business-capability example is `config/skill-packages/example-analytics.json`.

`python scripts/platform/test_dependency_runtime.py` builds a **synthetic test-only approval**, runs real Docker assertions, and writes private verification profiles/public trust keys under `var/verification/`. `python scripts/platform/test_sandbox.py` also verifies the complete platform pipeline. A test approval is rejected by production consumers.

Build outputs/contexts are intentionally retained as operator evidence in `var/runtime-candidates`; they are not a production retention/garbage-collection service. Company deployment requires a dedicated, hardened build node and explicit source/vulnerability/license review. A CycloneDX inventory, signature or smoke pass is **not** a malware or zero-vulnerability certification. Full contracts and remaining gates: [dependency runtime contract](../../docs/engineering/platform-dependency-runtime-contract.md).
