"""End-to-end tests: real HTTP client, real checks, stand-in gateway.

The gateway here executes the sandbox snippets for real, so a passing arithmetic test means the
numbers genuinely reconciled, not that a fixture agreed with itself.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app import config, pipeline

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def gateway():
    from tests.stub_gateway import app as stub

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(stub, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}/v1"
    previous = (config.OTARI_BASE_URL, config.OTARI_API_KEY)
    config.OTARI_BASE_URL = base
    config.OTARI_API_KEY = "stub-key"
    yield base
    config.OTARI_BASE_URL, config.OTARI_API_KEY = previous


def _run(name: str) -> dict:
    image = (ROOT / "fixtures" / f"{name}.png").read_bytes()
    import base64

    data_url = "data:image/png;base64," + base64.b64encode(image).decode()
    return pipeline.analyze(image_data_url=data_url, end_user=f"test-{name}")


def _checks(result: dict) -> dict:
    return {check["id"]: check for check in result["checks"]}


def test_clean_bill_is_safe_to_pay(gateway):
    result = _run("bill_clean")
    assert result["status"] == "ok"
    assert result["document"]["total_stated"] == "516.40"
    checks = _checks(result)
    assert checks["arithmetic"]["verdict"] == "pass"
    assert checks["sender"]["verdict"] == "pass"
    assert checks["deadline"]["verdict"] == "pass"
    assert result["verdict"] == "safe_to_pay"


def test_receipts_carry_a_request_id_and_a_real_cost(gateway):
    result = _run("bill_clean")
    steps = [r["step"] for r in result["receipts"]]
    assert steps[:2] == ["read", "check"]
    for receipt in result["receipts"]:
        if receipt["model"] is None:
            continue
        assert receipt["request_id"]
        assert receipt["cost_usd"] >= 0
    sandbox = [r for r in result["receipts"] if r["step"] == "sandbox"]
    assert sandbox and sandbox[0]["tool_calls"], "the sandbox step must show the tool call it made"


def test_lookups_done_in_app_are_marked_free_and_off_gateway(gateway):
    result = _run("bill_clean")
    local = [r for r in result["receipts"] if r["model"] is None]
    assert {r["step"] for r in local} <= {"fetch", "mcp"}
    for receipt in local:
        assert receipt["cost_usd"] == 0.0
        assert receipt["served_by"] == "this app"
        assert receipt["tool_calls"], "an app-side lookup must still show what it read"


def test_sandbox_output_is_real_python(gateway):
    result = _run("bill_clean")
    assert result["sandbox_code"], "the code that ran is shown"
    assert '"line_sum": 516.4' in result["sandbox_output"].replace(" ", " ")


def test_doctored_bill_fails_arithmetic_and_sender(gateway):
    result = _run("bill_doctored")
    checks = _checks(result)
    assert checks["arithmetic"]["verdict"] == "fail"
    assert checks["sender"]["verdict"] == "fail"
    assert result["verdict"] == "do_not_pay"
    arithmetic = checks["arithmetic"]
    assert "100.00" in arithmetic["headline"]
    assert "516.40" in arithmetic["detail"] and "616.40" in arithmetic["detail"]


def test_injected_notice_is_blocked_before_reading(gateway):
    result = _run("notice_injection")
    assert result["status"] == "blocked"
    assert result["verdict"] == "do_not_pay"
    assert result["receipts"] == [], "a blocked request must not be billed"
    assert result["checks"][0]["id"] == "guardrail"


def test_letter_that_asks_for_no_money_is_not_treated_as_a_bill(gateway):
    result = _run("letter_insurance")
    assert result["status"] == "ok"
    assert result["document"]["asks_for_money"] is False
    assert result["document"]["amount_payable"] is None
    assert result["verdict"] != "do_not_pay"
