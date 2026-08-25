"""MCP 对照实现:把工具层通过 Model Context Protocol 暴露出去。

默认不启用(USE_MCP=1 打开)。存在的意义是证明工具层的抽象足够干净 ——
接 MCP 不需要改任何一个工具的实现。

为什么改动这么小:
  toolkit.py 早就把工具收敛成「schema + handler」两段式,而这正好是 MCP 的形状。

      本项目                          MCP 协议
      tool_schemas()          <-->    tools/list  响应
      execute_tool(ctx,n,a)   <-->    tools/call  分发

两种运行方式:
  1. **独立进程**(标准用法):`python -m app.mcp.server`,
     用 stdio 传输,可被 Claude Desktop 等任意 MCP 宿主直接连接
  2. **进程内桥接**(本项目开关打开时用):不起子进程,
     直接把调用包装成 MCP 的 Tool/CallToolResult 数据结构再解回来

为什么默认关闭:
  单体应用里工具只有自己用,跨进程调用带来的收益(跨宿主复用、
  第三方工具即插即用)抵不上进程管理与序列化的成本。
  真会打开的场景是:想把「比价」「配料分析」开放给别的 agent 复用。
"""

from __future__ import annotations

import json
from typing import Any


def build_mcp_tools() -> list[dict[str, Any]]:
    """把本项目的工具 schema 转成 MCP tools/list 的格式。

    两者几乎同构:OpenAI 的 function.parameters 就是 MCP 的 inputSchema。
    """
    from ..agent.toolkit import tool_schemas

    tools = []
    for item in tool_schemas():
        function = item["function"]
        tools.append({
            "name": function["name"],
            "description": function.get("description", ""),
            "inputSchema": function.get("parameters") or {
                "type": "object", "properties": {},
            },
        })
    return tools


def to_openai_schema(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """反向转换:MCP tools/list -> OpenAI tools。

    有了这一步,远端 MCP 工具就能和本地工具混在同一张工具表里喂给模型,
    决策层完全感知不到某个工具其实在另一个进程。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema")
                or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


class InProcessMCPBridge:
    """进程内 MCP 桥接:走完整的 MCP 数据结构,但不起子进程。

    目的是在不引入进程管理复杂度的前提下,真实地跑一遍
    「schema 转换 -> 调用 -> CallToolResult 解包」这条链路,
    从而验证工具层确实符合 MCP 契约。

    与真实跨进程 MCP 的唯一差别是没有 stdio 序列化那一跳。
    """

    def __init__(self) -> None:
        self._tools = build_mcp_tools()

    def list_tools(self) -> list[dict[str, Any]]:
        """对应 MCP 的 tools/list。"""
        return self._tools

    def openai_tools(self) -> list[dict[str, Any]]:
        """给决策层用的 OpenAI 格式工具表(经过 MCP 往返转换)。"""
        return to_openai_schema(self._tools)

    async def call_tool(self, ctx, name: str, arguments: dict) -> dict:
        """对应 MCP 的 tools/call。

        MCP 的返回是 content 数组(TextContent 等),所以这里要:
        执行 -> 序列化成 TextContent -> 再解回本项目的 dict 结果。
        这一步刻意保留,因为它正是跨进程时真实发生的损耗。
        """
        from ..agent.toolkit import execute_tool

        result = await execute_tool(ctx, name, arguments)

        # 打包成 MCP CallToolResult 的形状
        is_error = result.get("type") == "tool_error"
        packed = {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
            "isError": is_error,
        }
        # 解包回本项目结构
        return _unpack(packed, fallback=result)


def _unpack(packed: dict, fallback: dict) -> dict:
    """把 MCP CallToolResult 解回本项目的工具结果结构。

    解析失败时退回原始结果并说明原因,而不是抛错中断整轮 ——
    与工具层「单点失败不中断」的原则保持一致。
    """
    try:
        blocks = packed.get("content") or []
        for block in blocks:
            if block.get("type") == "text":
                return json.loads(block["text"])
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return fallback


def build_server():
    """构建一个标准 MCP server,可被任意 MCP 宿主通过 stdio 连接。

    单独放在这里而不是模块顶层导入,是为了让没装 mcp 包时其余功能照常可用。
    """
    from mcp.server import Server
    import mcp.types as types

    from ..adapters.base import create_adapters
    from ..agent.toolkit import Context as AgentContext
    from ..agent.toolkit import execute_tool
    from ..domain.models import ShoppingTask
    from ..profile.store import profile_store

    # MCP 宿主是无状态调用方,这里为它维持一个长驻任务上下文
    task = ShoppingTask(task_id="mcp-session")
    ctx = AgentContext(
        task=task, profiles=profile_store, adapters=create_adapters("mock")
    )

    async def on_list_tools(request_ctx, params):
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool["name"],
                    description=tool["description"],
                    inputSchema=tool["inputSchema"],
                )
                for tool in build_mcp_tools()
            ]
        )

    async def on_call_tool(request_ctx, params):
        result = await execute_tool(ctx, params.name, dict(params.arguments or {}))
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, default=str),
                )
            ],
            isError=result.get("type") == "tool_error",
        )

    return Server(
        name="shopping-decision-agent",
        version="1.0.0",
        title="购物决策 Agent 工具集",
        instructions=(
            "提供全品类比价、配料表分析、健康档案硬过滤等购物决策工具。"
            "只做决策与跳转,不代下单、不碰支付。"
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def serve_stdio() -> None:
    """以 stdio 传输运行 MCP server(标准用法)。"""
    from mcp.server import stdio_server

    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
