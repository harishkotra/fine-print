# DoraHacks submission copy

Paste-ready text for https://dorahacks.io/hackathon/mozilla-devs-wilding/build

## Project name

Fine Print

## One line

Photograph a bill, notice or letter and get one answer a model cannot fake on its own: what this paper is asking you to do, and whether it holds.

## Vision (short field)

Most people cannot tell a real bill from a fake one, and the tell is never in the prose. It is in the arithmetic, the account number, the date, and in what the paper does not say. Fine Print reads the page, then checks four things separately: the line items against the stated total, the payment details against what the sender actually publishes, the deadline and late fee against the paper's own terms, and finally whether a value it needs is simply not printed. Anything unproven comes back as "cannot tell" or "not stated" rather than a guess. If the page tries to give instructions to the model reading it, the page is stopped before a second model ever sees it.

## Description

### The problem

Every scam notice and every misprinted bill lands the same way: a page that looks official, an amount, an account, a date before which something bad happens. People pay because the page is confident. The four things that would give it away are all mechanical, and all of them are things a language model asked to "read this bill" will happily paper over. It will tidy an arithmetic error. It will trust an account number it has never seen. It will estimate a deadline it cannot see. It will invent a value that is not on the page rather than admit the page does not contain it.

Fine Print is built so that none of those four answers can come from the model alone.

### What it does

1. **Reads the page once.** An open-weight vision model (`alibaba/qwen3-vl-30b-a3b-instruct`) transcribes the document into a fixed JSON contract: issuer, line items, stated total, amount payable, due date, payment handle / account / IFSC, late fee terms, and a `stated` block that records which fields were actually printed. This is a reading, not a judgement.
2. **Sums the paper's own numbers in a sandbox.** The line items go to Otari's code execution tool, which returns a real figure and a real delta. When the paper says 616.40 and the lines add to 516.40, that is arithmetic in a sandbox, not a model's impression of arithmetic.
3. **Checks where the money would go.** The sender is matched against an issuer allowlist that lives in data, not in the model: payment handle, account number (compared digits only) and IFSC. The issuer's own published payment page is fetched and cited next to the document's claims, and an IFSC is confirmed through an MCP server. An off-list sender is never called safe.
4. **Does the date maths against the paper's terms.** Days remaining and the late fee come from the document's own words, so "pay by the 20th or 50.00 applies" is turned into a date and a number.
5. **Refuses to fill gaps.** If a field is missing from the page, the answer is "not stated", not an inference. The check that verifies claims lists every value it could not trace back to printed text.
6. **Stops hostile pages before the expensive read.** After the first transcription and before any second model is asked anything, the transcribed text is sent to a guardrail with `mode: block`. A page containing assistant-directed instructions is refused: `status: blocked`, one failing check, and no second reading is paid for.

The verdict is one of four: **Safe to pay**, **Do not pay**, **Check it yourself**, or **Nothing to pay** for a letter that asks for nothing.

### How Otari is used

| Capability | Where it is in the app |
| --- | --- |
| Multiple models, distinct roles | `alibaba/qwen3-vl-30b-a3b-instruct` reads the page; `meta/llama-4-scout-17b` independently re-reads and is asked only to disagree |
| Model routing and fallbacks | a routing policy picks the reader; the checker falls back to `auto` instead of failing the request |
| Code execution | the arithmetic check runs in the gateway sandbox and returns the delta |
| Guardrails | `mode: block` on the untrusted read, plus a second scan of the transcription before the checker spends a token |
| Budgets and spending limits | a monthly ceiling per workspace, checked before every call, with a plain message when it is hit |
| Per-user budgets | spend is recorded per `end_user`, each with its own ceiling and ledger |
| Web fetch | the issuer's published payment page is fetched and shown as evidence |
| MCP | `lookup_ifsc`, a standalone streamable-HTTP MCP server in `mcp_server/` |

Two of those are executed by the application rather than by the gateway, and the interface says so on the receipt row: `served_by: "this app"`, `cost_usd: 0.0`. A hosted workspace refuses a request that names MCP servers by URL, and request-time fetching is a workspace switch a workspace key cannot flip, so Fine Print does both itself rather than pretend it did not. The arithmetic, the model calls, the routing, the guardrail and the budgets are genuine gateway calls with real receipts, including the request id and the billed cost.

### Evidence

Four documents, one hosted call each, on the EU endpoint:

- clean water bill: `safe_to_pay`, all four checks hold, USD 0.000987
- bill with the total inflated by 100.00: `do_not_pay`, arithmetic fails by 100.00, and the account is not one the issuer publishes, USD 0.000906
- final notice addressed to the AI: `blocked` by the guardrail before the second model runs, USD 0.000529
- hospital letter asking for no money: `check_it_yourself`, with arithmetic and sender both "cannot tell", USD 0.000729

The four runs together billed USD 0.003151, which is the same figure the demo video shows on its receipts card. Per-run receipts with request ids are in `runs/`.

### What I would fix next

The honest gap is the one above: two capabilities run in the app because a hosted workspace key cannot reach them. Both belong on the gateway, and both are one master-key action away.

## Links

- Video walkthrough (3:07): recorded from the running app, one take per section
- Repository: https://github.com/harishkotra/fine-print
- Issues filed while building: https://github.com/mozilla-ai/otari/issues/3142 and https://github.com/mozilla-ai/otari/issues/3143

Built By Harish Kotra
[harishkotra.me](https://harishkotra.me)

Checkout my other builds
[dailybuild.xyz](https://dailybuild.xyz)
