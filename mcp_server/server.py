"""Fine Print's MCP server: one tool, one job — does this IFSC exist, and whose is it.

Speaks the streamable-HTTP MCP subset Otari needs: initialize, tools/list, tools/call. No SDK, so
there is nothing between the tool call and the answer. Run it on port 8099 and point
FINE_PRINT_MCP_URL at a public tunnel of it, or leave that blank and the app calls it directly.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

DATA = json.loads((Path(__file__).parent / "data" / "ifsc.json").read_text())["codes"]
PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "lookup_ifsc",
        "description": (
            "Look up an Indian bank IFSC code. Returns the bank, branch and city that the code belongs to, "
            "or found=false when the code does not exist. Use this before anyone sends money to an account "
            "printed on a bill."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ifsc": {"type": "string", "description": "11-character IFSC, e.g. SBIN0001234"}},
            "required": ["ifsc"],
        },
    }
]

app = FastAPI(title="Fine Print MCP", version="0.1.0")


def _result(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}


def _call(name: str, arguments: dict) -> dict:
    if name != "lookup_ifsc":
        return {"content": [{"type": "text", "text": json.dumps({"error": f"no such tool: {name}"})}], "isError": True}
    code = str(arguments.get("ifsc") or "").strip().upper()
    record = DATA.get(code)
    if not record:
        return _result({"found": False, "ifsc": code, "reason": "not present in the bank directory"})
    return _result({"found": True, "ifsc": code, **record})


@app.get("/mcp")
def mcp_get() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})


@app.post("/mcp")
async def mcp_post(request: Request):
    body = await request.json()
    method = body.get("method")
    request_id = body.get("id")
    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "fine-print-lookup", "version": "0.1.0"},
                },
            }
        )
    if method in {"notifications/initialized", "notifications/cancelled"} or request_id is None:
        return Response(status_code=202)
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    if method == "tools/call":
        params = body.get("params") or {}
        result = _call(str(params.get("name") or ""), params.get("arguments") or {})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {}})
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}},
        status_code=200,
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True, "tools": [t["name"] for t in TOOLS], "records": len(DATA)}


def run() -> None:
    import uvicorn

    uvicorn.run("mcp_server.server:app", host="0.0.0.0", port=8099, reload=False)
