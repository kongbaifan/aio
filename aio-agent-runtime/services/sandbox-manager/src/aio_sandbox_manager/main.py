"""Start one trusted manager per locked state directory. Use TLS/mTLS at the approved private proxy."""

import os
import uvicorn
from .api import from_environment


def main():
    host = os.environ.get("SANDBOX_MANAGER_HOST", "127.0.0.1")
    port = int(os.environ.get("SANDBOX_MANAGER_PORT", "8094"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid private manager port")
    uvicorn.run(from_environment(), host=host, port=port, workers=1)


if __name__ == "__main__":
    main()
