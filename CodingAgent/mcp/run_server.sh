#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CODINGAGENT_ROOT="$PROJECT_ROOT"

if ! python3 -c "import mcp" >/dev/null 2>&1; then
  echo "Python package 'mcp' is missing. Install it with:" >&2
  echo "  python3 -m pip install --index-url https://packagefeedproxy.microsoft.io/pypi/simple -r \"$PROJECT_ROOT/mcp/requirements.txt\"" >&2
  exit 1
fi

exec python3 "$PROJECT_ROOT/mcp/mcp_server.py"
