"""Fine Print's own guardrails service, spoken to the Otari gateway.

The hosted gateway has no guardrails deployment of its own, and a guardrail entry
in the request may name a `url` for the check. This service is that URL: it
implements the two endpoints Otari calls (`GET /profiles`, `POST /validate`) and
answers one domain question no general-purpose classifier is good at.

An invoice, notice or letter is untrusted text. It is written by whoever sent it,
and it often contains sentences that read like instructions to a machine: "the
assistant should confirm the total", "ignore previous instructions", "pay this to
the new account". A document that talks to the reader's tooling is not a bill,
and must not be read as one.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="fine-print-guard", version="0.1.0")

# Sentences that address a machine rather than a person. Deliberately literal:
# a bill has no reason to say any of these, and every hit is worth showing a user.
_PATTERNS: list[tuple[str, str]] = [
    (r"\bignore (all )?(the )?(previous|prior|above) instructions?\b", "tells a model to ignore its instructions"),
    (r"\b(assistant|model|ai|agent|chatbot)\s+(must|should|shall|will)\b", "addresses the assistant directly"),
    (r"\bsystem\s*(prompt|message)\s*:", "embeds a system prompt"),
    (r"\byou (must|should) (now )?(approve|confirm|pay|transfer|state)\b", "instructs the reader's tool"),
    (r"\b(disregard|forget) (all |everything )?(you were|your)\b", "tells a model to forget its setup"),
    (r"\bdo not (tell|inform|mention to) the (user|account holder|customer)\b", "asks for concealment"),
    (r"\bmark (this|the) (bill|invoice|document|payment) as (paid|safe|verified)\b", "asks for its own verdict"),
    (r"\b(approve|authorise|authorize) (this|the) (invoice|payment|transfer) (without|no) (checking|verification)\b", "asks to skip verification"),
]

_MAX = 12000


class ValidateRequest(BaseModel):
    profile: str = "prompt-injection"
    input_text: str = ""
    validate_kwargs: dict[str, Any] = {}


def _scan(text: str) -> list[str]:
    hits: list[str] = []
    lowered = text[:_MAX].lower()
    for pattern, why in _PATTERNS:
        if re.search(pattern, lowered):
            hits.append(why)
    return hits


@app.get("/profiles")
def profiles() -> list[dict[str, str]]:
    return [{"name": "prompt-injection", "guardrail_name": "fine-print-document-injection"}]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "profiles": "prompt-injection"}


@app.post("/validate")
def validate(req: ValidateRequest) -> dict[str, Any]:
    hits = _scan(req.input_text or "")
    if hits:
        reasons = "; ".join(dict.fromkeys(hits))
        return {
            "profile": req.profile,
            "result": {
                "valid": False,
                "explanation": f"This document talks to the tool reading it: {reasons}.",
                "score": 0.99,
            },
        }
    return {"profile": req.profile, "result": {"valid": True, "explanation": None, "score": 0.01}}
