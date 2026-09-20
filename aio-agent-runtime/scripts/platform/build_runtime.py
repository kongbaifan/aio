"""Operator/isolated CI entry point: build a reviewed offline-wheel runtime candidate, not an approval."""

import argparse
from pathlib import Path
from uuid import uuid4

from runtime_artifacts import build, download_wheels, read_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--download-pinned-pypi-wheels",
        action="store_true",
        help="Optional explicit opaque-byte fetch; never resolve versions or execute package metadata on the host",
    )
    args = parser.parse_args()
    manifest = read_manifest(args.lock)
    if args.download_pinned_pypi_wheels:
        download_wheels(manifest, args.wheelhouse)
    candidate = build(manifest, args.wheelhouse, args.output, verification="runtime-" + uuid4().hex)
    print("Runtime candidate awaits independent operator review:", candidate["image_digest"], args.output)


if __name__ == "__main__":
    main()
