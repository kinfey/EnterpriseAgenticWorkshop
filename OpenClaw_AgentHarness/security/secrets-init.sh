#!/usr/bin/env sh
# secrets-init.sh — Generate a fresh OpenClaw Gateway token on each boot
# and inject it into config/openclaw.json (gateway.auth.token).
set -e

SECRETS_DIR="/run/secrets"
TOKEN_FILE="$SECRETS_DIR/gateway-token"
OPENCLAW_CONFIG="/openclaw-config/openclaw.json"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# Idempotency: if the openclaw.json already has a non-placeholder token, reuse
# it. Rotating while the gateway is still running leaves it with a stale
# in-memory token and breaks the in-container CLI (which compares
# gateway.remote.token to the gateway's live gateway.auth.token).
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
  echo "[secrets-init] Reusing existing gateway token (already in config/secrets)"
  NEW_TOKEN="$EXISTING_TOKEN"
else
  echo "[secrets-init] Generating new gateway token..."
  NEW_TOKEN=$(cat /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '-' || \
              head -c 32 /dev/urandom | xxd -p | head -c 48)
fi

# Sync token into openclaw.json BEFORE writing the secret file so the
# gateway never reads a stale token.
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
    echo "[secrets-init] Token synced into openclaw.json (auth + remote)"
  else
    # Fallback: sed replacement of the placeholder
    sed -i "s/change_me_to_a_random_secret_string/${NEW_TOKEN}/" "$OPENCLAW_CONFIG"
    echo "[secrets-init] Token synced via sed fallback"
  fi
fi

echo "$NEW_TOKEN" > "$TOKEN_FILE"
chmod 444 "$TOKEN_FILE"

echo "[secrets-init] Token written to $TOKEN_FILE ($(wc -c < $TOKEN_FILE) bytes)"
echo "[secrets-init] Done."
