"""项目根目录定位。

裸机和容器里的目录层级不一样，不能用固定的 parents[N]：

    裸机   <repo>/apps/local-harness/app/llm/providers.py  -> parents[4]
    容器   /app/app/llm/providers.py                       -> parents[4] 越界 IndexError

所以改成向上找标志物。config/ 是模型目录所在，两种部署下都必须存在，用它做判据。
"""

from __future__ import annotations

import os
from pathlib import Path


# 判定某一层是不是项目根的标志物。config/ 放 models.json，是运行时真正要读的东西。
_ROOT_MARKERS = ("config",)


def find_root(start: Path) -> Path | None:
    """从 start 向上找第一个含标志物的目录；找不到返回 None。"""
    for parent in start.parents:
        if any((parent / marker).is_dir() for marker in _ROOT_MARKERS):
            return parent
    return None


def project_root() -> Path:
    """返回项目根目录。

    优先用 HARNESS_PROJECT_ROOT 显式指定；否则从本文件向上找标志物；
    都找不到时退回到 harness 应用目录（app 的上一级），保证不抛异常。
    """
    explicit = os.environ.get("HARNESS_PROJECT_ROOT", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    here = Path(__file__).resolve()
    found = find_root(here)
    if found is not None:
        return found
    # app/paths.py -> app -> local-harness（容器里是 /app）
    return here.parents[1]


def config_dir() -> Path:
    return project_root() / "config"


def models_json_path() -> Path:
    return config_dir() / "models.json"


def models_local_json_path() -> Path:
    return config_dir() / "models.local.json"
