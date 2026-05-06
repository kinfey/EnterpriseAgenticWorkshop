"""
openclaw_client.py — Drive OpenClaw agents via `docker exec` (Option A).

The OpenClaw 2026.5.x gateway speaks WebSocket only — there is no
OpenAI-compatible REST endpoint. So we shell into the running openclaw
container and invoke its built-in CLI:

    docker exec <container> node /app/openclaw.mjs agent \\
        --agent <id> --message <prompt> --json --timeout <s>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid

import requests


OPENCLAW_GATEWAY = os.getenv("OPENCLAW_GATEWAY", "http://openclaw:18789")
OPENCLAW_CONTAINER = os.getenv("OPENCLAW_CONTAINER", "codingagent-openclaw")
OPENCLAW_CLI = os.getenv("OPENCLAW_CLI", "node /app/openclaw.mjs")


def check_health(timeout: int = 5) -> bool:
    for path in ("/health", "/healthz"):
        try:
            r = requests.get(f"{OPENCLAW_GATEWAY}{path}", timeout=timeout)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


def wait_for_gateway(max_wait: int = 180) -> None:
    print(f"[openclaw_client] Waiting for gateway at {OPENCLAW_GATEWAY} ...", flush=True)
    start = time.time()
    while time.time() - start < max_wait:
        if check_health():
            print("[openclaw_client] Gateway ready ✓", flush=True)
            return
        print("  .", end="", flush=True)
        time.sleep(3)
    raise RuntimeError(
        f"OpenClaw gateway did not become ready within {max_wait}s. "
        "Check `docker logs codingagent-openclaw`."
    )


def _ensure_docker_available() -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("`docker` CLI not found in the harness container.")
    if not os.path.exists("/var/run/docker.sock"):
        raise RuntimeError("/var/run/docker.sock is not mounted into the harness container.")


def _extract_reply(stdout: str) -> str:
    """
    The CLI emits diagnostic lines + a final JSON object when --json is set.
    Find the last balanced JSON object and pull the assistant text out of it;
    fall back to raw stdout.
    """
    text = stdout.strip()
    if not text:
        return ""

    end = text.rfind("}")
    while end != -1:
        depth = 0
        for i in range(end, -1, -1):
            ch = text[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    candidate = text[i : end + 1]
                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    for key in ("reply", "result", "response"):
                        if isinstance(obj.get(key), dict):
                            inner = obj[key]
                            for k in ("content", "text", "message"):
                                v = inner.get(k)
                                if isinstance(v, str) and v.strip():
                                    return v.strip()
                    for k in ("content", "text", "message", "output"):
                        v = obj.get(k)
                        if isinstance(v, str) and v.strip():
                            return v.strip()
                    return candidate
        end = text.rfind("}", 0, end)

    return text


def call_agent(
    agent_id: str,
    prompt: str,
    *,
    timeout: int = 600,
    max_retries: int = 2,
) -> str:
    """Run one turn of the named OpenClaw agent and return assistant text."""
    _ensure_docker_available()

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        print(
            f"[openclaw_client] → agent='{agent_id}' "
            f"(attempt {attempt}/{max_retries}, prompt={len(prompt)} chars)",
            flush=True,
        )

        cmd = [
            "docker", "exec", "-i",
            OPENCLAW_CONTAINER,
            *OPENCLAW_CLI.split(),
            "agent",
            "--agent", agent_id,
            "--session-id", uuid.uuid4().hex,
            "--message", prompt,
            "--json",
            "--timeout", str(timeout),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
            time.sleep(3 * attempt)
            continue

        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-15:]
            raise RuntimeError(
                f"OpenClaw CLI failed for agent '{agent_id}' "
                f"(exit {proc.returncode}):\n  " + "\n  ".join(tail)
            )

        content = _extract_reply(proc.stdout)
        if not content and proc.stderr:
            content = proc.stderr.strip()

        print(
            f"[openclaw_client] ← agent='{agent_id}' ({len(content)} chars)",
            flush=True,
        )
        return content

    raise RuntimeError(
        f"Cannot run OpenClaw CLI for agent '{agent_id}' after "
        f"{max_retries} attempts: {last_err}"
    )
