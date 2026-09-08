#!/usr/bin/env sh
# secrets-init.sh — Generate a fresh OpenClaw Gateway token on each boot
# and inject it into config/openclaw.json (gateway.auth.token).
set -e

SECRETS_DIR="/run/secrets"
TOKEN_FILE="$SECRETS_DIR/gateway-token"
OPENCLAW_CONFIG="/openclaw-config/openclaw.json"
OPENCLAW_CONFIG_TEMPLATE="/config-template/openclaw.json"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
mkdir -p "$(dirname "$OPENCLAW_CONFIG")"

# Idempotency: reuse the token from the secrets volume while this Compose
# deployment exists. Removing volumes intentionally rotates it.
EXISTING_TOKEN=""
if [ -s "$TOKEN_FILE" ]; then
  EXISTING_TOKEN="$(cat "$TOKEN_FILE")"
fi

if [ -n "$EXISTING_TOKEN" ]; then
  echo "[secrets-init] Reusing existing gateway token (already in config/secrets)"
  NEW_TOKEN="$EXISTING_TOKEN"
else
  echo "[secrets-init] Generating new gateway token..."
  NEW_TOKEN=$(cat /proc/sys/kernel/random/uuid 2>/dev/null | tr -d '-' || \
              head -c 32 /dev/urandom | xxd -p | head -c 48)
fi

# Build the runtime config atomically so a running gateway never observes the
# placeholder token from the tracked template.
apk add --no-cache jq >/dev/null 2>&1 || true
RUNTIME_TMP="/openclaw-config/openclaw.json.tmp"
if command -v jq >/dev/null 2>&1; then
  jq --arg tok "$NEW_TOKEN" '
    .gateway.auth.token = $tok
    | .gateway.remote.url = "ws://127.0.0.1:18789"
    | .gateway.remote.transport = "direct"
    | .gateway.remote.token = $tok
  ' "$OPENCLAW_CONFIG_TEMPLATE" > "$RUNTIME_TMP"
  echo "[secrets-init] Token synced into runtime config (auth + remote)"
else
  cp "$OPENCLAW_CONFIG_TEMPLATE" "$RUNTIME_TMP"
  sed -i "s/change_me_to_a_random_secret_string/${NEW_TOKEN}/g" "$RUNTIME_TMP"
  echo "[secrets-init] Token synced via sed fallback"
fi
chown 1000:1000 "$RUNTIME_TMP"
chmod 600 "$RUNTIME_TMP"
mv "$RUNTIME_TMP" "$OPENCLAW_CONFIG"
chown 1000:1000 /openclaw-config
chmod 700 /openclaw-config

echo "$NEW_TOKEN" > "$TOKEN_FILE"
chmod 444 "$TOKEN_FILE"

echo "[secrets-init] Token written to $TOKEN_FILE ($(wc -c < $TOKEN_FILE) bytes)"
echo "[secrets-init] Done."
