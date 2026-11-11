export type Verdict = "pass" | "fail" | "unknown";
export type Overall = "safe_to_pay" | "do_not_pay" | "check_manually" | "nothing_to_pay";

export interface Evidence {
  label: string;
  value: string;
  source: string;
}

export interface Check {
  id: string;
  title: string;
  verdict: Verdict;
  headline: string;
  detail: string;
  evidence: Evidence[];
}

export interface ToolCall {
  kind: "code_execution" | "web_fetch" | "mcp";
  code?: string;
  output?: string;
  exit_status?: number | string;
  url?: string;
  server?: string;
  tool?: string;
}

export interface Receipt {
  step: string;
  model: string;
  served_by: string;
  request_id: string;
  cost_usd: number;
  pricing_source: string;
  latency_ms: number;
  guardrails: Record<string, unknown>[];
  tool_calls: ToolCall[];
}

export interface Document {
  doc_type: string | null;
  sender_name: string | null;
  addressee: string | null;
  reference_no: string | null;
  issue_date: string | null;
  due_date: string | null;
  total_stated: string | null;
  amount_payable: string | null;
  late_fee_text: string | null;
  line_items: { label: string; amount: string | null }[] | null;
  payment_upi: string | null;
  payment_account: string | null;
  payment_ifsc: string | null;
  payment_note: string | null;
  what_they_want: string | null;
  asks_for_money: boolean | null;
}

export interface Disagreement {
  field: string;
  read_as: unknown;
  checker_read: unknown;
}

export interface Analysis {
  id: string;
  status: "ok" | "blocked" | "unreadable" | "budget_exhausted";
  end_user: string;
  document: Document;
  checks: Check[];
  verdict: Overall;
  receipts: Receipt[];
  disagreements: Disagreement[];
  notes: string[];
  models?: { reader: string | null; checker: string | null };
  totals?: { cost_usd: number; requests: number; latency_ms: number };
  budget?: { end_user: string; spent_usd: number; limit_usd: number; remaining_usd: number };
  blocked?: { verdicts: Record<string, unknown>[]; message: string };
  sandbox_code?: string;
  sandbox_output?: string;
}

export interface Sample {
  name: string;
  label: string;
  note: string;
  image: string;
}

export interface Health {
  ok: boolean;
  base_url: string;
  key_present: boolean;
  reader: string;
  checker: string;
  guardrail: string;
  mcp_url: string;
  budget_usd: number;
}
