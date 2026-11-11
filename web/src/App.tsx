import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { analyzeFile, analyzeSample, health, samples } from "./api";
import type { Analysis, Check, Health, Overall, Receipt, Sample, Verdict } from "./types";

type State =
  | { kind: "idle" }
  | { kind: "working"; label: string; preview: string | null }
  | { kind: "done"; result: Analysis; preview: string | null }
  | { kind: "error"; message: string; preview: string | null };

const VERDICT: Record<Overall, { stamp: string; line: string; tone: string }> = {
  safe_to_pay: {
    stamp: "Safe to pay",
    line: "The paper adds up, the money goes where the sender says it should, and nothing on it contradicts itself.",
    tone: "ok",
  },
  do_not_pay: {
    stamp: "Do not pay",
    line: "Something on this paper does not hold. Pay nothing until you have checked it yourself, from a number you looked up.",
    tone: "bad",
  },
  nothing_to_pay: {
    stamp: "Nothing to pay",
    line: "This paper asks for no money. Nothing here needs paying, and nothing here is at risk if you file it and move on.",
    tone: "ok",
  },
  check_manually: {
    stamp: "Check it yourself",
    line: "Nothing here proves this is wrong, and nothing here proves it is right. That is the honest answer.",
    tone: "warn",
  },
};

const CHECK_TONE: Record<Verdict, string> = { pass: "ok", fail: "bad", unknown: "warn" };
const CHECK_WORD: Record<Verdict, string> = { pass: "holds", fail: "fails", unknown: "cannot tell" };

const STEP_WORD: Record<string, string> = {
  read: "Read the page",
  check: "Second, independent reading",
  sandbox: "Arithmetic and dates, in the sandbox",
  fetch: "The issuer's own page, fetched live",
  mcp: "Bank directory, over MCP",
};

const money = (value: number | undefined) => (value === undefined ? "—" : `$${value.toFixed(5)}`);

function Field({ label, value, mono = false }: { label: string; value: string | null | undefined; mono?: boolean }) {
  const missing = value === null || value === undefined || value === "";
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd className={missing ? "missing" : mono ? "num" : ""}>{missing ? "not stated on the page" : value}</dd>
    </div>
  );
}

function CheckCard({ check }: { check: Check }) {
  return (
    <article className={`check ${CHECK_TONE[check.verdict]}`}>
      <header>
        <h3>{check.title}</h3>
        <span className="chip">{CHECK_WORD[check.verdict]}</span>
      </header>
      <p className="headline">{check.headline}</p>
      {check.detail ? <p className="detail">{check.detail}</p> : null}
      {check.evidence.length ? (
        <ul className="evidence">
          {check.evidence.map((item, index) => (
            <li key={`${check.id}-${index}`}>
              <span className="ev-label">{item.label}</span>
              <span className="ev-value">{item.value}</span>
              {item.source ? <span className="ev-source">{item.source}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function ToolCallView({ call }: { call: Receipt["tool_calls"][number] }) {
  return (
    <div className="toolcall">
      <div className="toolcall-head">
        <span className="chip quiet">{call.kind.replace("_", " ")}</span>
        {call.url ? <code>{call.url}</code> : null}
        {call.server ? <code>{call.server}{call.tool ? ` · ${call.tool}` : ""}</code> : null}
        {call.exit_status !== undefined && call.exit_status !== null ? <code>exit {String(call.exit_status)}</code> : null}
      </div>
      {call.code ? <pre className="code">{call.code}</pre> : null}
      {call.output ? <pre className="output">{call.output}</pre> : null}
    </div>
  );
}

function ReceiptRow({ receipt }: { receipt: Receipt }) {
  return (
    <details className="receipt">
      <summary>
        <span className="receipt-step">{STEP_WORD[receipt.step] ?? receipt.step}</span>
        <span className="receipt-model">{receipt.served_by || receipt.model || "—"}</span>
        <span className="receipt-meta num">
          {receipt.latency_ms} ms · {money(receipt.cost_usd)}
        </span>
      </summary>
      <dl className="receipt-body">
        <div>
          <dt>request id</dt>
          <dd className="num">{receipt.request_id || "not returned"}</dd>
        </div>
        <div>
          <dt>model asked for</dt>
          <dd className="num">{receipt.model || "—"}</dd>
        </div>
        <div>
          <dt>model that served</dt>
          <dd className="num">{receipt.served_by || "not reported"}</dd>
        </div>
        {receipt.pricing_source ? (
          <div>
            <dt>price source</dt>
            <dd className="num">{receipt.pricing_source}</dd>
          </div>
        ) : null}
        {receipt.guardrails.length ? (
          <div>
            <dt>guardrail verdict</dt>
            <dd className="num">{JSON.stringify(receipt.guardrails)}</dd>
          </div>
        ) : null}
      </dl>
      {receipt.tool_calls.map((call, index) => (
        <ToolCallView key={index} call={call} />
      ))}
    </details>
  );
}

function Capabilities({ result }: { result: Analysis }) {
  const used = useMemo(() => {
    const models = new Set(result.receipts.map((r) => r.served_by || r.model).filter(Boolean));
    const kinds = new Set(result.receipts.flatMap((r) => r.tool_calls.map((c) => c.kind)));
    const guarded = result.receipts.some((r) => r.guardrails.length > 0) || Boolean(result.blocked);
    const rows = [`${models.size} open-weight model${models.size === 1 ? "" : "s"}, different roles`];
    if (guarded) rows.push("guardrail on the untrusted read");
    if (kinds.has("code_execution")) rows.push("code execution");
    if (kinds.has("web_fetch")) rows.push("web fetch");
    if (kinds.has("mcp")) rows.push("MCP tool");
    if (result.budget) rows.push("per-user spend ceiling");
    return rows;
  }, [result]);
  return (
    <ul className="capabilities">
      {used.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Result({ result }: { result: Analysis }) {
  const verdict = VERDICT[result.verdict];
  const doc = result.document;
  return (
    <div className="result">
      {result.status === "blocked" ? (
        <section className="quarantine">
          <h2>Quarantined before it was read</h2>
          <p>{result.blocked?.message}</p>
          <p className="detail">
            The page carried instructions addressed to the assistant. A bill has no reason to do that, so the
            gateway stopped the request and no model read it. The safe move is the same as a failed check: pay
            nothing, and do not use the number or the account printed on it.
          </p>
          {result.blocked?.verdicts?.length ? (
            <pre className="output">{JSON.stringify(result.blocked.verdicts, null, 2)}</pre>
          ) : null}
        </section>
      ) : null}

      {result.status === "budget_exhausted" ? (
        <section className="quarantine warn">
          <h2>The allowance is spent</h2>
          <p>{result.notes[0]}</p>
          <p className="detail">Nothing was sent to a model. A household should not be surprised by a bill from the tool that reads its bills.</p>
        </section>
      ) : null}

      {result.checks.length ? (
        <>
          <div className={`stamp ${verdict.tone}`}>
            <span>{verdict.stamp}</span>
          </div>
          {result.status === "blocked" ? (
            <p className="sentence">This paper was stopped before it reached a model.</p>
          ) : (
            <p className="sentence">{doc.what_they_want ?? "The page does not say clearly what it wants."}</p>
          )}
          <p className="verdict-line">{verdict.line}</p>
        </>
      ) : null}

      {result.checks.length && result.status !== "blocked" ? (
        <section className="block">
          <h2>What the paper says</h2>
          <p className="block-note">Transcribed, not trusted. Everything below is quoted from the page; the checks decide what it means.</p>
          <dl className="facts">
            <Field label="Document" value={doc.doc_type} />
            <Field label="From" value={doc.sender_name} />
            <Field label="Against" value={doc.reference_no} mono />
            <Field label="Due" value={doc.due_date ? `${doc.due_date}${doc.late_fee_text ? "" : ""}` : null} mono />
            <Field label="Total printed" value={doc.total_stated} mono />
            <Field label="Asked to pay" value={doc.amount_payable} mono />
            <Field label="Pay to" value={[doc.payment_upi, doc.payment_account, doc.payment_ifsc].filter(Boolean).join(" · ") || null} mono />
            {doc.late_fee_text ? <Field label="If late" value={doc.late_fee_text} /> : null}
          </dl>
          {doc.line_items?.length ? (
            <ul className="lines">
              {doc.line_items.map((item, index) => (
                <li key={index}>
                  <span>{item.label}</span>
                  <span className="num">{item.amount ?? "—"}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {result.checks.length ? (
        <section className="block">
          <h2>Four things a model alone cannot fake</h2>
          <div className="checks">
            {result.checks.map((check) => (
              <CheckCard key={check.id} check={check} />
            ))}
          </div>
        </section>
      ) : null}

      {result.disagreements.length ? (
        <section className="block">
          <h2>Where the two readings disagreed</h2>
          <ul className="disagreements">
            {result.disagreements.map((row, index) => (
              <li key={index}>
                <span className="num">{row.field}</span>
                <span>
                  read as <b>{row.read_as === null ? "nothing" : String(row.read_as)}</b>, second reader said{" "}
                  <b>{row.checker_read === null ? "not on the page" : String(row.checker_read)}</b>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.notes.filter(Boolean).length ? (
        <section className="block">
          <h2>What the app could not do</h2>
          <ul className="notes">
            {result.notes.filter(Boolean).map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.receipts.length ? (
        <section className="block">
          <h2>The receipts</h2>
          <p className="block-note">
            Every claim above came from one of these requests. Open any of them to see the model that served it, its
            request id, what it cost, and the raw output of the tool it ran.
          </p>
          <Capabilities result={result} />
          <div className="receipts">
            {result.receipts.map((receipt, index) => (
              <ReceiptRow key={index} receipt={receipt} />
            ))}
          </div>
          {result.totals ? (
            <div className="totals">
              <div>
                <span className="num">{result.totals.requests}</span> requests
              </div>
              <div>
                <span className="num">{result.totals.latency_ms} ms</span> end to end
              </div>
              <div>
                <span className="num">{money(result.totals.cost_usd)}</span> this document
              </div>
              <div>
                analysis <span className="num">{result.id}</span>
              </div>
            </div>
          ) : null}
          {result.budget ? (
            <div className="budget">
              <div className="budget-bar">
                <div
                  style={{
                    width: `${Math.min(100, (result.budget.spent_usd / result.budget.limit_usd) * 100).toFixed(1)}%`,
                  }}
                />
              </div>
              <p>
                <span className="num">{result.end_user}</span> has spent{" "}
                <span className="num">${result.budget.spent_usd.toFixed(4)}</span> of{" "}
                <span className="num">${result.budget.limit_usd.toFixed(2)}</span> this month. When it runs out, the app
                stops and says so.
              </p>
            </div>
          ) : null}
          {result.sandbox_code ? (
            <details className="receipt">
              <summary>
                <span className="receipt-step">The code the sandbox actually ran</span>
                <span className="receipt-model">otari_code_execution</span>
              </summary>
              <pre className="code">{result.sandbox_code}</pre>
              {result.sandbox_output ? <pre className="output">{result.sandbox_output}</pre> : null}
            </details>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [info, setInfo] = useState<Health | null>(null);
  const [sampleList, setSampleList] = useState<Sample[]>([]);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void health().then(setInfo);
    void samples().then(setSampleList);
  }, []);

  const runFile = useCallback(async (file: File) => {
    const preview = file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
    setState({ kind: "working", label: `Reading ${file.name}`, preview });
    try {
      const result = await analyzeFile(file);
      setState({ kind: "done", result, preview });
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "that did not work", preview });
    }
  }, []);

  const runSample = useCallback(async (sample: Sample) => {
    setState({ kind: "working", label: `Reading ${sample.label}`, preview: sample.image });
    try {
      const result = await analyzeSample(sample.name);
      setState({ kind: "done", result, preview: sample.image });
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "that did not work", preview: sample.image });
    }
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void runFile(file);
    },
    [runFile],
  );

  const working = state.kind === "working";
  const preview = state.kind === "idle" ? null : state.preview;

  return (
    <div className="page">
      <header className="masthead">
        <div className="wordmark">
          <svg viewBox="0 0 64 64" aria-hidden="true">
            <path d="M16 14h24l10 10v26H16z" fill="none" stroke="currentColor" strokeWidth="3" />
            <path d="M40 14v10h10" fill="none" stroke="currentColor" strokeWidth="3" />
            <path d="M23 33h18M23 40h13" stroke="#c13517" strokeWidth="3" />
          </svg>
          <div>
            <h1>Fine Print</h1>
            <p>Photograph the paper. Find out what it is actually asking.</p>
          </div>
        </div>
        <div className="status">
          <span className={`dot ${info?.key_present ? "live" : "dead"}`} />
          {info?.key_present ? (
            <span>
              {info.reader === "auto" ? "model chosen from the catalogue" : info.reader} · guardrail{" "}
              {info.guardrail} · ceiling ${info.budget_usd.toFixed(2)} a month
            </span>
          ) : (
            <span>no gateway key on this machine — set OTARI_API_KEY and restart</span>
          )}
        </div>
      </header>

      <main>
        <aside className="desk">
          <div
            className={`drop ${dragging ? "over" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") input.current?.click();
            }}
          >
            {preview ? <img src={preview} alt="the paper being read" /> : null}
            <div className="drop-copy">
              <strong>{preview ? "Read another piece of paper" : "Drop a photo of a bill, a notice or a letter"}</strong>
              <span>jpg, png or webp · or click to choose a file · nothing is stored on a server you do not own</span>
            </div>
          </div>
          <input
            ref={input}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void runFile(file);
            }}
          />

          {sampleList.length ? (
            <div className="samples">
              <h2>Or use one of these</h2>
              <p className="block-note">Four synthetic papers, built for this demo. Each one is a different answer.</p>
              <div className="sample-list">
                {sampleList.map((sample) => (
                  <button key={sample.name} type="button" disabled={working} onClick={() => void runSample(sample)}>
                    <span>{sample.label}</span>
                    <small>{sample.note}</small>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="colophon">
            <p>
              Built By Harish Kotra — <a href="https://harishkotra.me">harishkotra.me</a>
            </p>
            <p>
              <a href="https://dailybuild.xyz">Checkout my other builds</a>
            </p>
          </div>
        </aside>

        <section className="reading">
          {state.kind === "idle" ? (
            <div className="empty">
              <p className="lede">
                A bill, a demand notice, a letter from a hospital. Fine Print reads it, then checks the four things a
                language model on its own gets wrong: whether the numbers add up, whether the money would reach the
                sender, whether the deadline is real, and whether it is inventing anything the page does not say.
              </p>
              <ol className="steps">
                <li>
                  <b>It reads, twice.</b> Two open-weight models, separately: one transcribes, the other tries to
                  disagree.
                </li>
                <li>
                  <b>It does the arithmetic in a sandbox.</b> Line items are summed by code, not by a model, and the
                  printed total is quoted beside it.
                </li>
                <li>
                  <b>It checks the sender.</b> The account, handle and IFSC are compared against what the issuer
                  actually publishes, and the IFSC against a bank directory over MCP.
                </li>
                <li>
                  <b>It refuses to guess.</b> A field that is not printed is reported as not stated, never filled in.
                </li>
              </ol>
            </div>
          ) : null}

          {working ? (
            <div className="working">
              <div className="spinner" />
              <p>{state.label}</p>
              <ul className="steps working-steps">
                <li>reading the page behind the guardrail</li>
                <li>asking a second model to disagree</li>
                <li>summing the line items in the sandbox</li>
                <li>comparing the account with what the issuer publishes</li>
              </ul>
            </div>
          ) : null}

          {state.kind === "error" ? (
            <div className="error">
              <h2>That did not work</h2>
              <p>{state.message}</p>
              <p className="block-note">
                If this says the gateway key is missing, the app is running without an Otari key. It will not invent an
                answer without one.
              </p>
            </div>
          ) : null}

          {state.kind === "done" ? <Result result={state.result} /> : null}
        </section>
      </main>
    </div>
  );
}
