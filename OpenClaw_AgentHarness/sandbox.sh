#!/usr/bin/env bash
set -euo pipefail

SANDBOX_NAME="${OPENCLAW_SANDBOX_NAME:-openclaw-agent-harness}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_MEMORY="${OPENCLAW_SANDBOX_MEMORY:-8g}"
SANDBOX_CPUS="${OPENCLAW_SANDBOX_CPUS:-4}"

usage() {
  cat <<'EOF'
Usage: ./sandbox.sh <command>

Commands:
  deploy   Create the Docker Sandbox, build the images, and start OpenClaw
  run      Run the coder -> tester -> runner pipeline
  status   Show sandbox and Compose service status
  dashboard Copy the Gateway token and open the authenticated Control UI
  logs     Follow OpenClaw gateway logs
  shell    Open a shell in the sandbox
  down     Stop the Compose application (keeps the sandbox)
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
      --publish 18789:18789 \
      shell "$PROJECT_DIR"
    sbx policy allow network --sandbox "$SANDBOX_NAME" \
      'packagefeedproxy.microsoft.io,*.pkgs.visualstudio.com,*.vsblob.vsassets.io'
  fi
}

exec_with_token() {
  local token
  token="$(copilot_token)"
  sbx exec \
    -e "COPILOT_GITHUB_TOKEN=$token" \
    -e "SANDBOX_NAME=$SANDBOX_NAME" \
    -w "$PROJECT_DIR" \
    "$SANDBOX_NAME" "$@"
}

require_sbx

case "${1:-}" in
  deploy)
    ensure_sandbox
    exec_with_token bash -lc './setup.sh && docker compose up -d openclaw'
    echo "OpenClaw is running at http://127.0.0.1:18789/"
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
  dashboard)
    ensure_sandbox
    token="$(
      sbx exec -w "$PROJECT_DIR" "$SANDBOX_NAME" \
        docker exec openclaw node -e \
        'const c=require("/home/node/.openclaw/openclaw.json");process.stdout.write(c.gateway.auth.token)' \
        | tail -n 1
    )"
    if [ -z "$token" ]; then
      echo "Gateway token unavailable. Run ./sandbox.sh deploy first." >&2
      exit 1
    fi
    printf '%s' "$token" | pbcopy
    open "http://127.0.0.1:18789/#token=$token"
    unset token
    echo "Authenticated Control UI opened; Gateway token copied to clipboard."
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
