"""Project-local operator helper: derive Gateway/BFF references from a fixed Manager template.

This never runs or installs the MCP server. Build/review the image separately.
"""

import argparse
import json
from pathlib import Path

from aio_sandbox_manager.stdio_contracts import StdioProfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--endpoint-id", required=True)
    parser.add_argument("--read-tool", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Generated endpoint example must stay in this project")
    raw = args.profiles.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Template catalog exceeds its bound")
    profiles = [StdioProfile.model_validate(value) for value in json.loads(raw)["profiles"]]
    matches = [profile for profile in profiles if profile.id == args.profile_id]
    if len(matches) != 1:
        raise ValueError("Select one exact approved template")
    profile = matches[0]
    from aio_connector_gateway.contracts import Endpoint

    reference = {
        "profile_id": profile.id,
        "image_digest": profile.image_digest,
        "template_digest": profile.template_digest,
        "credential_env": profile.credential_env,
        "network_profile": "none",
    }
    if profile.input_policy != "none":
        reference["input_policy"] = profile.input_policy
    endpoint = Endpoint(
        args.endpoint_id,
        "stdio://" + profile.id,
        frozenset(args.read_tool),
        transport="stdio",
        stdio=reference,
        authentication="bearer" if profile.credential_env else "none",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": endpoint.id,
                        "url": endpoint.url,
                        "transport": "stdio",
                        "authentication": endpoint.authentication,
                        "read_tools": sorted(endpoint.read_tools),
                        "timeout_seconds": min(30, profile.max_timeout_seconds),
                        "stdio": reference,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Wrote approved reference", output, "without executing server code")


if __name__ == "__main__":
    main()
