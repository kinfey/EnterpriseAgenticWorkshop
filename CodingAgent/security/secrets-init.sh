#!/usr/bin/env sh
# secrets-init.sh — Create runtime OpenClaw config and credentials.
set -e

SECRETS_DIR="/run/secrets"
TOKEN_FILE="$SECRETS_DIR/gateway-token"
OPENCLAW_CONFIG="/openclaw-config/openclaw.json"
OPENCLAW_TEMPLATE="/config-template/openclaw.json"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
mkdir -p /openclaw-config

if [ ! -f "$OPENCLAW_TEMPLATE" ]; then
  echo "[secrets-init] Missing config template: $OPENCLAW_TEMPLATE" >&2
  exit 1
fi

cp "$OPENCLAW_TEMPLATE" "$OPENCLAW_CONFIG"

EXISTING_TOKEN=""
if [ -s "$TOKEN_FILE" ]; then
  EXISTING_TOKEN="$(cat "$TOKEN_FILE")"
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
# Seed runtime-only per-agent Copilot auth profiles. The tracked config remains
# credential-free; OpenClaw resolves these profiles from config-vol.
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
  echo "[secrets-init] COPILOT_GITHUB_TOKEN is required." >&2
  exit 1
fi

chown -R 1000:1000 /openclaw-config

echo "[secrets-init] Token written ($(wc -c < $TOKEN_FILE) bytes). Done."
