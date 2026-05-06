"""
mcp_server.py — Expose the CodingAgent pipeline as a stdio MCP server so
OpenCode (or any MCP-aware client) can invoke it as a tool.

Tools:
  - codingagent_generate(spec, skills?, max_iterations?)
        Write SPEC.md → run the docker-compose pipeline → return the produced
        solution.py + RUN_LOG.md + DIAGNOSIS.md.
  - codingagent_list_skills()
        Return the catalogue of Skill documents under workspace/skills/.
  - codingagent_read_skill(name)
        Return the full text of one Skill document (so OpenCode users can
        @-reference it the same way the Coder Agent does internally).
  - codingagent_add_skill(name, content)
        Drop a new Skill document into workspace/skills/ so future SPEC.md
        files can reference it via @<name>.md.

This server is meant to run on the HOST (not inside the harness container).
It shells out to `docker compose` to drive the pipeline, which keeps token
rotation, sandboxing, and gateway lifecycle exactly as defined by
docker-compose.yml.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


PROJECT_ROOT = Path(os.getenv("CODINGAGENT_ROOT", Path(__file__).resolve().parent.parent))
WORKSPACE = PROJECT_ROOT / "workspace"
CODE_DIR = WORKSPACE / "code"
SKILLS_DIR = WORKSPACE / "skills"

COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
SKILL_REF_RE = re.compile(r"@([A-Za-z0-9_\-]+\.md)")


server: Server = Server("codingagent")


# ────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────

def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _ensure_paths() -> None:
    CODE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _validate_skill_refs(spec: str) -> tuple[list[str], list[str]]:
    """Return (resolved, missing) skill references found in `spec`."""
    found = list(dict.fromkeys(SKILL_REF_RE.findall(spec)))
    resolved = [r for r in found if (SKILLS_DIR / r).exists()]
    missing = [r for r in found if r not in resolved]
    return resolved, missing


def _run_pipeline(max_iterations: int, timeout: int) -> tuple[int, str]:
    """Run `docker compose up --abort-on-container-exit harness`."""
    env = os.environ.copy()
    env["MAX_ITERATIONS"] = str(max_iterations)
    cmd = [
        "docker", "compose",
        "-f", str(COMPOSE_FILE),
        "up",
        "--abort-on-container-exit",
        "--exit-code-from", "harness",
        "harness",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return 124, f"docker compose timed out after {timeout}s\n{e.stdout or ''}\n{e.stderr or ''}"
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


# ────────────────────────────────────────────────────────────────────
#  Tool registry
# ────────────────────────────────────────────────────────────────────

@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="codingagent_generate",
            description=(
                "Run the OpenClaw + Copilot self-correcting code-generation pipeline. "
                "Provide a Markdown SPEC (may reference @SKILL.md files); the server "
                "writes it to workspace/code/SPEC.md and drives Coder → Runner → "
                "Diagnoser until the solution passes or max_iterations is reached. "
                "Returns the final solution.py, RUN_LOG.md and DIAGNOSIS.md."
            ),
            inputSchema={
                "type": "object",
                "required": ["spec"],
                "properties": {
                    "spec": {
                        "type": "string",
                        "description": (
                            "Full SPEC.md content. Use `@FILE.md` lines under a "
                            "'## Required Skills' section to opt into existing skills."
                        ),
                    },
                    "max_iterations": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 4,
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 60,
                        "maximum": 3600,
                        "default": 1800,
                    },
                },
            },
        ),
        Tool(
            name="codingagent_list_skills",
            description="List available Skill documents under workspace/skills/.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="codingagent_read_skill",
            description="Return the full text of one Skill document by file name.",
            inputSchema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill file name, e.g. 'PYTHON_STYLE.md'.",
                    }
                },
            },
        ),
        Tool(
            name="codingagent_add_skill",
            description=(
                "Create or overwrite a Skill document under workspace/skills/. "
                "Future SPEC.md files can then reference it via @<name>.md."
            ),
            inputSchema={
                "type": "object",
                "required": ["name", "content"],
                "properties": {
                    "name": {"type": "string", "description": "File name, must end with .md"},
                    "content": {"type": "string"},
                },
            },
        ),
    ]


# ────────────────────────────────────────────────────────────────────
#  Tool dispatch
# ────────────────────────────────────────────────────────────────────

@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    _ensure_paths()

    if name == "codingagent_list_skills":
        items = sorted(p.name for p in SKILLS_DIR.glob("*.md"))
        if not items:
            return [TextContent(type="text", text="(no skills)")]
        body = "\n".join(f"- @{n}" for n in items)
        return [TextContent(type="text", text=body)]

    if name == "codingagent_read_skill":
        skill_name = arguments.get("name", "").strip()
        if not skill_name.endswith(".md"):
            skill_name += ".md"
        path = SKILLS_DIR / skill_name
        if not path.exists():
            return [TextContent(type="text", text=f"ERROR: skill '{skill_name}' not found")]
        return [TextContent(type="text", text=path.read_text(encoding="utf-8"))]

    if name == "codingagent_add_skill":
        skill_name = arguments.get("name", "").strip()
        content = arguments.get("content", "")
        if not skill_name.endswith(".md") or "/" in skill_name or skill_name.startswith("."):
            return [TextContent(type="text", text="ERROR: invalid skill name")]
        path = SKILLS_DIR / skill_name
        path.write_text(content, encoding="utf-8")
        return [TextContent(type="text", text=f"OK — wrote {path} ({len(content)} bytes)")]

    if name == "codingagent_generate":
        spec = arguments.get("spec", "")
        if not spec.strip():
            return [TextContent(type="text", text="ERROR: 'spec' is required")]
        max_iter = int(arguments.get("max_iterations", 4))
        timeout = int(arguments.get("timeout_seconds", 1800))

        resolved, missing = _validate_skill_refs(spec)

        # Wipe stale per-iteration artifacts so this run is clean.
        for fname in ("solution.py", "RUN_LOG.md", "DIAGNOSIS.md", "smoke_test.py", "test_solution.py"):
            f = CODE_DIR / fname
            if f.exists():
                f.unlink()
        (CODE_DIR / "SPEC.md").write_text(spec, encoding="utf-8")

        rc, log = _run_pipeline(max_iter, timeout)

        solution = _read(CODE_DIR / "solution.py")
        run_log = _read(CODE_DIR / "RUN_LOG.md")
        diagnosis = _read(CODE_DIR / "DIAGNOSIS.md")

        # Pull final status out of RUN_LOG.md if present.
        m = re.search(r"##\s*Result\s*\n+\s*(PASS|FAIL)", run_log, re.IGNORECASE)
        status = m.group(1).upper() if m else ("PASS" if rc == 0 else "FAIL")

        report = [
            f"## Pipeline Result\n{status}  (compose exit={rc})",
            f"## Skill References\nresolved: {resolved or '(none)'}"
            + (f"\nmissing: {missing}" if missing else ""),
            "## solution.py\n```python\n" + (solution or "(not produced)") + "\n```",
            "## RUN_LOG.md\n" + (run_log or "(not produced)"),
            "## DIAGNOSIS.md\n" + (diagnosis or "(not produced — pipeline either passed or skipped diagnosis)"),
        ]
        if status != "PASS":
            tail = "\n".join(log.strip().splitlines()[-40:])
            report.append("## Compose Log (tail)\n```\n" + tail + "\n```")
        return [TextContent(type="text", text="\n\n".join(report))]

    return [TextContent(type="text", text=f"ERROR: unknown tool '{name}'")]


# ────────────────────────────────────────────────────────────────────
#  Entrypoint
# ────────────────────────────────────────────────────────────────────

async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
