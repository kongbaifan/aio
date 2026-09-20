# AIO Runtime Policy

Pure versioned dependency-manifest and Ed25519 approval contracts shared by platform and Manager. This package contains no Docker, network, package-installation or arbitrary execution interface. Private signing bytes are supplied only to the operator signing helper; runtime consumers use independently configured public trust keys.

Install from project root: `python -m pip install -e packages/runtime-policy`.
Run contracts: `python -m pytest packages/runtime-policy/tests -q`.

Wire format, purpose restrictions, wheel/manifest bounds, trust separation and limits are documented in [the runtime contract](../../docs/engineering/platform-dependency-runtime-contract.md). Checked-in examples/verification use test-purpose approvals only; the signing key is never put into an execution cell.
