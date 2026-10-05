"""Codex hook adapter for the AI status notification tool."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "telegram_notify.py"
CONFIG = ROOT / "config.json"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_NONZERO_EXIT = re.compile(r"(?:exit(?:ed)?(?:\s+with)?(?:\s+status)?|code)\D*(-?\d+)", re.IGNORECASE)


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        return {}
    data = json.loads(raw.decode("utf-8-sig"))
    return data if isinstance(data, dict) else {}


def tool_failed(response: Any) -> bool:
    if isinstance(response, dict):
        if response.get("isError") is True or response.get("success") is False:
            return True
        for key in ("exit_code", "exitCode", "code"):
            value = response.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value != 0
        status = response.get("status")
        if isinstance(status, str) and status.lower() in {"error", "failed", "failure"}:
            return True
        error = response.get("error")
        if error not in (None, "", False, 0, [], {}):
            return True
        return any(tool_failed(value) for value in response.values())
    if isinstance(response, list):
        return any(tool_failed(item) for item in response)
    if isinstance(response, str):
        match = _NONZERO_EXIT.search(response)
        return bool(match and int(match.group(1)) != 0)
    return False


def status_for(event: str, payload: dict[str, Any]) -> str | None:
    if event == "Interrupt":
        return "AI_fail"
    if event == "Stop":
        return "AI_done"
    if event == "PostToolUse":
        return "AI_fail" if tool_failed(payload.get("tool_response")) else None
    if event in {
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "SubagentStart",
        "SubagentStop",
    }:
        return "AI_wait"
    return None


def spawn(status: str) -> None:
    command = [
        sys.executable,
        str(TOOL),
        "--config",
        str(CONFIG),
        "--ide",
        "Codex",
        status,
    ]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            DETACHED_PROCESS
            | CREATE_NEW_PROCESS_GROUP
            | CREATE_NO_WINDOW
            | CREATE_BREAKAWAY_FROM_JOB
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def main() -> None:
    payload = read_payload()
    status = status_for(str(payload.get("hook_event_name") or ""), payload)
    if status and os.environ.get("AI_STATUS_NOTIFY_DRY") != "1":
        spawn(status)
    if os.environ.get("AI_STATUS_NOTIFY_DRY") == "1":
        print(f"STATUS={status or 'none'}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
