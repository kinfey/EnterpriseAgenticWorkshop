#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/sbxenv.yaml"
SANDBOX_NAME="skill-testing-harness"
VENV_DIR="/home/agent/.venvs/skill-testing-harness"

usage() {
  cat <<'EOF'
Usage: ./scripts/docker-sandbox.sh <command>

Commands:
  plan     Show the Docker Sandbox environment plan
  setup    Create the sandbox and install Python dependencies
  login    Authenticate GitHub Copilot inside the sandbox
  run      Setup and run the Responses service in the foreground
  start    Setup and run the Responses service in the background
  shell    Open a shell in the sandbox
  status   Show sandbox and published-port status
  stop     Stop the sandbox
  remove   Remove the sandbox and its persistent state
EOF
}

require_sbx() {
  if ! command -v sbx >/dev/null 2>&1; then
    echo "ERROR: sbx is required. Install Docker Sandboxes first." >&2
    exit 1
  fi
}

create_sandbox() {
  if sbx ls -q | grep -Fxq "$SANDBOX_NAME"; then
    return
  fi
  sbx env create --auto-approve "$ENV_FILE"
}

configure_network() {
  local policy_json
  policy_json="$(sbx policy ls --json)"
  local resources=(
    "packagefeedproxy.microsoft.io:443"
    "*.pkgs.visualstudio.com:443"
    "*.vsblob.vsassets.io:443"
  )
  local resource
  for resource in "${resources[@]}"; do
    if ! grep -Fq "\"$resource\"" <<<"$policy_json"; then
      sbx policy allow network --sandbox "$SANDBOX_NAME" "$resource"
    fi
  done
}

install_dependencies() {
  sbx env exec "$ENV_FILE" -- bash -lc "
    set -euo pipefail
    if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
      for attempt in \$(seq 1 30); do
        if sudo apt-get update && sudo apt-get install -y python3-venv; then
          break
        fi
        if [[ \$attempt -eq 30 ]]; then
          echo 'ERROR: apt remained unavailable after 30 attempts.' >&2
          exit 1
        fi
        sleep 2
      done
    fi
    python3 -m venv '$VENV_DIR'
    '$VENV_DIR/bin/python' -m pip install --disable-pip-version-check --upgrade pip
    '$VENV_DIR/bin/python' -m pip install --disable-pip-version-check -r requirements.txt
    mkdir -p /home/agent/state/sessions
  "
}

run_service() {
  local service_command
  service_command="unset GH_TOKEN GITHUB_TOKEN COPILOT_GITHUB_TOKEN; exec '$VENV_DIR/bin/python' main.py"
  if [[ "${1:-}" == "detached" ]]; then
    if [[ -f "$ROOT_DIR/.env" ]]; then
      sbx env exec -d --env-file "$ROOT_DIR/.env" "$ENV_FILE" -- bash -lc "$service_command"
    else
      sbx env exec -d "$ENV_FILE" -- bash -lc "$service_command"
    fi
  elif [[ -f "$ROOT_DIR/.env" ]]; then
    sbx env exec --env-file "$ROOT_DIR/.env" "$ENV_FILE" -- bash -lc "$service_command"
  else
    sbx env exec "$ENV_FILE" -- bash -lc "$service_command"
  fi
}

require_sbx
command="${1:-}"

case "$command" in
  plan)
    sbx env plan "$ENV_FILE"
    ;;
  setup)
    create_sandbox
    configure_network
    install_dependencies
    ;;
  login)
    create_sandbox
    sbx env exec -it "$ENV_FILE" -- bash -lc "unset GH_TOKEN GITHUB_TOKEN COPILOT_GITHUB_TOKEN; copilot login"
    ;;
  run)
    create_sandbox
    configure_network
    install_dependencies
    run_service
    ;;
  start)
    create_sandbox
    configure_network
    install_dependencies
    run_service detached
    echo "Docker Sandbox service started at http://localhost:18088"
    ;;
  shell)
    create_sandbox
    sbx env exec -it "$ENV_FILE" -- bash -l
    ;;
  status)
    sbx ls
    sbx ports "$SANDBOX_NAME" || true
    ;;
  stop)
    sbx stop "$SANDBOX_NAME"
    ;;
  remove)
    sbx env rm --force "$ENV_FILE"
    ;;
  *)
    usage
    exit 2
    ;;
esac
