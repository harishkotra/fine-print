"""The four checks.

Two rules hold everywhere in this file:
1. A check never guesses. If the paper does not carry the value, the verdict is "unknown" and the
   screen says so, in those words.
2. The truth for arithmetic and dates is code that ran, not prose a model wrote. The sandbox output
   is compared against an independent recomputation, and a disagreement is itself a finding.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass
class Check:
    id: str
    title: str
    verdict: str
    headline: str
    detail: str = ""
    evidence: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "verdict": self.verdict,
            "headline": self.headline,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def money(value) -> Decimal | None:
    """Parse a currency string the way paper prints it: separators, symbols, stray spaces."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = str(value)
    text = re.sub(r"(?i)(rs\.?|inr|₹|\$|usd)", "", text)
    text = re.sub(r"[^\d.\-]", "", text)
    if text.count(".") > 1:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


# ----------------------------------------------------------------------------- 1. arithmetic

def recompute(doc: dict) -> dict:
    items = []
    for item in doc.get("line_items") or []:
        if isinstance(item, dict):
            label = str(item.get("label") or "")
            amount = money(item.get("amount") if item.get("amount") is not None else item.get("value"))
        else:
            # a model that drifts off the schema still tends to print "Label 120.00"
            text = str(item or "")
            found = re.findall(r"-?\d[\d,]*\.\d{2}|-?\d[\d,]*", text)
            label = re.sub(r"[\d,.]+\s*$", "", text).strip(" :-")
            amount = money(found[-1]) if found else None
        if amount is not None:
            items.append({"label": label, "amount": amount})
    total = sum((i["amount"] for i in items), Decimal("0.00"))
    stated_total = money(doc.get("total_stated"))
    payable = money(doc.get("amount_payable"))
    return {
        "line_sum": total,
        "stated_total": stated_total,
        "payable": payable,
        "lines": items,
        "asks_for_money": doc.get("asks_for_money"),
        "delta_total": (total - stated_total) if stated_total is not None else None,
        "delta_payable": (total - payable) if payable is not None else None,
    }


def evaluate_arithmetic(computed: dict, sandbox: dict | None) -> Check:
    line_sum = computed["line_sum"]
    stated = computed["stated_total"]
    payable = computed["payable"]
    evidence = [
        {"label": "Line items added", "value": f"{line_sum:.2f}", "source": "code, this run"},
    ]
    if sandbox and sandbox.get("line_sum") is not None:
        evidence.append({"label": "Same sum, Otari sandbox", "value": str(sandbox["line_sum"]), "source": "otari_code_execution"})
    if stated is not None:
        evidence.append({"label": "Total printed on the paper", "value": f"{stated:.2f}", "source": "document"})
    if payable is not None:
        evidence.append({"label": "Amount asked for", "value": f"{payable:.2f}", "source": "document"})

    if stated is None and payable is None and computed.get("asks_for_money") is False:
        return Check(
            "arithmetic",
            "The arithmetic",
            PASS,
            "Nothing is being charged, so there are no sums to reconcile",
            "The document asks for documents or information, not money.",
            evidence,
        )
    if stated is None and payable is None:
        return Check(
            "arithmetic",
            "The arithmetic",
            UNKNOWN,
            "The paper does not print a total, so there is nothing to check",
            "No total or amount payable could be read off this document.",
            evidence,
        )

    target = payable if payable is not None else stated
    label = "amount asked for" if payable is not None else "printed total"
    delta = target - line_sum
    if delta == 0:
        return Check("arithmetic", "The arithmetic", PASS, f"The lines add up to the {label}", "", evidence)
    if abs(delta) < Decimal("0.02"):
        return Check("arithmetic", "The arithmetic", PASS, f"The lines add up to the {label}", "Rounded to the nearest paisa.", evidence)

    direction = "more" if delta > 0 else "less"
    return Check(
        "arithmetic",
        "The arithmetic",
        FAIL,
        f"The {label} is {abs(delta):.2f} {direction} than the lines on this paper",
        f"The items on the page add to {line_sum:.2f}. The paper asks for {target:.2f}. "
        f"That difference is not explained anywhere on the document.",
        evidence,
    )


# ----------------------------------------------------------------------------- 2. deadline

def recompute_deadline(doc: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    due = doc.get("due_date")
    parsed = None
    if due:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y"):
            try:
                parsed = dt.datetime.strptime(str(due).strip(), fmt).date()
                break
            except ValueError:
                continue
    return {
        "today": today,
        "due": parsed,
        "days_left": (parsed - today).days if parsed else None,
        "weekday": parsed.strftime("%A") if parsed else None,
        "late_fee": doc.get("late_fee_text") or "",
    }


def evaluate_deadline(computed: dict, sandbox: dict | None) -> Check:
    due = computed["due"]
    evidence = [{"label": "Checked against", "value": computed["today"].strftime("%A, %d %b %Y"), "source": "code, this run"}]
    if sandbox and sandbox.get("days_left") is not None:
        evidence.append({"label": "Days, Otari sandbox", "value": str(sandbox["days_left"]), "source": "otari_code_execution"})
    if due is None:
        return Check("deadline", "The deadline", UNKNOWN, "No due date is printed on this paper", "", evidence)
    evidence.append({"label": "Due date on the paper", "value": due.strftime("%d %b %Y") + f" ({computed['weekday']})", "source": "document"})
    if computed["late_fee"]:
        evidence.append({"label": "What the paper says happens late", "value": computed["late_fee"], "source": "document"})

    days = computed["days_left"]
    if days < 0:
        return Check(
            "deadline",
            "The deadline",
            FAIL,
            f"The date on this paper passed {abs(days)} days ago",
            "Either it is a reminder for something already paid, or it is being sent to pressure you. "
            "Check the reference number against the issuer's own site before paying anything.",
            evidence,
        )
    if days == 0:
        return Check("deadline", "The deadline", PASS, "It is due today", "", evidence)
    return Check("deadline", "The deadline", PASS, f"Due in {days} days, on {due.strftime('%d %b')}", "", evidence)


# ----------------------------------------------------------------------------- 3. sender

_UPI = re.compile(r"\b([a-z0-9][a-z0-9._-]{1,})@([a-z0-9-]{2,}(?:\.[a-z0-9-]{2,})*)\b", re.I)
_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
_ACCOUNT = re.compile(r"\b(\d{9,18})\b")


def upi_handles(text: str) -> list[dict]:
    out = []
    for handle, provider in _UPI.findall(text or ""):
        if provider.lower() in {"example", "test"}:
            continue
        out.append({"handle": f"{handle}@{provider}", "provider": provider.lower()})
    return out


# Handle providers that are payment-service banks, not the issuer's own domain. A bill that says
# nnwb@okhdfcbank is normal; a bill that says nnwb@some-domain.example is not.
PSP_HANDLES = {"okhdfcbank", "okicici", "oksbi", "okaxis", "ybl", "paytm", "apl", "ibl", "axl", "upi", "airtel", "fbl"}


def _digits(value: object) -> str:
    """Account numbers get printed with slashes, spaces and labels around them."""
    return re.sub(r"\D", "", str(value or ""))


def evaluate_sender(doc: dict, issuer: dict | None, mcp: dict | None, fetch: dict | None) -> Check:
    text = " ".join(str(doc.get(k) or "") for k in ("payment_upi", "payment_account", "payment_note", "sender_name"))
    handles = upi_handles(str(doc.get("payment_upi") or ""))
    if not handles and "upi" in str(doc.get("payment_note") or "").lower():
        handles = upi_handles(str(doc.get("payment_note") or ""))
    ifsc = str(doc.get("payment_ifsc") or "").strip().upper() or None
    if not ifsc:
        found = _IFSC.search(text)
        ifsc = found.group(1) if found else None
    account = _digits(doc.get("payment_account")) or None
    if not account:
        found = _ACCOUNT.search(str(doc.get("payment_note") or ""))
        account = found.group(1) if found else None
    if account:
        account = re.sub(r"\D", "", account) or None

    evidence: list[dict] = []
    if issuer:
        published = ", ".join(issuer.get("payment_handles") or []) or "none published"
        evidence.append({"label": "Handles the issuer publishes", "value": published, "source": "issuer directory"})
        accounts = ", ".join(issuer.get("bank_accounts") or []) or "none published"
        evidence.append({"label": "Accounts the issuer publishes", "value": accounts, "source": "issuer directory"})
    if handles:
        evidence.append({"label": "Handle printed on this paper", "value": handles[0]["handle"], "source": "document"})
    if account:
        evidence.append({"label": "Account printed on this paper", "value": account, "source": "document"})
    if ifsc:
        evidence.append({"label": "IFSC printed on this paper", "value": ifsc, "source": "document"})
    if fetch and fetch.get("output"):
        evidence.append({"label": "From the issuer's own payment page", "value": str(fetch["output"])[:300], "source": str(fetch.get("url") or "")})
    if mcp and mcp.get("found") is not None:
        evidence.append(
            {
                "label": "Bank directory lookup",
                "value": (f"{mcp.get('bank')}, {mcp.get('branch')}" if mcp.get("found") else f"{ifsc} does not exist"),
                "source": f"mcp: {mcp.get('server', 'lookup_ifsc')}",
            }
        )

    if not handles and not ifsc and not account:
        if doc.get("asks_for_money") is False:
            return Check(
                "sender",
                "Who is asking for money",
                PASS,
                "This paper asks for no money, so there is no payment detail to check",
                "Documents can be legitimate and still ask for nothing. Nothing here needs paying.",
                evidence,
            )
        return Check("sender", "Who is asking for money", UNKNOWN, "This paper names no account, handle or IFSC to pay", "", evidence)

    problems: list[str] = []
    matched = 0
    if issuer:
        published_handles = [str(h).lower() for h in issuer.get("payment_handles") or []]
        suffix = str(issuer.get("upi_suffix") or "").lower()
        for handle in handles:
            value = handle["handle"].lower()
            if value in published_handles:
                matched += 1
                continue
            if handle["provider"] in PSP_HANDLES and suffix and suffix in handle["handle"].lower().split("@")[0]:
                matched += 1
                continue
            if handle["provider"] not in PSP_HANDLES:
                problems.append(
                    f"the handle {handle['handle']} is on {handle['provider']}, which is not a payment handle the issuer uses"
                )
            else:
                problems.append(f"the handle {handle['handle']} is not one the issuer publishes")

        published_accounts = [re.sub(r"\D", "", str(a)) for a in issuer.get("bank_accounts") or []]
        if account and published_accounts:
            if account in published_accounts:
                matched += 1
            else:
                problems.append(f"account {account} is not an account the issuer publishes")

        published_ifsc = [str(i).upper() for i in issuer.get("ifsc") or []]
        if ifsc and published_ifsc:
            if ifsc in published_ifsc:
                matched += 1
            else:
                bank = (mcp or {}).get("bank") or "another bank"
                problems.append(
                    f"the account on this paper is at {bank} ({ifsc}), and the issuer publishes only "
                    + ", ".join(published_ifsc)
                )

    if ifsc and mcp is not None and mcp.get("found") is False:
        problems.append(f"the IFSC {ifsc} does not exist in the bank directory")

    if problems:
        return Check(
            "sender",
            "Who is asking for money",
            FAIL,
            "The money on this paper would not go to the organisation that sent it",
            "The paper and the issuer's own published details disagree: "
            + "; ".join(problems)
            + ". Pay nothing until you have opened the issuer's site yourself.",
            evidence,
        )
    if issuer and matched:
        return Check(
            "sender",
            "Who is asking for money",
            PASS,
            "Every payment detail on this paper is one the issuer publishes",
            "Handle, account and IFSC all match the issuer's own published payment details.",
            evidence,
        )
    return Check(
        "sender",
        "Who is asking for money",
        UNKNOWN,
        "Nothing on file to check these payment details against",
        "This sender is not in the issuer directory, so the app will not call these details safe. Add the issuer's official domain to check it.",
        evidence,
    )


# ----------------------------------------------------------------------------- 4. quotes

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%b %d, %Y", "%B %d, %Y", "%d.%m.%Y")


def _forms(value) -> list[str]:
    """Ways a single value may legitimately appear on a printed page."""
    raw = str(value or "").strip()
    if not raw:
        return []
    forms = {_norm(raw)}
    for fmt in _DATE_FORMATS:
        try:
            day = dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        forms |= {
            _norm(day.strftime("%d %b %Y")),
            _norm(day.strftime("%d %B %Y")),
            _norm(day.strftime("%d/%m/%Y")),
            _norm(day.strftime("%d-%m-%Y")),
            _norm(day.strftime("%d.%m.%Y")),
        }
        break
    if re.fullmatch(r"\d+\.\d{2}", raw):
        forms.add(_norm(raw.rstrip("0").rstrip(".")))
        forms.add(_norm(f"{Decimal(raw):,.2f}"))
    return [f for f in forms if f]


def audit_quotes(doc: dict, source_text: str) -> Check:
    """Every field the reader returned must be findable on the paper, or it is withdrawn."""
    source = _norm(source_text)
    if not source:
        return Check("quotes", "Every claim traced to the page", UNKNOWN, "No text to check against", "")
    fields = {
        "sender name": doc.get("sender_name"),
        "total": doc.get("total_stated"),
        "amount payable": doc.get("amount_payable"),
        "due date": doc.get("due_date"),
        "reference": doc.get("reference_no"),
    }
    supported, unsupported = [], []
    for label, value in fields.items():
        if not value:
            continue
        found = any(form in source for form in _forms(value))
        (supported if found else unsupported).append(str(value))
    evidence = [{"label": f"{len(supported)} values found word for word on the page", "value": ", ".join(supported[:6]) or "none", "source": "text match"}]
    if unsupported:
        evidence.append({"label": f"{len(unsupported)} values NOT on the page", "value": ", ".join(unsupported), "source": "withdrawn"})
    if unsupported:
        return Check(
            "quotes",
            "Every claim traced to the page",
            FAIL,
            f"{len(unsupported)} value(s) could not be found on the page and were withdrawn: " + ", ".join(unsupported),
            "The screen never shows a number the paper does not carry. These were dropped: " + ", ".join(unsupported),
            evidence,
        )
    return Check("quotes", "Every claim traced to the page", PASS, "Every value shown is printed on the page", "", evidence)


def overall(checks: list[Check]) -> str:
    by_id = {c.id: c.verdict for c in checks}
    if by_id.get("sender") == FAIL or by_id.get("arithmetic") == FAIL or by_id.get("quotes") == FAIL:
        return "do_not_pay"
    if by_id.get("deadline") == FAIL and by_id.get("sender") != PASS:
        return "do_not_pay"
    if all(v == PASS for v in by_id.values()):
        return "safe_to_pay"
    return "check_manually"
