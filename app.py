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
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

DEFAULT_PRIMARY_RPC_URL = "https://eth.llamarpc.com"
DEFAULT_FALLBACK_RPC_URLS = [
    "https://eth.drpc.org",
    "https://ethereum-mainnet.gateway.tatum.io",
    "https://eth-mainnet.nodereal.io/v1/1659dfb40aa24bbb8153a677b98064d7",
    "https://eth1.lava.build",
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth.api.onfinality.io/public",
    "https://mainnet.gateway.tenderly.co",
    "https://eth.blockrazor.xyz",
    "https://ethereum-rpc.publicnode.com",
    "https://rpc.fullsend.to",
    "https://virginia.rpc.blxrbdn.com",
    "https://eth.rpc.blxrbdn.com",
    "https://singapore.rpc.blxrbdn.com",
    "https://uk.rpc.blxrbdn.com",
    "https://eth.llamarpc.com",
    "https://1rpc.io/eth",
    "https://eth.merkle.io",
    "https://eth-mainnet.public.blastapi.io",
    "https://rpc.eth.gateway.fm",
    "https://ethereum-json-rpc.stakely.io",
    "https://0xrpc.io/eth",
    "https://eth-mainnet.rpcfast.com?api_key=xbhWBI1Wkguk8SNMu1bvvLurPGLXmgwYeC4S6g2H7WdwFigZSmPWVZRxrskEQwIf",
    "https://ethereum-public.nodies.app",
    "https://eth.meowrpc.com",
    "https://endpoints.omniatech.io/v1/eth/mainnet/public",
    "https://ethereum.public.blockpi.network/v1/rpc/public",
    "https://public-eth.nownodes.io",
    "https://rpc.flashbots.net/fast",
    "https://api.zan.top/eth-mainnet",
    "https://ethereum.rpc.subquery.network/public",
    "https://rpc.mevblocker.io",
    "https://rpc.mevblocker.io/noreverts",
    "https://rpc.mevblocker.io/fullprivacy",
    "https://rpc.mevblocker.io/fast",
    "https://rpc.flashbots.net",
]
ETH_RPC_URLS = list(
    dict.fromkeys(
        url
        for url in [
            os.getenv("ETH_RPC_URL", DEFAULT_PRIMARY_RPC_URL),
            *DEFAULT_FALLBACK_RPC_URLS,
        ]
        if url
    )
)
DEFAULT_TIMEOUT_S = float(os.getenv("ETH_RPC_TIMEOUT_S", "30"))
DEFAULT_ALLOWED_HOSTS = [
    "meow-block.xeift.tw",
    "meow-block.xeift.tw:*",
    "localhost",
    "localhost:*",
    "127.0.0.1",
    "127.0.0.1:*",
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
    if "streamable_http_path" in sig.parameters:
        kwargs["streamable_http_path"] = "/"
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
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
        for rpc_url in ETH_RPC_URLS:
            try:
                response = await client.post(rpc_url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                continue
    raise RuntimeError("All Ethereum RPC endpoints failed") from last_error


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

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.post("/rpc")
async def rpc_proxy(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "Expected JSON object"})
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        return JSONResponse(status_code=400, content={"error": "Missing JSON-RPC method"})
    params = payload.get("params")
    request_id = payload.get("id", 1)
    try:
        return await call_eth_rpc(method=method, params=params, request_id=request_id)
    except RuntimeError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
