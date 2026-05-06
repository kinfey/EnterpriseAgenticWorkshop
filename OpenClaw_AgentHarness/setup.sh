#!/usr/bin/env bash
# setup.sh — one-shot bootstrap for the OpenClaw Agent Harness
set -euo pipefail

GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; BOLD="\033[1m"; RESET="\033[0m"
info()    { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
section() { echo -e "\n${BOLD}━━━  $*  ━━━${RESET}"; }

section "Step 0 — Prerequisites"
command -v docker >/dev/null 2>&1 || { error "docker not found"; exit 1; }
docker compose version >/dev/null 2>&1 || { error "docker compose v2 required"; exit 1; }
info "Docker OK"

section "Step 1 — .env"
if [ ! -f .env ]; then
  TOKEN=$(openssl rand -hex 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(24))")
  sed "s/change_me_to_a_random_secret_string/${TOKEN}/" .env.example > .env
  info ".env created"
  warn "Edit .env and set COPILOT_GITHUB_TOKEN to a GitHub token with Copilot access."
else
  warn ".env already exists, skipping"
fi

if grep -q '^COPILOT_GITHUB_TOKEN=ghu_replace_me' .env; then
  error "COPILOT_GITHUB_TOKEN is not configured in .env."
  echo "  Edit .env and set COPILOT_GITHUB_TOKEN to your GitHub Copilot token."
  echo "  Tip:  echo \"COPILOT_GITHUB_TOKEN=\$(gh auth token)\" >> .env"
  exit 1
fi

section "Step 2 — Permissions"
chmod +x security/secrets-init.sh
chmod 700 config workspace 2>/dev/null || true
mkdir -p workspace/code
info "Filesystem permissions set"

section "Step 3 — Pull images"
docker pull alpine:3.19
docker pull python:3.12-slim
docker pull openclaw/openclaw:latest || warn "Could not pre-pull openclaw/openclaw — compose will retry on up."

section "Step 4 — Build harness image"
docker compose build harness

section "Done."
echo ""
echo -e "${BOLD}Run the self-loop pipeline:${RESET}"
echo "  docker compose up --abort-on-container-exit harness"
echo ""
echo -e "${BOLD}Or step-by-step:${RESET}"
echo "  docker compose up -d openclaw"
echo "  docker compose logs -f openclaw     # check gateway readiness"
echo "  docker compose run --rm harness     # run one full pipeline"
echo ""
echo -e "${BOLD}Replace the task spec:${RESET}"
echo "  edit workspace/code/SPEC.md, then re-run harness"
