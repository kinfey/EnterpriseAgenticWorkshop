#!/usr/bin/env bash
set -euo pipefail

SANDBOX_NAME="${OPENCLAW_SANDBOX_NAME:-codingagent-openclaw}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_MEMORY="${OPENCLAW_SANDBOX_MEMORY:-8g}"
SANDBOX_CPUS="${OPENCLAW_SANDBOX_CPUS:-4}"

usage() {
  cat <<'EOF'
Usage: ./sandbox.sh <command>

Commands:
  deploy   Create the microVM, build images, and start OpenClaw 2.0
  run      Run the coder -> runner -> diagnoser pipeline
  status   Show Docker Sandbox and Compose service status
  logs     Follow OpenClaw logs
  shell    Open a shell inside the microVM
  down     Stop Compose services while retaining the microVM
EOF
}

require_sbx() {
  command -v sbx >/dev/null 2>&1 || {
    echo "Docker Sandbox CLI not found. Install it with:" >&2
    echo "  brew trust docker/tap && brew install docker/tap/sbx" >&2
    exit 1
  }
}

copilot_token() {
  if [ -n "${COPILOT_GITHUB_TOKEN:-}" ]; then
    printf '%s' "$COPILOT_GITHUB_TOKEN"
  elif command -v gh >/dev/null 2>&1; then
    gh auth token
  else
    echo "Set COPILOT_GITHUB_TOKEN or sign in with gh auth login." >&2
    exit 1
  fi
}

sandbox_exists() {
  sbx ls 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq "$SANDBOX_NAME"
}

ensure_sandbox() {
  if ! sandbox_exists; then
    sbx create --quiet \
      --name "$SANDBOX_NAME" \
      --cpus "$SANDBOX_CPUS" \
      --memory "$SANDBOX_MEMORY" \
      --publish 18790:18790 \
      shell "$PROJECT_DIR"
    sbx policy allow network --sandbox "$SANDBOX_NAME" \
      'github.com,api.github.com,*.githubusercontent.com,ghcr.io,*.ghcr.io,*.githubcopilot.com,*.copilot.github.com,packagefeedproxy.microsoft.io,*.pkgs.visualstudio.com,*.vsblob.vsassets.io'
  fi
}

exec_with_token() {
  local token
  token="$(copilot_token)"
  sbx exec \
    -e "COPILOT_GITHUB_TOKEN=$token" \
    -e "MAX_ITERATIONS=${MAX_ITERATIONS:-4}" \
    -w "$PROJECT_DIR" \
    "$SANDBOX_NAME" "$@"
}

require_sbx

case "${1:-}" in
  deploy)
    ensure_sandbox
    exec_with_token bash -lc \
      'docker compose stop openclaw >/dev/null 2>&1 || true; ./setup.sh && docker compose up -d openclaw'
    echo "OpenClaw 2.0 is running at http://127.0.0.1:18790/"
    ;;
  run)
    ensure_sandbox
    exec_with_token docker compose run --rm --no-deps harness
    ;;
  status)
    sbx ls
    if sandbox_exists; then
      sbx exec -w "$PROJECT_DIR" "$SANDBOX_NAME" docker compose ps
    fi
    ;;
  logs)
    ensure_sandbox
    sbx exec -it -w "$PROJECT_DIR" "$SANDBOX_NAME" docker compose logs -f openclaw
    ;;
  shell)
    ensure_sandbox
    sbx exec -it -w "$PROJECT_DIR" "$SANDBOX_NAME" bash
    ;;
  down)
    ensure_sandbox
    sbx exec -w "$PROJECT_DIR" "$SANDBOX_NAME" docker compose down
    ;;
  *)
    usage
    exit 2
    ;;
esac
