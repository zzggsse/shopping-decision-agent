"""让 MCP server 可以用 `python -m app.mcp` 直接启动。"""

import asyncio

from .server import serve_stdio

if __name__ == "__main__":
    asyncio.run(serve_stdio())
