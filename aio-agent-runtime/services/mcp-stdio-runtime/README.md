# MCP stdio reference image

This is an explicitly synthetic/reference server built with the official MCP SDK. Its Python dependencies are version-locked and the image carries the SHA-256 of `requirements.lock`; the Manager requires both the immutable image digest and the approved startup template digest.

`scripts/platform/test_stdio.py` builds the image and exercises actual Docker stdin/stdout, user identity, private HOME/workspace, bounded malformed output and cleanup. It writes an exact local example to `var/verification/stdio-profile.json`.

The Manager launches the registered program as UID10001 under a separate UID10000 lifetime watchdog, read-only root, no network, hard memory/CPU/PID/tmpfs limits and no host bind or Docker socket. The scoped synthetic credential arrives over the exec stdin pipe, never through Docker Config.Env/Cmd or a manager transcript. The process can read this credential: it is a credential-bearing execution domain, not a general compute sandbox.

The reference tools are not a production integration. `write_private` exists for isolation tests and is not automatically exposed by the Gateway's approved-tool list. To deploy another server, publish a reviewed image, dependency lock declaration and fixed executable/argument template. Runtime `npm install`, `pip install`, arbitrary commands and network profiles are not accepted through the Web/API.

The generated reference profile explicitly allows `input_policy=run_attachments`, but every Run still defaults to no file delivery. When the user also opts in, at most 32 files / 4 MiB are copied to fixed `attachments/<artifact UUID>` paths with a metadata manifest. `list_attachments` and `read_attachment` demonstrate scoped local access; the reader returns a full-file checksum and at most 2 KiB of text preview, not a general document parser or binary-output importer. `replace_attachment_for_test` exists only to prove that repeated initialization cannot overwrite a process's private copies; never include it in the Gateway's approved read-tool list. The immutable source files and project head are unchanged. See [the input contract](../../docs/engineering/platform-mcp-stdio-input-contract.md).

See [stdio contract](../../docs/engineering/platform-mcp-stdio-contract.md) for lifecycle, authority and remaining limits.
