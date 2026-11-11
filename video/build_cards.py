"""Render the evidence cards from what the demo actually recorded.

Reads /tmp/fp_demo_real.sqlite3, takes the newest run per verdict from the four
demo documents, and prints each run's billed cost from its receipts.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cards import ROOT, bullets_card, table_card  # noqa: E402

DB = "/tmp/fp_demo_real.sqlite3"
ORDER = ["safe_to_pay", "do_not_pay", "blocked", "letter"]
LETTER = ("nothing_to_pay", "check_manually")
LABEL = {
    "safe_to_pay": "Water bill, untouched",
    "do_not_pay": "Total raised by 100.00",
    "blocked": "Notice with assistant text",
    "letter": "Hospital letter, no payment",
}
STAMPED = {
    "safe_to_pay": "SAFE TO PAY",
    "do_not_pay": "DO NOT PAY",
    "blocked": "STOPPED",
    "letter": None,  # stamped from whatever that run actually decided
}


def run_cost(payload: dict) -> float:
    return sum(float(r.get("cost_usd") or 0.0) for r in payload.get("receipts", []))


def main() -> None:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    seen: dict[str, tuple[float, dict]] = {}
    for row in db.execute("select payload from analyses order by created_at desc limit 12"):
        p = json.loads(row["payload"])
        v = "blocked" if p.get("status") == "blocked" else p.get("verdict")
        if v in LETTER:
            v = "letter"
        if v in ORDER and v not in seen:
            seen[v] = (run_cost(p), p)
        if len(seen) == len(ORDER):
            break
    missing = [v for v in ORDER if v not in seen]
    if missing:
        raise SystemExit(f"no recorded run for {missing}")

    rows, total = [], 0.0
    for v in ORDER:
        cost, payload = seen[v]
        said = str(payload.get("verdict", ""))
        stamp = STAMPED[v] or {"check_manually": "CHECK IT YOURSELF"}.get(
            said, said.replace("_", " ").upper()
        )
        total += cost
        rows.append((LABEL[v], stamp, f"${cost:.6f}"))
    print("total", f"${total:.6f}", "rows", len(rows))

    out = ROOT / "cards"
    table_card(
        "Four documents, four verdicts",
        "What the hosted gateway actually answered, run by run",
        rows,
        f"Billed by the gateway, add up to ${total:.4f} for the whole demo  ·  ceiling $1.50",
        out / "receipts.png",
    )
    bullets_card(
        "What is next",
        "Small, honest, and already load bearing",
        [
            "Issuer coverage beyond one water board",
            "A camera flow that works on a phone",
            "The two app-side lookups moved onto the gateway",
        ],
        "github.com/harishkotra/fine-print  ·  issues 3142 and 3143 filed upstream",
        out / "next.png",
    )
    print("cards written", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()
