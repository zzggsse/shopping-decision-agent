"""本地配置加载：把项目根目录的 local.env 读进环境变量。

为什么自己写而不用 python-dotenv：只需要「KEY=VALUE 逐行读」这么点功能，
不值得为此多一个依赖。

两个原则：
  1. **已存在的环境变量优先**。你在终端里 `$env:XXX=` 临时指定的值，
     不应该被文件默默覆盖。
  2. **文件不存在不是错误**。不配任何凭据也要能完整跑。

凭据只会出现在 local.env（已 gitignore），不写入任何会入库的文件。
"""

from __future__ import annotations

import os
import pathlib

#: 项目根目录：backend/app/env.py -> backend/app -> backend -> 根
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCAL_ENV = PROJECT_ROOT / "local.env"


def load_local_env(path: pathlib.Path | None = None) -> list[str]:
    """读 local.env 写进 os.environ，返回本次真正生效的变量名。

    支持 KEY=VALUE，`#` 开头的行为注释，值两端的引号会被剔除。
    """
    target = path or LOCAL_ENV
    if not target.exists():
        return []

    applied: list[str] = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            continue
        # 终端里显式指定的优先于文件
        if os.getenv(key):
            continue
        os.environ[key] = value
        applied.append(key)
    return applied
