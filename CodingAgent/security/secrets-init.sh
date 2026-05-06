#!/usr/bin/env sh
# secrets-init.sh — Generate / reuse OpenClaw Gateway token and inject it
# into config/openclaw.json (gateway.auth.token + gateway.remote.token).
set -e

SECRETS_DIR="/run/secrets"
TOKEN_FILE="$SECRETS_DIR/gateway-token"
OPENCLAW_CONFIG="/openclaw-config/openclaw.json"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

EXISTING_TOKEN=""
if [ -s "$TOKEN_FILE" ]; then
  EXISTING_TOKEN="$(cat "$TOKEN_FILE")"
fi
if [ -z "$EXISTING_TOKEN" ] && [ -f "$OPENCLAW_CONFIG" ]; then
  apk add --no-cache jq >/dev/null 2>&1 || true
  if command -v jq >/dev/null 2>&1; then
    CURR="$(jq -r '.gateway.auth.token // ""' "$OPENCLAW_CONFIG" 2>/dev/null)"
    case "$CURR" in
      ""|change_me_to_a_random_secret_string|null) ;;
      *) EXISTING_TOKEN="$CURR" ;;
    esac
  fi
fi

if [ -n "$EXISTING_TOKEN" ]; then
  echo "[secrets-init] Reusing existing gateway token"
  NEW_TOKEN="$EXISTING_TOKEN"
else
  echo "[secrets-init] Generating new gateway token..."
  NEW_TOKEN=$(cat /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '-' || \
              head -c 32 /dev/urandom | xxd -p | head -c 48)
fi

if [ -f "$OPENCLAW_CONFIG" ]; then
  apk add --no-cache jq >/dev/null 2>&1 || true
  if command -v jq >/dev/null 2>&1; then
    jq --arg tok "$NEW_TOKEN" '
      .gateway.auth.token = $tok
      | .gateway.remote.url = "ws://127.0.0.1:18789"
      | .gateway.remote.transport = "direct"
      | .gateway.remote.token = $tok
    ' "$OPENCLAW_CONFIG" > /tmp/oc.tmp
    mv /tmp/oc.tmp "$OPENCLAW_CONFIG"
    echo "[secrets-init] Token synced into openclaw.json"
  else
    sed -i "s/change_me_to_a_random_secret_string/${NEW_TOKEN}/" "$OPENCLAW_CONFIG"
    echo "[secrets-init] Token synced via sed fallback"
  fi
fi

echo "$NEW_TOKEN" > "$TOKEN_FILE"
chmod 444 "$TOKEN_FILE"

# ──────────────────────────────────────────────────────────────────────
# Seed per-agent Copilot auth profiles so the gateway uses a stored
# token (no live token-exchange) — this avoids HTTP 403 errors when
# COPILOT_GITHUB_TOKEN does not have the Copilot OAuth scope, and matches
# the layout used by docs.openclaw.ai → "Non-interactive onboarding".
#
# Reference:
#   https://docs.openclaw.ai/providers/github-copilot#copilot-proxy-plugin-copilot-proxy
# ──────────────────────────────────────────────────────────────────────
if [ -n "${COPILOT_GITHUB_TOKEN:-}" ] && [ "$COPILOT_GITHUB_TOKEN" != "ghu_replace_me" ]; then
  AGENTS_BASE="/openclaw-config/agents"
  for agent in coder runner diagnoser; do
    DIR="$AGENTS_BASE/$agent/agent"
    mkdir -p "$DIR"
    cat > "$DIR/auth-profiles.json" <<JSON
{
  "version": 1,
  "profiles": {
    "github-copilot:github": {
      "type": "token",
      "provider": "github-copilot",
      "token": "${COPILOT_GITHUB_TOKEN}"
    }
  }
}
JSON
    cat > "$DIR/auth-state.json" <<JSON
{
  "version": 1,
  "lastGood": {
    "github-copilot": "github-copilot:github"
  }
}
JSON
    chmod 600 "$DIR/auth-profiles.json" "$DIR/auth-state.json" 2>/dev/null || true
  done
  echo "[secrets-init] Seeded Copilot auth profiles for: coder, runner, diagnoser"
else
  echo "[secrets-init] WARNING: COPILOT_GITHUB_TOKEN not set or unchanged — gateway will fall back to env-based token exchange (likely HTTP 403)."
fi

echo "[secrets-init] Token written ($(wc -c < $TOKEN_FILE) bytes). Done."
