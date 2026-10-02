"""Cursor hook: ask telegram_notify.py to take one AI status, then return.

That program writes the desktop prompt immediately and batches Telegram itself.
Start this file with python.exe (or the machine's Python 3) directly.
On Windows, the `py` launcher can drop Cursor's stdin JSON — prefer python.exe.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# This file lives in <project>/cursor_hooks/ — project root is the parent folder.
ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "telegram_notify.py"
CONFIG = ROOT / "config.json"
MARKER = Path(
    os.environ.get(
        "AI_STATUS_MARKER",
        str(Path.home() / ".cursor" / "hooks" / "ai-status-notify.status"),
    )
)
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_STDIN_PREFIX = ""


def _decode_payload(raw: bytes) -> str:
    """Cursor on Windows may hand the event as UTF-8 with a BOM, or as UTF-16."""
    sample = raw[:4]
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if b"\x00" in sample:
        encoding = "utf-16-le" if sample[1:2] == b"\x00" else "utf-16-be"
        return raw.decode(encoding)
    return raw.decode("utf-8-sig")


def read_payload() -> dict:
    global _STDIN_PREFIX
    raw = sys.stdin.buffer.read()
    _STDIN_PREFIX = raw[:24].hex()
    if not raw.strip():
        return {}
    data = json.loads(_decode_payload(raw))
    return data if isinstance(data, dict) else {}


def consume_marker() -> str | None:
    if not MARKER.exists():
        return None
    text = MARKER.read_text(encoding="utf-8-sig").strip()
    MARKER.unlink(missing_ok=True)
    if text in ("AI_wait", "AI_fail", "AI_done"):
        return text
    return None


def status_for(event: str, payload: dict) -> str | None:
    """Map Cursor hook events to notify short names.

    Write tools, shell commands, and subagents send wait.
    Tool failures send fail. Agent stop sends done, unless a marker overrides it.
    """
    if event == "stop":
        marked = consume_marker()
        if marked is not None:
            return marked
        return "AI_done"
    if event == "postToolUseFailure":
        return "AI_fail"
    if event in (
        "subagentStart",
        "subagentStop",
        "preToolUse",
        "beforeShellExecution",
    ):
        return "AI_wait"
    return None


def spawn(status: str) -> None:
    command = [sys.executable, str(TOOL), "--config", str(CONFIG), status]
    kwargs = {
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


def cursor_output(event: str) -> str:
    if event in ("preToolUse", "subagentStart", "beforeShellExecution"):
        return '{"permission":"allow"}'
    return "{}"


def finish(event: str) -> None:
    print(cursor_output(event), flush=True)
    # Windows can treat a fast hook as finished before stdout is read.
    time.sleep(0.05)


def main() -> None:
    payload = read_payload()
    event = str(payload.get("hook_event_name") or "")
    status = status_for(event, payload)
    dry_run = os.environ.get("AI_STATUS_NOTIFY_DRY") == "1"
    if status and not dry_run:
        spawn(status)
    if dry_run:
        print(f"STATUS={status or 'none'}", file=sys.stderr, flush=True)
    finish(event)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log = Path.home() / ".cursor" / "hooks" / "ai_status_notify.err"
        try:
            log.write_text(
                f"{type(error).__name__}: {error}\nprefix={_STDIN_PREFIX}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print("{}", flush=True)
        time.sleep(0.05)
        sys.exit(0)
