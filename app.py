from __future__ import annotations

import contextlib
import inspect
import os
from typing import Any, Dict

import httpx
import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")
DEFAULT_TIMEOUT_S = float(os.getenv("ETH_RPC_TIMEOUT_S", "30"))
MCP_MOUNT_PATH = os.getenv("MCP_MOUNT_PATH", "/")


def _normalize_mount_path(path: str) -> str:
    if path.startswith("/"):
        return path
    return f"/{path}"


def _parse_allowed_hosts(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _make_fastmcp() -> FastMCP:
    kwargs: Dict[str, Any] = {"name": "meowblock"}
    sig = inspect.signature(FastMCP.__init__)
    if "stateless_http" in sig.parameters:
        kwargs["stateless_http"] = True
    if "json_response" in sig.parameters:
        kwargs["json_response"] = True
    if "transport_security" in sig.parameters:
        allowed_hosts = _parse_allowed_hosts(os.getenv("MCP_ALLOWED_HOSTS", ""))
        if allowed_hosts:
            kwargs["transport_security"] = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=allowed_hosts,
                allowed_origins=[],
            )
    return FastMCP(**kwargs)


mcp = _make_fastmcp()


async def get_eth_block_number() -> int:
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    headers = {"Content-Type": "application/json", "User-Agent": "MeowBlock/1.0"}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
        response = await client.post(ETH_RPC_URL, json=payload, headers=headers)
    response.raise_for_status()
    response_json = response.json()
    if "error" in response_json:
        raise RuntimeError(f"RPC Error: {response_json['error']['message']}")
    return int(response_json["result"], 16)


@mcp.tool(name="meow")
async def meow() -> str:
    block_number = await get_eth_block_number()
    return f"Meow {block_number}"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)

app.mount(_normalize_mount_path(MCP_MOUNT_PATH), mcp.streamable_http_app())


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
