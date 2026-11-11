# Demo video: script and shot list

Rubric constraint: screen recording with the participant's own voice. No narration synthesis, no slides-only cut. Target 3:30, hard ceiling 5:00.

Record at 1440x900 or larger, browser at 100% zoom, one window, no notifications. Have the terminal visible in a second window for the two proof beats (receipts and budget).

## Before you record

```bash
cd ~/fine-print && bash run.sh          # app on 8077, MCP on 8099
ngrok http 8099                          # copy the https URL into OTARI_GUARDRAIL_URL / FINE_PRINT_MCP_URL
```

Open http://127.0.0.1:8077 once and run the four samples through in one pass, so the DB has warm data and you know the timing. Clear the DB before the real take if you want the spend figures to look clean:

```bash
rm -f data/fineprint.db
```

Do one dry run of the injection sample: the stamp must read "Do not pay" with the stopped line, because that is the beat that proves the guardrail.

## 0:00 - 0:20 The problem, said plainly

**On screen:** the clean bill fixture, full frame, nothing else.

> "This is a water bill. It looks ordinary. In the next three minutes I want to show you the four things that decide whether it is real, and why the app you are about to see refuses to let a language model answer any of them on its own."

## 0:20 - 1:05 One page, one answer

**On screen:** click the clean sample. Let the whole result render. Scroll slowly once, top to bottom.

> "Fine Print reads the page once with an open-weight vision model, Qwen3-VL, and turns it into strict JSON: issuer, line items, total, due date, payment details, and a record of which fields were actually printed. That is a transcription, not a judgement. Then four checks run, and each one is something a model cannot fake."

Point at each check as you say it. On screen they are titled "The arithmetic", "Who is asking for money", "The deadline", "Every claim traced to the page":

> "The arithmetic: the lines add up to the amount asked for, computed in a sandbox, not in the model's head. Who is asking for money: every payment detail on this page is one the water board actually publishes. The deadline: nine days, from the paper's own words. Every claim traced to the page: every value shown was traced back to printed text."

## 1:05 - 1:45 The tampered page

**On screen:** click the doctored sample. Wait for the stamp.

> "Same paper, one number moved. The total says six hundred and sixteen forty. The lines add to five hundred and sixteen forty. The code execution sandbox returns the hundred rupee delta as a number, and the sender check has a second thing to say: the account on this paper is not the account the issuer publishes."

**On screen:** scroll to the receipts panel, hover the arithmetic row.

> "This is the receipt for that check. The model that served it, the tool call that ran, and the billed cost. Nothing in this app reports a check it did not actually run."

## 1:45 - 2:25 The page that talks to the AI

**On screen:** click the notice with assistant instructions. Stall deliberately before clicking.

> "Scam mail has started doing something new: it writes instructions to whatever model reads it. 'Ignore the amounts', 'mark this as verified'. So the guardrail runs on the transcription before a second model is allowed to look at it."

**On screen:** the blocked state. No facts panel, no transcription.

> "The page was refused. Status blocked, one failing check, and the transcription is hidden on purpose: there is nothing on a hostile page worth showing an operator. The second model was never called, so this document cost less than the ones before it."

## 2:25 - 2:55 The paper that asks for nothing

**On screen:** click the hospital letter.

> "Not every document is about money. This one is a discharge letter. Arithmetic cannot tell, because there is no total. Sender cannot tell, because there is no payment detail. The verdict is 'check it yourself', not 'safe', because two of the four things could not be proven. That distinction is the whole point of the product."

## 2:55 - 3:20 What is running underneath

**On screen:** switch to the terminal, `curl` the health endpoint or show the receipts JSON for one analysis.

> "Two open-weight models in different roles: Qwen3-VL reads, Llama 4 Scout is asked only to disagree with the reading. A routing policy picks the reader, and falls back to auto rather than failing. Budgets are enforced per workspace and per end user, and when the ceiling is hit the app says so instead of spending. MCP is a small server in the repo, streaming HTTP, exposing an IFSC lookup that the sender check cites."

Say this part honestly, do not skip it:

> "Two of those, the issuer page fetch and the MCP call, this app performs itself and labels as its own on the receipt, because a hosted workspace refuses a request that names MCP servers by URL. The receipts show which is which: gateway calls carry a request id and a real cost, app-side calls are labelled and free."

## 3:20 - 3:30 Close

**On screen:** back to the clean result, stamp visible.

> "Four checks, four verdicts, one honest answer per page. Fine Print. Built by Harish Kotra."

## If you have time left

- Show the budget ceiling refuse a call: set `FINE_PRINT_MONTHLY_BUDGET_USD=0.0005`, restart, run one sample, show the allowance message. This is the clearest proof for two rubric rows at once.
- Show `GET /api/samples` so a judge can see the four documents are part of the app, not local files on your laptop.

## Don'ts

- Do not describe a capability you do not show on screen in the same breath.
- Do not apologise for the app-side calls; state the reason once, plainly, and move on.
- Do not cut between the click and the result. The wait is part of the demonstration that a real call is happening.
