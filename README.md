# MeowBlock
<img src="https://raw.githubusercontent.com/Xeift/MeowBlock/main/pfp.png" alt="pfp" width="200">

MeowBlock is a lightweight FastAPI-based MCP server that exposes Ethereum JSON-RPC through both MCP tools and a plain HTTP JSON-RPC proxy.

It is designed to be simple, self-hostable, and easy to integrate with MCP clients, agents, and scripts that need Ethereum mainnet access.

It is also registered under ERC-8004 on Ethereum mainnet as agent #6809 ( [8004scan](https://www.8004scan.io/agents/ethereum/6809) | [Agentscan](https://agentscan.info/agents/41fd8a57-0369-4350-aa92-71375c7ad6c1) ).

## Features

- Exposes Ethereum JSON-RPC through MCP
- Provides a generic `eth_rpc` tool for arbitrary Ethereum JSON-RPC methods
- Includes a simple `meow` tool that returns the latest Ethereum block number
- Offers a plain HTTP JSON-RPC proxy at `/rpc`
- Includes a health check endpoint at `/healthz`
- Supports fallback Ethereum RPC endpoints
- Includes basic IP-based rate limiting
- Ready for deployment on Vercel

## Use MeowBlock in ChatGPT Web!
<img width="1920" height="1080" alt="gpt" src="https://github.com/user-attachments/assets/0b0b7950-182a-4580-aefe-6e6dc0325949" />

You will need ChatGPT Plus to use custom connectors.
<details>
<summary>Steps (click to expand)</summary>
<img width="1920" height="1080" alt="1" src="https://github.com/user-attachments/assets/2e2a29c6-7648-49f1-8e01-f98654b42e13" />
<img width="1920" height="1080" alt="2" src="https://github.com/user-attachments/assets/6eae25a1-f17f-4b68-bd0a-78e412aff44f" />
<img width="1920" height="1080" alt="3" src="https://github.com/user-attachments/assets/16757260-110d-44ea-a0ab-2c1d432f0558" />
<img width="1920" height="1080" alt="4" src="https://github.com/user-attachments/assets/278161d2-8d9e-4fca-b079-b9bc90cf0512" />
<img width="1920" height="1080" alt="5" src="https://github.com/user-attachments/assets/c8686cef-46b9-413e-b99e-c4e8c03db76d" />
<img width="1920" height="1080" alt="6" src="https://github.com/user-attachments/assets/422fe707-d450-4168-9fb3-97cf5bbc413a" />
</details>

## MCP Tools

### `meow`

Returns the latest Ethereum block number in a meow format.

Example output:

```text
Meow 21987654
```

### `eth_rpc`

Calls any Ethereum JSON-RPC method.

Parameters:

- `method` — Ethereum JSON-RPC method name
- `params` — optional parameters array or object
- `request_id` — optional JSON-RPC request ID

## HTTP Endpoints

### `POST /rpc`

A generic Ethereum JSON-RPC proxy.

Example request:

```bash
curl -X POST http://localhost:8000/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "eth_blockNumber",
    "params": [],
    "id": 1
  }'
```

Example response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": "0x14f9d12"
}
```

### `GET /healthz`

Health check endpoint.

Example response:

```json
{
  "ok": true
}
```

### `/mcp`

Streamable HTTP MCP endpoint.

Use this endpoint with MCP-compatible clients.

## Public Service

If you want to use the hosted service directly, these endpoints are exposed publicly:

- MCP: `https://meow-block.xeift.tw/mcp`
- HTTP JSON-RPC: `https://meow-block.xeift.tw/rpc`
- Health: `https://meow-block.xeift.tw/healthz`

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── registration.json
├── oasf-record.json
├── vercel.json
└── LICENSE
```

## Requirements

- Python 3.10+
- `fastapi`
- `uvicorn`
- `httpx`
- `mcp[cli]`

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Local Development

Clone the repository:

```bash
git clone https://github.com/Xeift/MeowBlock.git
cd MeowBlock
```

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the server:

```bash
python app.py
```

By default, the app runs on:

```text
http://localhost:8000
```

## Environment Variables

The following environment variables are supported:

| Name | Default | Description |
|---|---|---|
| `ETH_RPC_URL` | `https://eth.llamarpc.com` | Primary Ethereum RPC endpoint |
| `ETH_RPC_TIMEOUT_S` | `30` | Timeout for upstream Ethereum RPC requests |
| `RATE_LIMIT_PER_MINUTE` | `60` | Per-IP request limit per minute |
| `MCP_ALLOWED_HOSTS` | built-in defaults | Allowed hosts for MCP transport security |
| `PORT` | `8000` | Server port |

## Deployment

This repository includes a `vercel.json` configuration and is ready to deploy on Vercel.

### Deploy on Vercel

1. Import the repository into Vercel
2. Make sure Python dependencies are installed from `requirements.txt`
3. Optionally configure:
   - `ETH_RPC_URL`
   - `ETH_RPC_TIMEOUT_S`
   - `RATE_LIMIT_PER_MINUTE`
   - `MCP_ALLOWED_HOSTS`

## Rate Limiting

The public server applies a basic per-IP rate limit.

Default:

```text
60 requests per minute per IP
```

## Notes

- The server forwards Ethereum JSON-RPC requests to upstream Ethereum RPC providers
- If the primary endpoint fails, it retries using fallback RPC endpoints
- The `/rpc` endpoint expects a JSON object with at least a `method` field
- Invalid JSON or malformed payloads return an error response

## Disclaimer
This project is **NOT** associated with any crypto projects. Always DYOR.

Any token or coins associated with any other crypto project send to the agent's wallet address will be burned. I've already burned like 1177.37 USD😂
- [0x953ecb426aba7209be59be560645098a19fd5239b582f1c81afbd44fcee7e02c](https://bscscan.com/tx/0x953ecb426aba7209be59be560645098a19fd5239b582f1c81afbd44fcee7e02c) (Binance Chain)
- [0xdca436ff32804d8767864ef712cab804a1e285431718de69f708ea94a7f32e3f](https://bscscan.com/tx/0xdca436ff32804d8767864ef712cab804a1e285431718de69f708ea94a7f32e3f) (Binance Chain)
- [0x17e818ba5d1e7e1bdc8f70cdb2058720334a7e62c7742098f935d3e2c7b29b58](https://basescan.org/tx/0x17e818ba5d1e7e1bdc8f70cdb2058720334a7e62c7742098f935d3e2c7b29b58) (Base)

## License

MIT
