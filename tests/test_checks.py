from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app import checks as C

ISSUER = {
    "name": "Nirmal Nagar Water Board",
    "domain": "nnwb.demo",
    "upi_suffix": "nnwb",
    "payment_handles": ["nnwb@okhdfcbank"],
    "bank_accounts": ["50100234567890"],
    "ifsc": ["SBIN0001234"],
}

CLEAN = {
    "sender_name": "Nirmal Nagar Water Board",
    "total_stated": "516.40",
    "amount_payable": "516.40",
    "due_date": "2026-11-20",
    "line_items": [
        {"label": "Water charges, Oct", "amount": "420.00"},
        {"label": "Meter rent", "amount": "60.00"},
        {"label": "Sewer cess", "amount": "36.40"},
    ],
    "payment_upi": "nnwb@okhdfcbank",
    "payment_account": "50100234567890",
    "payment_ifsc": "SBIN0001234",
}

MCP_OK = {"found": True, "bank": "State Bank of India", "branch": "HAJIGANJ", "server": "lookup.ifsc"}


def test_arithmetic_passes_when_lines_match_the_total():
    check = C.evaluate_arithmetic(C.recompute(CLEAN), None)
    assert check.verdict == C.PASS
    assert "add up" in check.headline


def test_arithmetic_fails_when_the_paper_asks_for_more_than_the_lines():
    doctored = {**CLEAN, "amount_payable": "616.40", "total_stated": "616.40"}
    check = C.evaluate_arithmetic(C.recompute(doctored), None)
    assert check.verdict == C.FAIL
    assert "100.00 more" in check.headline
    assert "516.40" in check.detail


def test_arithmetic_is_unknown_when_no_total_is_printed():
    check = C.evaluate_arithmetic(C.recompute({"line_items": CLEAN["line_items"]}), None)
    assert check.verdict == C.UNKNOWN


def test_sandbox_disagreement_is_shown_not_hidden():
    check = C.evaluate_arithmetic(C.recompute(CLEAN), {"line_sum": 999.0, "days_left": 3})
    assert any("Otari sandbox" in e["label"] and e["value"] == "999.0" for e in check.evidence)


def test_money_parses_print_forms():
    assert C.money("Rs. 1,240.50") == C.money("1240.5")
    assert C.money("₹ 96") == C.money("96.00")
    assert C.money("") is None


def test_deadline_counts_days_from_today():
    computed = C.recompute_deadline(CLEAN, today=dt.date(2026, 11, 11))
    check = C.evaluate_deadline(computed, None)
    assert check.verdict == C.PASS
    assert computed["days_left"] == 9
    assert computed["weekday"] == "Friday"


def test_deadline_fails_when_the_date_has_passed():
    computed = C.recompute_deadline({"due_date": "2026-10-01"}, today=dt.date(2026, 11, 11))
    assert C.evaluate_deadline(computed, None).verdict == C.FAIL


def test_deadline_is_unknown_without_a_date():
    computed = C.recompute_deadline({}, today=dt.date(2026, 11, 11))
    assert C.evaluate_deadline(computed, None).verdict == C.UNKNOWN


def test_sender_passes_when_everydetail_matches_the_issuer():
    check = C.evaluate_sender(CLEAN, ISSUER, MCP_OK, None)
    assert check.verdict == C.PASS


def test_sender_fails_when_the_account_belongs_to_another_bank():
    doctored = {**CLEAN, "payment_account": "50200098765432", "payment_ifsc": "HDFC0000001", "payment_upi": ""}
    check = C.evaluate_sender(doctored, ISSUER, {"found": True, "bank": "HDFC Bank", "branch": "NARIMAN POINT"}, None)
    assert check.verdict == C.FAIL
    assert "HDFC Bank" in check.detail
    assert "50100234567890" in check.detail or "SBIN0001234" in check.detail


def test_sender_fails_when_the_handle_is_not_a_payment_handle():
    doctored = {**CLEAN, "payment_upi": "nnwb.pay@secure-payments.example", "payment_account": None, "payment_ifsc": None}
    check = C.evaluate_sender(doctored, ISSUER, None, None)
    assert check.verdict == C.FAIL
    assert "secure-payments.example" in check.detail


def test_sender_is_unknown_when_the_issuer_is_unknown():
    check = C.evaluate_sender(CLEAN, None, MCP_OK, None)
    assert check.verdict == C.UNKNOWN
    assert "will not call these details safe" in check.detail


def test_sender_is_unknown_when_the_paper_asks_for_no_money():
    doc = {"sender_name": "Sunrise Hospital", "payment_upi": None, "payment_account": None, "payment_ifsc": None, "payment_note": None}
    assert C.evaluate_sender(doc, ISSUER, None, None).verdict == C.UNKNOWN


def test_quote_audit_withdraws_values_that_are_not_on_the_page():
    page = "Nirmal Nagar Water Board. Total 516.40. Due 2026-11-20. Consumer No 778812."
    ok = C.audit_quotes({"sender_name": "Nirmal Nagar Water Board", "total_stated": "516.40"}, page)
    assert ok.verdict == C.PASS
    bad = C.audit_quotes({"sender_name": "Nirmal Nagar Water Board", "total_stated": "516.40", "reference_no": "999999"}, page)
    assert bad.verdict == C.FAIL
    assert "999999" in bad.headline


def test_overall_never_says_safe_when_a_check_failed():
    checks = [
        C.Check("arithmetic", "a", C.PASS, ""),
        C.Check("deadline", "d", C.PASS, ""),
        C.Check("sender", "s", C.UNKNOWN, ""),
        C.Check("quotes", "q", C.PASS, ""),
    ]
    assert C.overall(checks) == "check_manually"
    checks[2] = C.Check("sender", "s", C.FAIL, "")
    assert C.overall(checks) == "do_not_pay"


def test_issuer_directory_is_valid_json_with_payment_details():
    data = json.loads((Path(__file__).resolve().parent.parent / "app" / "data" / "issuers.json").read_text())
    for issuer in data["issuers"]:
        assert issuer["domain"]
        assert issuer["payment_handles"], issuer["name"]
        assert issuer["bank_accounts"], issuer["name"]
        assert issuer["ifsc"], issuer["name"]
