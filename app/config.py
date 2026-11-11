"""Configuration. Everything is env-driven so the same build runs on otari.ai or a self-hosted gateway."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Otari gateway. Hosted default; set OTARI_BASE_URL to http://localhost:8000/api/v1 for a self-hosted one.
OTARI_BASE_URL = os.getenv("OTARI_BASE_URL", "https://api.otari.ai/api/v1")
OTARI_API_KEY = os.getenv("OTARI_API_KEY", "")

# Catalogue selectors. Blank means "ask the gateway's catalogue and pick", which is what a fresh
# workspace needs; set them once you know your workspace's access.
READER_MODEL = os.getenv("OTARI_READER_MODEL", "")
READER_FALLBACK = os.getenv("OTARI_READER_FALLBACK", "")
CHECKER_MODEL = os.getenv("OTARI_CHECKER_MODEL", "")
# A routing policy name, if the deployment has one. Sending this instead of a model lets Otari
# do the failover itself and keeps the policy name on the receipt.
ROUTING_POLICY = os.getenv("OTARI_ROUTING_POLICY", "")

# Guardrails. The reader request is the one that touches untrusted paper, so it is the one guarded.
GUARDRAIL_PROFILE = os.getenv("OTARI_GUARDRAIL_PROFILE", "prompt-injection")
GUARDRAIL_MODE = os.getenv("OTARI_GUARDRAIL_MODE", "block")
# The guardrails service to run that profile against. A hosted deployment may have none of its
# own, in which case the check goes to a service we run and Otari only carries the verdict.
GUARDRAIL_URL = os.getenv("OTARI_GUARDRAIL_URL", "")

# Per-person spend. The app enforces its own ceiling on top of any Otari budget, so a demo
# cannot burn an allowance even if the gateway budget is missing.
MONTHLY_BUDGET_USD = float(os.getenv("FINE_PRINT_MONTHLY_BUDGET_USD", "0.25"))

# The MCP server this app calls. Reachable from the gateway, so it must be a public URL
# (cloudflared / ngrok) when running against otari.ai.
MCP_URL = os.getenv("FINE_PRINT_MCP_URL", "")

DB_PATH = Path(os.getenv("FINE_PRINT_DB", str(ROOT / "data" / "fineprint.db")))
WEB_DIST = ROOT / "web" / "dist"
FIXTURES = ROOT / "fixtures"

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
