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


# ---- the guardrail check, served from the same public tunnel ------------------
# Otari carries the guardrail verdict but needs an HTTPS endpoint to run the check against. This
# service is reachable through the same tunnel as the MCP tool, so one public URL serves both.
from guard_server.app import ValidateRequest, _scan  # noqa: E402


@app.get("/profiles")
def guard_profiles() -> list[dict[str, str]]:
    return [{"name": "prompt-injection", "guardrail_name": "fine-print-document-injection"}]


@app.post("/validate")
async def guard_validate(request: Request) -> JSONResponse:
    payload = await request.json()
    req = ValidateRequest(**payload)
    hits = _scan(req.input_text or "")
    if hits:
        reasons = "; ".join(dict.fromkeys(hits))
        return JSONResponse(
            {
                "profile": req.profile,
                "result": {
                    "valid": False,
                    "explanation": f"This document talks to the tool reading it: {reasons}.",
                    "score": 0.99,
                },
            }
        )
    return JSONResponse({"profile": req.profile, "result": {"valid": True, "explanation": None, "score": 0.01}})
