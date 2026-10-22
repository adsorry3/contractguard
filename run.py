"""开发启动入口。

在 PyCharm 里右键本文件 → Run 'run'，就能启动服务，不用敲任何 conda 命令。

为什么需要这个文件：
直接运行 app/main.py 时，Python 会把 sys.path 指向 app/ 目录，
导致 `from app.config import ...` 找不到包（ModuleNotFoundError: No module named 'app'）。
这个文件放在项目根目录，先把项目根目录加进 sys.path，再启动 uvicorn。
"""

import sys
from pathlib import Path

# 把项目根目录加入模块搜索路径（必须在导入 app 之前）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(ROOT / "app")],
    )
