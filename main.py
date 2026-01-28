#!/usr/bin/env python3
"""
MeowBlock MCP Server - FastAPI implementation
Based on standard MCP over SSE patterns
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from fastapi import FastAPI, Request as FastAPIRequest, Response
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import uvicorn


# --- Ethereum RPC Functions ---
ETH_RPC_URL = "https://eth.llamarpc.com"

async def get_eth_block_number() -> int:
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    data = json.dumps(payload).encode('utf-8')
    req = Request(ETH_RPC_URL, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'MeowBlock/1.0'})
    
    loop = asyncio.get_event_loop()
    response_data = await loop.run_in_executor(None, lambda: urlopen(req).read())
    response_json = json.loads(response_data.decode('utf-8'))
    
    if "error" in response_json:
        raise Exception(f"RPC Error: {response_json['error']['message']}")
    
    return int(response_json["result"], 16)


# --- MCP Server & Tool Definitions ---
mcp_server = Server("meowblock")

@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="meow",
            description="Returns 'Meow' followed by the current Ethereum block number",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool execution"""
    if name == "meow":
        try:
            block_number = await get_eth_block_number()
            return [TextContent(type="text", text=f"Meow {block_number}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    raise ValueError(f"Unknown tool: {name}")


# --- FastAPI Application ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("🐱 MeowBlock MCP Server Starting...")
    yield
    # Shutdown logic
    print("🐱 MeowBlock MCP Server Stopping...")

app = FastAPI(lifespan=lifespan)

# Store active SSE transports: endpoint_id -> SseServerTransport
sse_transports: Dict[str, SseServerTransport] = {}

@app.get("/meow")
async def simple_meow():
    """Simple GET endpoint for testing without MCP"""
    try:
        block = await get_eth_block_number()
        return {"message": f"Meow {block}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/mcp")
async def handle_sse(request: FastAPIRequest):
    """
    Handle SSE connection.
    This creates a transport, assigns it an endpoint ID, and starts an MCP session.
    """
    
    # We use the official SseServerTransport logic but adapt it for FastAPI/sse-starlette
    # 1. Create a new transport bound to the /messages endpoint
    transport = SseServerTransport("/messages")
    
    async def event_generator():
        # 2. Use the transport's connect_sse method to establish the initial stream
        #    But instead of yielding directly, we need to run the MCP server loop
        
        # We need a way to run the MCP server concurrently with generating events
        # The transport.connect_sse is designed as a context manager that yields streams
        async with transport.connect_sse(
            request.scope, 
            request.receive, 
            request._send
        ) as streams:
            read_stream, write_stream = streams
            
            # Store the transport instance so we can handle POST messages later
            # Since SseServerTransport generates a session ID internally, we need to map it
            # But wait, connection is stateful.
            # In a real Any-MCP implementation, we usually run the mcp_server.run in a background task
            # and yield events from the write_stream.
            
            # For simplicity with the standard SDK, we let it run properly
            # The issue: connect_sse yields (read, write) streams.
            # We want to run mcp_server.run(read, write, options)
            # AND we need to handle the POST messages.
            
            # Let's fix this properly:
            # SseServerTransport handles the session ID generation. 
            # We actually need to execute the server.run inside here.
            
            init_options = InitializationOptions(
                server_name="meowblock",
                server_version="1.0.0",
                capabilities=mcp_server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
            
            # Run the server
            await mcp_server.run(read_stream, write_stream, init_options)

    # Note: connect_sse handles the EventSource response internal logic usually
    # But since we are using FastAPI, we delegate to the transport's native handler if possible
    # However, the user specifically asked for "Any-MCP" style which uses sse-starlette.
    
    # Actually, the standard SDK's SseServerTransport.connect_sse IS an ASGI app.
    # We can just return it directly if we mount it, but we want it on a specific route.
    
    # Let's use the transport directly as the handler, it's easier and correct!
    await transport.connect_sse(request.scope, request.receive, request._send)

@app.post("/messages")
async def handle_messages(request: FastAPIRequest):
    """Handle client messages (POST)"""
    # We need to find the correct transport. 
    # With the standard SDK, SseServerTransport.handle_post_message handles this by 
    # looking up the session ID in the query string (added by transport.connect_sse).
    
    # But wait, we created a NEW transport instance in /mcp every time.
    # This is statelessness problem.
    # The standard SDK implementation expects the SAME transport instance to handle both.
    
    # FIX: We need a GLOBAL transport instance if we want to support multiple clients simply,
    # OR we need to map session IDs to transport instances.
    
    # The standard SseServerTransport IS capable of handling multiple connections *if* it's the same instance?
    # No, usually you make one per connection or manage them.
    # Actually checking source: SseServerTransport is designed for one session usually?
    # Let's use a global singleton for simplicity as Vercel effectively spins up new instances anyway for scale,
    # but for a single concurrent session logic, let's try a singleton.
    
    await _global_transport.handle_post_message(request.scope, request.receive, request._send)


# --- Global Transport Fix ---
# To make this work in Vercel (stateless), we have a problem:
# The transport object created in GET /mcp is lost when that request finishes (or hangs open).
# But POST /messages comes in a DIFFERENT request.
#
# How does standard MCP SDK solve this?
# It stores sessions in memory.
# In Vercel, memory is preserved *if* the instance stays warm, but not guaranteed.
# However, within the scope of a single "server" process, we can use a global.

_global_transport = SseServerTransport("/messages")

# We override the app routes to use the transport directly for these paths
# This bypasses FastAPI's wrappers around these specific endpoints to ensure
# raw ASGI access which the SDK expects.

# However, we still want FastAPI for /meow and docs.
# So we mount or overwrite.

from starlette.routing import Route
app.router.routes = [
    r for r in app.router.routes if r.path not in ["/mcp", "/messages"]
]
app.add_route("/mcp", _global_transport.connect_sse, methods=["GET"])
app.add_route("/messages", _global_transport.handle_post_message, methods=["POST"])


# Start the MCP server logic in background?
# No, run() needs to be called *per connection*.
# SseServerTransport doesn't run the logic itself, it just gives us streams.
# We need to hook into the connection establishment.

# RE-RE-FACTOR: The "Any-MCP" way (panz2018/fastapi_mcp_sse) logic:
# It creates a custom endpoint that yields events.

async def mcp_sse_handler(request: FastAPIRequest):
    async with _global_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        read_stream, write_stream = streams
        init_options = InitializationOptions(
            server_name="meowblock",
            server_version="1.0.0",
            capabilities=mcp_server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            )
        )
        await mcp_server.run(read_stream, write_stream, init_options)

# Overwrite the route with our wrapper that actually runs the server
# But wait, `connect_sse` IS the ASGI app that handles the connection. 
# It expects to be awaited and it takes over the response.
# We cannot wrap it easily in a python `await` if we want to run code *concurrently* with it?
# Actually `connect_sse` is a context manager returning streams!
# If used as `transport.connect_sse(scope, ...)` it fails (as we saw).
# It MUST be used as `async with transport.connect_sse(...)` INSIDE an endpoint.

# Final correct implementation:
@app.get("/mcp")
async def handle_mcp_sse(request: FastAPIRequest):
    """MCP SSE Endpoint"""
    async with _global_transport.connect_sse(
        request.scope, 
        request.receive, 
        request._send
    ) as streams:
        read_stream, write_stream = streams
        await mcp_server.run(
            read_stream, 
            write_stream, 
            InitializationOptions(
                server_name="meowblock",
                server_version="1.0.0",
                capabilities=mcp_server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )

# Remove the manual route add above and use this FastAPI endpoint
# And keep the global transport for message handling
app.router.routes = [r for r in app.router.routes if r.path != "/messages"]
app.add_route("/messages", _global_transport.handle_post_message, methods=["POST"])

# Clean up any mess in router
app.router.routes = [r for r in app.router.routes if r.path != "/mcp"]
app.add_api_route("/mcp", handle_mcp_sse, methods=["GET"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
