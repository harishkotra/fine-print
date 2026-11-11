#!/usr/bin/env bash
# Start Fine Print: the MCP server, then the app.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ ! -d .venv ]; then
  uv venv .venv
  . .venv/bin/activate
  uv pip install -e ".[dev]"
else
  . .venv/bin/activate
fi

if [ ! -d web/dist ]; then
  (cd web && npm install && npm run build)
fi

export FINE_PRINT_MCP_URL="${FINE_PRINT_MCP_URL:-http://127.0.0.1:8099/mcp}"

uvicorn mcp_server.server:app --host 127.0.0.1 --port 8099 --log-level warning &
MCP_PID=$!
trap 'kill "$MCP_PID" 2>/dev/null || true' EXIT

echo "Fine Print on http://127.0.0.1:8077  (MCP on 8099, pid $MCP_PID)"
uvicorn app.api:app --host 127.0.0.1 --port 8077
