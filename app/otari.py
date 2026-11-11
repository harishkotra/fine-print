"""Thin client over the Otari gateway.

Deliberately not the OpenAI SDK: this app needs the parts of the request and response that an
SDK hides, namely the guardrail verdict, the request id, the billed cost, the model that actually
served the request, and the sandbox tool's real output. Every one of those ends up on screen.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config


class OtariError(Exception):
    def __init__(self, message: str, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class ToolCall:
    kind: str
    code: str = ""
    output: str = ""
    exit_status: Any = None
    url: str = ""
    server: str = ""
    tool: str = ""

    def as_dict(self) -> dict:
        d = {"kind": self.kind}
        if self.code:
            d["code"] = self.code
        if self.output:
            d["output"] = self.output
        if self.exit_status is not None:
            d["exit_status"] = self.exit_status
        if self.url:
            d["url"] = self.url
        if self.server or self.tool:
            d["server"] = self.server
            d["tool"] = self.tool
        return d


@dataclass
class Completion:
    text: str
    model: str
    served_by: str
    request_id: str
    cost_usd: float
    pricing_source: str
    latency_ms: int
    guardrails: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def receipt(self, step: str) -> dict:
        return {
            "step": step,
            "model": self.model,
            "served_by": self.served_by,
            "request_id": self.request_id,
            "cost_usd": round(self.cost_usd, 6),
            "pricing_source": self.pricing_source,
            "latency_ms": self.latency_ms,
            "guardrails": self.guardrails,
            "tool_calls": [t.as_dict() for t in self.tool_calls],
        }


def _money(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tool_calls(payload: dict) -> list[ToolCall]:
    """Otari reports gateway-run tool activity under otari_tool_calls.

    The shape is read defensively: any dict carrying a code/output pair is a sandbox call, any
    dict carrying a url is a fetch, and anything else that names a server is an MCP call.
    """
    out: list[ToolCall] = []
    for call in payload.get("otari_tool_calls") or []:
        if not isinstance(call, dict):
            continue
        body = call.get("call") if isinstance(call.get("call"), dict) else call
        result = call.get("result") if isinstance(call.get("result"), dict) else {}
        merged = {**body, **result}
        if merged.get("code") or merged.get("output"):
            out.append(
                ToolCall(
                    kind="code_execution",
                    code=str(merged.get("code") or ""),
                    output=str(merged.get("output") or ""),
                    exit_status=merged.get("exit_status", merged.get("exit_code")),
                )
            )
        elif merged.get("url"):
            out.append(ToolCall(kind="web_fetch", url=str(merged.get("url")), output=str(merged.get("output") or "")))
        elif merged.get("server") or merged.get("mcp_server"):
            out.append(
                ToolCall(
                    kind="mcp",
                    server=str(merged.get("server") or merged.get("mcp_server") or ""),
                    tool=str(merged.get("tool") or merged.get("name") or ""),
                    output=str(merged.get("output") or merged.get("result") or ""),
                )
            )
    return out


def _text_of(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


class Otari:
    def __init__(self, key: str | None = None, base_url: str | None = None, timeout: float = 180.0):
        self.key = key if key is not None else config.OTARI_API_KEY
        self.base_url = (base_url or config.OTARI_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._catalog: list[dict] | None = None

    # -- discovery ---------------------------------------------------------------------------

    def catalog(self) -> list[dict]:
        if self._catalog is not None:
            return self._catalog
        body = self._get("/models")
        rows = body.get("data") or body.get("models") or []
        self._catalog = [r for r in rows if isinstance(r, dict)]
        return self._catalog

    def pick(self, modality: str = "text", open_weight: bool = True, exclude: set[str] | None = None) -> str:
        """Choose a catalogue id by modality, preferring open weights and skipping known-bad ids."""
        exclude = exclude or set()
        scored: list[tuple[int, str]] = []
        for row in self.catalog():
            model_id = str(row.get("id") or row.get("name") or "")
            if not model_id or model_id in exclude:
                continue
            inputs = row.get("input_modalities") or row.get("modalities") or row.get("architecture", {}).get("input_modalities")
            if isinstance(inputs, str):
                inputs = [inputs]
            blob = json.dumps(row).lower()
            if modality == "vision" and not (isinstance(inputs, list) and "image" in inputs or '"image"' in blob):
                continue
            if modality == "text" and isinstance(inputs, list) and "image" in inputs and "text" not in inputs:
                continue
            score = 0
            if "open" in blob or row.get("open_weights") is True:
                score += 4 if open_weight else 0
            if row.get("open_weights") is False:
                score -= 2
            scored.append((-score, model_id))
        if not scored:
            raise OtariError(f"no {modality} model in this workspace's catalogue")
        scored.sort()
        return scored[0][1]

    # -- requests ----------------------------------------------------------------------------

    def _get(self, path: str) -> dict:
        if not self.key:
            raise OtariError("OTARI_API_KEY is not set", 401, "missing_key")
        response = self._client.get(
            f"{self.base_url}{path}", headers={"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        )
        if response.status_code >= 400:
            raise OtariError(response.text[:400], response.status_code, "catalog_failed")
        return response.json()

    def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        guardrails: list[dict] | None = None,
        mcp_servers: list[dict] | None = None,
        end_user: str | None = None,
        budget_id: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        step: str = "",
    ) -> Completion:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        if guardrails:
            body["guardrails"] = guardrails
        if mcp_servers:
            body["mcp_servers"] = mcp_servers
        if end_user:
            # The end user is what makes a per-person budget possible without a key per person.
            body["user"] = end_user
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Accept": "application/json"}
        if budget_id:
            headers["Otari-End-User-Budget"] = budget_id
        started = time.time()
        response = self._client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        elapsed = int((time.time() - started) * 1000)
        lower = {k.lower(): v for k, v in response.headers.items()}
        guardrail_header = lower.get("otari-guardrails", "")
        parsed_guardrails: list[dict] = []
        if guardrail_header:
            try:
                parsed_guardrails = json.loads(guardrail_header)
            except ValueError:
                parsed_guardrails = [{"raw": guardrail_header}]
        if response.status_code == 403 and "guardrail_violation" in response.text:
            raise GuardrailBlocked(response.text[:400], parsed_guardrails)
        if response.status_code >= 400:
            code = ""
            try:
                code = str(response.json().get("error", {}).get("code") or "")
            except ValueError:
                pass
            raise OtariError(response.text[:400], response.status_code, code)
        payload = response.json()
        usage = payload.get("usage") or {}
        cost = _money(usage.get("cost_usd", lower.get("otari-cost-usd", 0)))
        return Completion(
            text=_text_of(payload),
            model=model,
            served_by=str(payload.get("model") or model),
            request_id=str(lower.get("otari-request-id") or payload.get("id") or ""),
            cost_usd=cost,
            pricing_source=str(usage.get("pricing_source") or lower.get("otari-pricing-source") or ""),
            latency_ms=elapsed,
            guardrails=parsed_guardrails,
            tool_calls=_tool_calls(payload),
            raw=payload,
        )

    def complete_with_fallback(self, candidates: list[str], **kwargs) -> tuple[Completion, list[dict]]:
        """Try each model in turn, recording every attempt so the receipt can show the switch."""
        attempts: list[dict] = []
        last: Exception | None = None
        for model in [c for c in candidates if c]:
            try:
                done = self.complete(model=model, **kwargs)
                if attempts:
                    attempts.append({"model": model, "result": "served", "after_failures": len(attempts)})
                return done, attempts
            except GuardrailBlocked:
                raise
            except OtariError as exc:
                attempts.append({"model": model, "result": "failed", "status": exc.status, "code": exc.code})
                last = exc
        raise last or OtariError("no model was available", 424, "no_candidate")


class GuardrailBlocked(OtariError):
    """The gateway refused the request before any model saw it."""

    def __init__(self, message: str, verdicts: list[dict]):
        super().__init__(message, 403, "guardrail_violation")
        self.verdicts = verdicts
