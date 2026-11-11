"""A stand-in Otari gateway, used only to test this app without spending credit.

It speaks the same wire format the real gateway does: an OpenAI-shaped completion, the Otari
response headers, `otari_tool_calls` for gateway-run tools, and a 403 guardrail_violation. The
sandbox calls it receives are genuinely executed here, so the arithmetic that comes back is real
Python output, not a canned number.

This file is test scaffolding. The app in `app/` never imports it, and the demo video uses the
hosted gateway.
"""
from __future__ import annotations

import httpx

import base64
import contextlib
import hashlib
import io
import json
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PROTOCOL_HEADERS = {"Otari-Guardrails": json.dumps([{"profile": "prompt-injection", "verdict": "allow"}])}

READER_DOCS: dict[str, dict] = {
    "bill_clean": {
        "doc_type": "utility bill",
        "sender_name": "NIRMAL NAGAR WATER BOARD",
        "sender_address": None,
        "addressee": "H. Kotra, 14 Nirmal Nagar, Flat 3B",
        "reference_no": "778812",
        "issue_date": "2026-11-01",
        "due_date": "2026-11-20",
        "total_stated": "516.40",
        "amount_payable": "516.40",
        "late_fee_text": "Pay before the due date to avoid a 2% late fee.",
        "line_items": [
            {"label": "Water charges, October 2026", "amount": "420.00"},
            {"label": "Meter rent", "amount": "60.00"},
            {"label": "Sewer cess", "amount": "36.40"},
        ],
        "payment_upi": "nnwb@okhdfcbank",
        "payment_account": "50100234567890",
        "payment_ifsc": "SBIN0001234",
        "payment_note": "Cash at any Nirmal Nagar counter.",
        "what_they_want": "Pay 516.40 for water and sewerage charges by 20 November 2026.",
        "asks_for_money": True,
    },
    "bill_doctored": {
        "doc_type": "utility bill",
        "sender_name": "NIRMAL NAGAR WATER BOARD",
        "sender_address": None,
        "addressee": "H. Kotra, 14 Nirmal Nagar, Flat 3B",
        "reference_no": "778812",
        "issue_date": "2026-11-01",
        "due_date": "2026-11-20",
        "total_stated": "616.40",
        "amount_payable": "616.40",
        "late_fee_text": "Pay before the due date to avoid a 2% late fee.",
        "line_items": [
            {"label": "Water charges, October 2026", "amount": "420.00"},
            {"label": "Meter rent", "amount": "60.00"},
            {"label": "Sewer cess", "amount": "36.40"},
        ],
        "payment_upi": "nnwb@okhdfcbank",
        "payment_account": "50200098765432",
        "payment_ifsc": "HDFC0000001",
        "payment_note": "Cash at any Nirmal Nagar counter.",
        "what_they_want": "Pay 616.40 for water and sewerage charges by 20 November 2026.",
        "asks_for_money": True,
    },
    "letter_insurance": {
        "doc_type": "insurance letter",
        "sender_name": "Sunrise Multispeciality Hospital",
        "sender_address": None,
        "addressee": None,
        "reference_no": "SH/PA/4471",
        "issue_date": None,
        "due_date": "2026-11-18",
        "total_stated": None,
        "amount_payable": None,
        "late_fee_text": "If the documents are not received by 18 Nov 2026, the pre-authorisation lapses and the claim will be closed.",
        "line_items": [],
        "payment_upi": None,
        "payment_account": None,
        "payment_ifsc": None,
        "payment_note": "Send documents to billing@sunrisehospital.demo",
        "what_they_want": "Send the discharge summary and itemised bill to the hospital within seven days.",
        "asks_for_money": False,
    },
}


def _index() -> tuple[dict[str, str], dict[str, str]]:
    """Map both the image bytes and the plain-text transcription of each fixture to its name."""
    by_hash: dict[str, str] = {}
    by_text: dict[str, str] = {}
    for png in sorted(FIXTURES.glob("*.png")):
        name = png.stem
        if png.exists():
            by_hash[hashlib.sha256(png.read_bytes()).hexdigest()] = name
        txt = FIXTURES / f"{name}.txt"
        if txt.exists():
            by_text[txt.read_text().strip()[:120]] = name
    return by_hash, by_text


def _identify(payload: dict) -> str | None:
    by_hash, by_text = _index()
    for message in payload.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            head = content.split("---", 1)[-1].strip()
            if head:
                if "ASSISTANT INSTRUCTIONS" in head:
                    return "notice_injection"
                for probe, name in by_text.items():
                    if probe and probe[:60] in head:
                        return name
        elif isinstance(content, list):
            for part in content:
                if part.get("type") != "image_url":
                    continue
                url = (part.get("image_url") or {}).get("url", "")
                if "," in url:
                    raw = base64.b64decode(url.split(",", 1)[1])
                    name = by_hash.get(hashlib.sha256(raw).hexdigest())
                    if name:
                        return name
    return None


def _page_text(name: str) -> str:
    """The fixture's plain-text transcription stands in for the pixels' own words."""
    txt = FIXTURES / f"{name}.txt"
    return txt.read_text() if txt.exists() else ""


def _run(code: str) -> dict:
    """Execute the sandbox snippet the pipeline asked for, and return its real stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<sandbox>", "exec"), {"__name__": "__sandbox__"})
    return {"output": buf.getvalue().strip(), "exit_status": 0}


app = FastAPI(title="stub gateway")


@app.get("/v1/models")
def models() -> dict:
    return {
        "data": [
            {"id": "stub:mistral-small-3.2-vision", "input_modalities": ["text", "image"], "open_weights": True},
            {"id": "stub:qwen3-32b", "input_modalities": ["text"], "open_weights": True},
        ]
    }


def _completion(payload: dict, request_id: str, text: str, tool_calls: list | None = None) -> JSONResponse:
    return JSONResponse(
        {
            "id": f"chatcmpl-{request_id[:8]}",
            "object": "chat.completion",
            "model": payload.get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 260, "cost_usd": 0.0012, "pricing_source": "stub"},
            "otari_tool_calls": tool_calls or [],
        },
        headers={
            "Otari-Request-Id": request_id,
            "Otari-Cost-Usd": "0.0012",
            "Otari-Pricing-Source": "stub",
            **PROTOCOL_HEADERS,
        },
    )


def _mcp_call(servers: list[dict], ifsc: str) -> dict | None:
    """Do what the gateway does with an MCP server: call the tool and hand back its text."""
    for server in servers or []:
        url = str(server.get("url") or "")
        if not url:
            continue
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "lookup_ifsc", "arguments": {"ifsc": ifsc}},
        }
        try:
            r = httpx.post(url, json=body, timeout=8, headers={"Accept": "application/json, text/event-stream"})
            payload = r.json()
            text = payload["result"]["content"][0]["text"]
            return {"text": text, "server": server.get("name") or "lookup", "url": url}
        except Exception:
            continue
    return None


@app.post("/v1/chat/completions")
async def completions(request: Request):
    payload = await request.json()
    request_id = str(uuid.uuid4())
    blob = json.dumps(payload)
    tools = [t.get("type") for t in payload.get("tools") or []]
    servers = payload.get("mcp_servers") or []

    if servers:
        ifsc = ""
        for message in reversed(payload.get("messages") or []):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                ifsc = message["content"].strip().split()[-1]
                break
        got = _mcp_call(servers, ifsc)
        if got:
            try:
                body = json.loads(got["text"])
            except Exception:
                body = {"text": got["text"]}
            return _completion(
                payload,
                request_id,
                got["text"],
                [{"call": {"server": got["server"], "tool": "lookup_ifsc", "arguments": {"ifsc": ifsc}}, "result": body}],
            )

    if "otari_code_execution" in tools:
        task = ""
        for message in payload.get("messages") or []:
            if isinstance(message.get("content"), str):
                task = message["content"]
        code = task.split("arithmetic in your head.", 1)[-1].strip()
        result = _run(code)
        return _completion(
            payload,
            request_id,
            result["output"],
            [{"call": {"code": code}, "result": result}],
        )

    system = " ".join(
        m.get("content", "") if isinstance(m.get("content"), str) else "" for m in payload.get("messages") or []
    )
    if "You are the second reader" in system:
        return _completion(payload, request_id, json.dumps({"agrees": True, "corrections": {}, "unsupported": [], "notes": ""}))

    name = _identify(payload)
    if name == "notice_injection" or "ASSISTANT INSTRUCTIONS" in blob:
        return JSONResponse(
            {
                "error": {
                    "message": "request blocked by guardrail prompt-injection",
                    "code": "guardrail_violation",
                }
            },
            status_code=403,
            headers={
                "Otari-Request-Id": request_id,
                "Otari-Guardrails": json.dumps(
                    [{"profile": "prompt-injection", "verdict": "block", "reason": "instruction override in document body"}]
                ),
            },
        )
    doc = dict(READER_DOCS.get(name or "bill_clean", READER_DOCS["bill_clean"]))
    doc["page_text"] = _page_text(name or "bill_clean")
    return _completion(payload, request_id, json.dumps(doc))
