"""Functional probe in a bounded cell; this is not a malware or vulnerability certification."""

import importlib
import json
import os
from pathlib import Path
import sys

manifest = json.loads(Path("/opt/aio-runtime/manifest.json").read_text(encoding="utf-8"))
sys.path.append("/opt/aio-deps")
loaded = []
for package in manifest["packages"]:
    for name in package["imports"]:
        importlib.import_module(name)
        loaded.append(name)
if "numpy" in loaded and "pandas" in loaded:
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame({"value": [1, 2, 3]})
    assert float(np.mean(frame["value"].to_numpy())) == 2.0
for path in ["/opt/aio-deps/must-not-write", "/usr/local/lib/must-not-write"]:
    try:
        Path(path).write_bytes(b"forbidden")
    except OSError:
        continue
    raise ValueError("RUNTIME_WRITABLE")
assert os.getuid() == 10001
assert sorted(path.name for path in Path("/sys/class/net").iterdir()) == ["lo"]
assert not Path("/var/run/docker.sock").exists()
print(
    json.dumps(
        {
            "schema_version": 1,
            "state": "passed",
            "imports": loaded,
            "uid": os.getuid(),
            "network": "none",
            "readonly_runtime": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
)
