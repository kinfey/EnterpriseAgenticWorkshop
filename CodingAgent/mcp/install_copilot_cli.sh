#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$PROJECT_ROOT/mcp/run_server.sh"

command -v copilot >/dev/null 2>&1 || {
  echo "GitHub Copilot CLI is not installed or not on PATH." >&2
  exit 1
}

if ! python3 -c "import mcp" >/dev/null 2>&1; then
  echo "Python package 'mcp' is missing. Install it with:" >&2
  echo "  python3 -m pip install --index-url https://packagefeedproxy.microsoft.io/pypi/simple -r \"$PROJECT_ROOT/mcp/requirements.txt\"" >&2
  exit 1
fi

chmod +x "$LAUNCHER"
copilot mcp remove codingagent >/dev/null 2>&1 || true
copilot mcp add --tools '*' codingagent -- "$LAUNCHER"
copilot mcp get codingagent
