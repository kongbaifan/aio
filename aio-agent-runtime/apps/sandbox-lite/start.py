import uvicorn
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from server import app

if __name__ == "__main__":
    # 本地默认只监听回环地址；容器通过环境变量显式改为内部网卡。
    host = os.environ.get("SANDBOX_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("SANDBOX_PORT", "8081"))
    except ValueError:
        port = 8081
    uvicorn.run(app, host=host, port=port, log_level="info")
