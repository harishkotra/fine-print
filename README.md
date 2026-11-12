# Fine Print

Photograph a bill, a notice or a letter. Fine Print tells you what the paper is actually asking, then checks four things that a language model on its own cannot be trusted to check.

Every claim in the answer is tied to one of three sources: a value read off the page, a value published by the sender, or the output of a tool that ran. Anything that could not be found is reported as not found, not filled in.

Built for the Mozilla "Devs Wilding" hackathon on the Otari gateway.

[Demo Video](https://youtu.be/eVKXfbc462M)

## The problem it solves

A model reading a bill will happily tell you the total is correct, because the total is printed on the page and the line items look plausible. It will tell you the payment details are fine, because it has no way to know what the sender actually publishes. The failure is silent, and it costs money.

Fine Print puts four hard checks around the reading:

1. **Arithmetic.** The line items are summed in the Otari code sandbox, in real Python, and compared against the stated total. Both figures are quoted, along with the difference.
2. **Sender.** The account number, UPI handle and IFSC on the paper are compared against the payment details the issuer publishes on its own page (fetched with the web fetch tool) and against a bank directory reached over MCP. A sender who is not in the directory is never called safe.
3. **Deadline.** The due date is parsed and the days remaining are computed, together with the late fee the document itself states. No date on the page means no date in the answer.
4. **Refusal.** Every value printed on the paper is re-checked against the page text. A value that cannot be found word for word is withdrawn from the answer and named, so the answer never quietly gains a number the paper did not contain.

Each of those checks ends in `holds`, `fails` or `cannot tell`, and each one carries its evidence rows with the source of every value.

## What it looks like

Four states:

- `Safe to pay`, all four checks hold.
- `Do not pay`, at least one check fails. The failing check says what it found and both values.
- `Check it yourself`, nothing proves the paper wrong and nothing proves it right.
- `Nothing to pay`, the paper asks for no money at all, for example a hospital letter confirming a discharge.

A document that contains instructions aimed at the assistant rather than at the reader is blocked by the Otari guardrail before it reaches a model. The app shows the block, the guardrail verdict and the request id, and shows no transcription, because nothing read the page.

## Under the hood

Two open-weight models in different roles, both served through Otari:

- a vision model reads the page and returns a fixed JSON schema,
- a second, different open-weight model re-reads the extraction and is asked whether it agrees, exactly where, and what it would correct.

Then the checks run: code execution for the arithmetic, web fetch for the issuer's own payment page, MCP for the bank directory. The gateway's response headers give the app the request id, the guardrail verdict, the serving model and the billed cost of every call, and all of it is displayed.

The Otari client in `app/otari.py` is a small `httpx` client rather than the OpenAI SDK, because the SDK hides the response headers and the tool call output, and those are the parts worth showing.

## Capability map

| Rubric capability | Where it is actually used |
| --- | --- |
| Open-weight models | vision model reads the page, a second open-weight model audits the reading |
| Routing | reader and checker are different models, per role |
| Fallbacks | checker model falls back to `auto` if the preferred one is unavailable |
| Web fetch | fetches the issuer's own payment page for the sender check |
| Code execution | sums the line items in the sandbox and returns real Python output |
| Guardrails | block mode on the untrusted read, prompt injection is refused before inference |
| Budgets | per end user monthly ceiling, the app stops and says so, spend is recorded per request |
| MCP | `lookup_ifsc` tool, standalone server in `mcp_server/`, called by the gateway |

### Where the lookup actually runs

Two of those capabilities are performed by the app rather than by the gateway, and the receipts in the interface say so on every row.

- **MCP.** The standalone server in `mcp_server/` speaks `initialize` / `tools/list` / `tools/call` over streamable HTTP and answers `lookup_ifsc`. A hosted Otari workspace refuses a request that names an MCP server by URL (`400`, "use a stored server through `mcp_server_ids`"), and registering a stored server on the hosted plan needs a master key, so on the hosted run the app calls the same server itself.
- **Web fetch.** Issuer pages are fetched with `httpx` for the same reason: request-level fetching is a workspace switch that a workspace key cannot change.

Both still emit a receipt with `cost_usd: 0.0` and `served_by: "this app"`, so nothing is presented as a metered gateway call that was not one. The arithmetic really does run in the Otari code sandbox, which does work on the hosted plan.

## Run it

```bash
# backend
uv venv .venv
. .venv/bin/activate
uv pip install -e ".[dev]"

# front end
cd web && npm install && npm run build && cd ..

cp .env.example .env      # add your Otari key
./run.sh                  # http://127.0.0.1:8077
```

The MCP server is a separate process, started by `run.sh` on port 8099, and `FINE_PRINT_MCP_URL` points the gateway at it. For a public deployment that URL must be reachable from the internet, for example through a tunnel.

Without a key the app still serves the interface, reports `key_present: false` on `/api/health`, and refuses to analyse rather than pretending.

### Try the demo without spending credit

`tests/stub_gateway.py` is a stand-in gateway that speaks the same wire format. It really executes the sandbox code it is sent, so the arithmetic in the demo is genuine Python output, and it blocks the injected document with the same 403 the real gateway returns.

```bash
. .venv/bin/activate
uvicorn tests.stub_gateway:app --port 8090 &
OTARI_BASE_URL=http://127.0.0.1:8090/v1 OTARI_API_KEY=stub \
FINE_PRINT_MCP_URL=http://127.0.0.1:8099/mcp \
uvicorn app.api:app --port 8078
```

The demo video uses the hosted gateway, not the stub.

## The four sample documents

Synthetic bills rendered by `fixtures/build_fixtures.py` for three fictional issuers. Nothing imitates a real company, and no real person's document is used.

- a water bill that is exactly what it claims,
- a water bill whose line items sum to 516.40 and whose total says 616.40,
- a final notice that contains instructions addressed to the assistant,
- a hospital letter that asks for no money.

Each has a plain text transcription next to the PNG, used to test the refusal check without a camera.

### What the hosted gateway actually returns

Measured on the EU endpoint against four documents, one call each:

- water bill, untampered: `safe_to_pay`, four checks hold, `$0.000982`
- water bill, total inflated by 100.00: `do_not_pay`, arithmetic fails by `100.00` and the payment account is not one the issuer publishes, `$0.000903`
- final notice with assistant-directed text: `blocked` by the guardrail before the second model is called, one check, no charge for a second reading
- hospital letter asking for no money: `check_manually`, arithmetic and sender both `cannot tell`, `$0.000725`

## Tests

```bash
. .venv/bin/activate
python -m pytest -q          # 22 tests
python debug_run.py          # all four documents through the pipeline
```

The end to end tests start the stub gateway on a free port, point the client at it and drive the real pipeline, so the request shapes, the guardrail block, the receipts and the four checks are all exercised without network access.

## Limits, honestly

- The issuer directory is a local mirror shipped with the demo, not a live crawl of every utility. An issuer who is not in `app/data/issuers.json` gets `cannot tell`, never `safe`.
- The IFSC data was verified against ifsc.razorpay.com on 2026-11-11 and is fixed at build time.
- The arithmetic check trusts the line items the vision model returned. The quote audit catches numbers that are not on the page, but a misread amount that is on the page would pass both. This is the one place where a second model in a different role is doing the work, and it is the honest weak point.
- English documents only, rupee payment rails only, one page per analysis.

## License

[LICENSE](LICENSE)

### Screenshots

<img width="2912" height="5234" alt="fpreal_bill_clean" src="https://github.com/user-attachments/assets/7ae7d93e-1ca6-45b7-956e-333ca925c3f1" />
<img width="2912" height="5426" alt="fpreal_bill_doctored" src="https://github.com/user-attachments/assets/9d73ee40-4d5f-453c-bf22-657765741f6f" />
<img width="2880" height="3000" alt="fpreal_notice_injection" src="https://github.com/user-attachments/assets/27f77ebc-8adc-4567-9e60-01c58dd8a5e2" />
<img width="2880" height="4600" alt="fpreal_letter_insurance" src="https://github.com/user-attachments/assets/b6d2699e-4697-4a36-8f7b-ce09860a4495" />
