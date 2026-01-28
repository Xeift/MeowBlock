#!/usr/bin/env python3
"""
MeowBlock MCP Server with SSE transport
Minimal working implementation
"""

import asyncio
import json
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.sse import SseServerTransport
import uvicorn


ETH_RPC_URL = "https://eth.llamarpc.com"


async def get_eth_block_number() -> int:
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    data = json.dumps(payload).encode('utf-8')
    req = Request(ETH_RPC_URL, data=data, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'MeowBlock/1.0'
    })
    
    loop = asyncio.get_event_loop()
    response_data = await loop.run_in_executor(None, lambda: urlopen(req).read())
    response_json = json.loads(response_data.decode('utf-8'))
    
    if "error" in response_json:
        raise Exception(f"RPC Error: {response_json['error']['message']}")
    
    return int(response_json["result"], 16)


# Create MCP server
server = Server("meowblock")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [types.Tool(
        name="meow",
        description="Returns 'Meow' followed by the current Ethereum block number",
        inputSchema={"type": "object", "properties": {}, "required": []}
    )]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "meow":
        try:
            block_number = await get_eth_block_number()
            return [types.TextContent(type="text", text=f"Meow {block_number}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    raise ValueError(f"Unknown tool: {name}")


# Create SSE transport
sse_transport = SseServerTransport("/messages")

# Router ASGI app
async def app(scope, receive, send):
    path = scope.get('path', '')
    method = scope.get('method', '')
    
    print(f"🔍 Request: {method} {path}")
    
    if path == '/mcp':
        print(f"  → Method: {method}")
        if method == 'GET':
            print("  → Handling SSE connection")
            # SSE connection endpoint - this is a context manager
            async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
                print("  → SSE connected, running MCP server")
                init_options = InitializationOptions(
                    server_name="meowblock",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    )
                )
                await server.run(read_stream, write_stream, init_options)
                print("  → MCP server finished")
        elif method == 'POST':
            print("  → POST to /mcp, redirecting to handle_post_message")
            await sse_transport.handle_post_message(scope, receive, send)
        else:
            print(f"  → Unsupported method: {method}")
            await send({
                'type': 'http.response.start',
                'status': 405,
                'headers': [[b'content-type', b'text/plain']],
            })
            await send({
                'type': 'http.response.body',
                'body': b'Method Not Allowed',
            })
    elif path == '/messages':
        print(f"  → Handling POST message")
        # Client messages endpoint
        await sse_transport.handle_post_message(scope, receive, send)
    else:
        # 404 for other paths
        print(f"  → 404: {path}")
        await send({
            'type': 'http.response.start',
            'status': 404,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Not Found',
        })




async def main():
    print("🐱 MeowBlock MCP Server")
    print("=" * 60)
    print("🔌 MCP Endpoint: http://0.0.0.0:8000/mcp")
    print("📮 Messages: http://0.0.0.0:8000/messages")
    print("=" * 60)
    print()
    
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    uvicorn_server = uvicorn.Server(config)
    await uvicorn_server.serve()



if __name__ == "__main__":
    asyncio.run(main())
