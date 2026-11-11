"""Storage for analyses, receipts and the per-person spend ledger."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import config

SCHEMA = """
create table if not exists analyses (
  id text primary key,
  created_at real not null,
  doc_type text,
  verdict text not null,
  payload text not null
);
create table if not exists spend (
  id integer primary key autoincrement,
  end_user text not null,
  analysis_id text not null,
  step text not null,
  model text not null,
  request_id text,
  cost_usd real not null,
  created_at real not null
);
create index if not exists spend_user on spend(end_user, created_at);
"""


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_analysis(analysis_id: str, payload: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "insert or replace into analyses (id, created_at, doc_type, verdict, payload) values (?,?,?,?,?)",
            (
                analysis_id,
                time.time(),
                str((payload.get("document") or {}).get("doc_type") or ""),
                str(payload.get("verdict") or ""),
                json.dumps(payload),
            ),
        )


def get_analysis(analysis_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("select payload from analyses where id = ?", (analysis_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def recent(limit: int = 12) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "select id, created_at, doc_type, verdict, payload from analyses order by created_at desc limit ?",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        payload = json.loads(row["payload"])
        out.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "doc_type": row["doc_type"],
                "verdict": row["verdict"],
                "sender": (payload.get("document") or {}).get("sender_name") or "",
                "amount": (payload.get("document") or {}).get("amount_payable") or "",
                "cost_usd": (payload.get("totals") or {}).get("cost_usd", 0),
            }
        )
    return out


def record_spend(end_user: str, analysis_id: str, receipts: list[dict]) -> None:
    now = time.time()
    with _connect() as conn:
        for receipt in receipts:
            conn.execute(
                "insert into spend (end_user, analysis_id, step, model, request_id, cost_usd, created_at)"
                " values (?,?,?,?,?,?,?)",
                (
                    end_user,
                    analysis_id,
                    str(receipt.get("step") or ""),
                    str(receipt.get("model") or ""),
                    str(receipt.get("request_id") or ""),
                    float(receipt.get("cost_usd") or 0),
                    now,
                ),
            )


def month_spend(end_user: str) -> float:
    start = time.time()
    month = time.gmtime(start)
    first = time.mktime((month.tm_year, month.tm_mon, 1, 0, 0, 0, 0, 0, -1))
    with _connect() as conn:
        row = conn.execute(
            "select coalesce(sum(cost_usd), 0) as total from spend where end_user = ? and created_at >= ?",
            (end_user, first),
        ).fetchone()
    return float(row["total"] or 0)


def reset_all(path: Path | None = None) -> None:
    target = path or config.DB_PATH
    if target.exists():
        target.unlink()
