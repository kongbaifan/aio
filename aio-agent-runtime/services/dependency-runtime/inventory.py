"""Fixed inventory probe, run with -I -S in a read-only, no-network cell; no dependency imports."""

import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import re
import stat
import sys
import sysconfig

# Only trusted base pip's vendored metadata parser is used. No .pth/site execution or installed-package imports.
sys.path.append(sysconfig.get_path("purelib"))
from pip._vendor.packaging.requirements import Requirement  # noqa: E402
from pip._vendor.packaging.version import Version  # noqa: E402

manifest = json.loads(Path("/opt/aio-runtime/manifest.json").read_text(encoding="utf-8"))
root = Path("/opt/aio-deps")
installed = {}
for dist in distributions(path=[str(root)]):
    name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
    if name in installed:
        raise ValueError("DUPLICATE_DISTRIBUTION")
    installed[name] = {"version": dist.version, "requires": dist.requires or []}
expected = {item["name"]: item["version"] for item in manifest["packages"]}
if {name: value["version"] for name, value in installed.items()} != expected:
    raise ValueError("INSTALLED_SET_MISMATCH")
for value in installed.values():
    for raw in value["requires"]:
        requirement = Requirement(raw)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = re.sub(r"[-_.]+", "-", requirement.name).lower()
        if requirement.url or name not in expected or Version(expected[name]) not in requirement.specifier:
            raise ValueError("DEPENDENCY_CLOSURE_INVALID")
records, count, total = [], 0, 0
for directory, dirs, files in os.walk(root, followlinks=False):
    for name in dirs + files:
        path = Path(directory, name)
        st = path.lstat()
        if (
            stat.S_ISLNK(st.st_mode)
            or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode))
            or st.st_uid != 0
            or st.st_mode & 0o022
        ):
            raise ValueError("RUNTIME_TREE_NOT_IMMUTABLE")
        if stat.S_ISREG(st.st_mode):
            count += 1
            total += st.st_size
            if count > 20000 or total > 512 * 1024 * 1024 or path.suffix.lower() == ".pth":
                raise ValueError("RUNTIME_TREE_QUOTA_OR_STARTUP_HOOK")
            with path.open("rb") as file:
                records.append(
                    [path.relative_to(root).as_posix(), st.st_size, hashlib.file_digest(file, "sha256").hexdigest()]
                )
if sys.version_info[:2] != (3, 12) or sys.platform != "linux" or os.uname().machine != "x86_64":
    raise ValueError("RUNTIME_PLATFORM_MISMATCH")
print(
    json.dumps(
        {
            "schema_version": 1,
            "state": "passed",
            "python": sys.version.split()[0],
            "platform": "linux-x86_64",
            "packages": expected,
            "files": count,
            "bytes": total,
            "tree_sha256": hashlib.sha256(json.dumps(sorted(records), separators=(",", ":")).encode()).hexdigest(),
            "dependency_closure_verified": True,
            "package_code_imported": False,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
