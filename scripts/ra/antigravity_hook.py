"""Antigravity lifecycle hook adapter for the Research Paper Agent workspace guardrails.

Connects Antigravity's .agents/hooks.json events to scripts/ra/hooks.py.
Handles tool argument translation, Windows-to-WSL path conversion, and formats
stdout JSON according to Antigravity's hook contract.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from . import core, hooks


def to_wsl_path(p: str | None) -> str | None:
    if not p:
        return p
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return p.replace("\\", "/")


def to_hook_payload(event: str, agy: dict) -> tuple[str, dict] | None:
    sid = agy.get("conversationId") or agy.get("session_id")
    tc = agy.get("toolCall") or {}
    tool = tc.get("name") or ""
    args = tc.get("args") or {}

    base = {"session_id": sid, "cwd": str(core.ws())}

    if event == "pre-tool":
        if tool == "edit_file":
            return "pre-edit", {
                **base,
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": to_wsl_path(args.get("Path")),
                    "old_string": args.get("Target", ""),
                    "new_string": args.get("Replacement", ""),
                },
            }
        elif tool == "write_file":
            return "pre-edit", {
                **base,
                "tool_name": "Write",
                "tool_input": {
                    "file_path": to_wsl_path(args.get("Path")),
                    "content": args.get("Content", ""),
                },
            }
        elif tool == "read_file":
            return "pre-read", {
                **base,
                "tool_name": "Read",
                "tool_input": {
                    "file_path": to_wsl_path(args.get("Path")),
                },
            }
        elif tool == "run_command":
            return "pre-bash", {
                **base,
                "tool_name": "Bash",
                "tool_input": {
                    "command": args.get("CommandLine", ""),
                },
            }
        elif tool == "invoke_subagent":
            return "pre-skill", {
                **base,
                "tool_name": "Skill",
                "tool_input": {
                    "skill": args.get("TypeName") or args.get("Role", ""),
                },
            }
        return None

    elif event == "post-tool":
        if tool in ("edit_file", "write_file"):
            return "post-edit", {
                **base,
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": to_wsl_path(args.get("Path")),
                },
            }
        return None

    elif event == "session-start":
        return "session-start", {**base, "source": "startup"}

    return None


def handle_pre_tool(agy: dict) -> dict:
    mapped = to_hook_payload("pre-tool", agy)
    if not mapped:
        return {"decision": "allow"}

    hook_event, data = mapped
    handler = hooks.HANDLERS.get(hook_event)
    if not handler:
        return {"decision": "allow"}

    err_buf = io.StringIO()
    out_buf = io.StringIO()
    with redirect_stderr(err_buf), redirect_stdout(out_buf):
        rc = handler(data)

    err_text = err_buf.getvalue().strip()
    if rc != 0:
        reason = err_text or "[workspace guard] BLOCKED: Action not permitted by workspace rules."
        return {"decision": "deny", "reason": reason}

    return {"decision": "allow"}


def handle_post_tool(agy: dict) -> dict:
    mapped = to_hook_payload("post-tool", agy)
    if not mapped:
        return {}

    hook_event, data = mapped
    handler = hooks.HANDLERS.get(hook_event)
    if handler:
        err_buf = io.StringIO()
        out_buf = io.StringIO()
        with redirect_stderr(err_buf), redirect_stdout(out_buf):
            try:
                handler(data)
            except Exception:
                pass
    return {}


def handle_session_start(agy: dict) -> dict:
    sid = agy.get("conversationId")
    hooks.session_start({"session_id": sid, "source": "startup"})
    active = core.active_paper()
    msg = f"[research-agent workspace] Active paper: {active or '(none)'}. Framework is shared, each paper isolated."
    return {"injectSteps": [{"systemMessage": {"systemMessage": msg}}]}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    event = argv[0] if argv else "pre-tool"

    try:
        raw = sys.stdin.read()
        agy = json.loads(raw) if raw.strip() else {}
    except Exception:
        agy = {}

    res = {}
    if event == "pre-tool":
        res = handle_pre_tool(agy)
    elif event == "post-tool":
        res = handle_post_tool(agy)
    elif event == "session-start":
        res = handle_session_start(agy)

    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
