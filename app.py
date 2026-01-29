from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import time
from collections import deque
from typing import Any, Dict

import httpx
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
DEFAULT_TIMEOUT_S = float(os.getenv("ETH_RPC_TIMEOUT_S", "30"))
DEFAULT_ALLOWED_HOSTS = [
    "meowblock-mcp.xeift.tw",
    "meowblock-mcp.xeift.tw:*",
    "meow-block.xeift.tw",
    "meow-block.xeift.tw:*",
]
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_WINDOW_S = 60.0
_rate_limit_lock = asyncio.Lock()
_rate_limit_log: dict[str, deque[float]] = {}


def _parse_allowed_hosts(value: str) -> list[str]:
    hosts = [item.strip() for item in value.split(",") if item.strip()]
    return hosts or DEFAULT_ALLOWED_HOSTS


def _make_fastmcp() -> FastMCP:
    kwargs: Dict[str, Any] = {"name": "meowblock"}
    sig = inspect.signature(FastMCP.__init__)
    if "stateless_http" in sig.parameters:
        kwargs["stateless_http"] = True
    if "json_response" in sig.parameters:
        kwargs["json_response"] = True
    if "transport_security" in sig.parameters:
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_parse_allowed_hosts(os.getenv("MCP_ALLOWED_HOSTS", "")),
            allowed_origins=[],
        )
    return FastMCP(**kwargs)


mcp = _make_fastmcp()


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def call_eth_rpc(
    method: str,
    params: list[Any] | dict[str, Any] | None = None,
    request_id: int | str = 1,
) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": [] if params is None else params,
        "id": request_id,
    }
    headers = {"Content-Type": "application/json", "User-Agent": "MeowBlock/1.0"}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
        response = await client.post(ETH_RPC_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


async def get_eth_block_number() -> int:
    response_json = await call_eth_rpc("eth_blockNumber")
    if "error" in response_json:
        raise RuntimeError(f"RPC Error: {response_json['error']['message']}")
    return int(response_json["result"], 16)


@mcp.tool(name="meow")
async def meow() -> str:
    block_number = await get_eth_block_number()
    return f"Meow {block_number}"


@mcp.tool(name="eth_rpc")
async def eth_rpc(
    method: str,
    params: list[Any] | dict[str, Any] | None = None,
    request_id: int | str = 1,
) -> dict[str, Any]:
    return await call_eth_rpc(method=method, params=params, request_id=request_id)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = _get_client_ip(request)
    now = time.monotonic()
    async with _rate_limit_lock:
        timestamps = _rate_limit_log.get(client_ip)
        if timestamps is None:
            timestamps = deque()
            _rate_limit_log[client_ip] = timestamps
        cutoff = now - RATE_LIMIT_WINDOW_S
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
            retry_after = max(
                0, int(RATE_LIMIT_WINDOW_S - (now - timestamps[0]))
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )
        timestamps.append(now)
    return await call_next(request)

app.mount("/", mcp.streamable_http_app())


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
