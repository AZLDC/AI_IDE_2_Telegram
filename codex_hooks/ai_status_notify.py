"""Codex hook adapter for the AI status notification tool."""

import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
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
_CODEX_INTERNAL_DIRS = {
    "ambient-suggestions",
    "archived_sessions",
    "cache",
    "computer-use",
    "generated_images",
    "memories",
    "node_repl",
    "plugins",
    "sessions",
    "skills",
    "tmp",
    "visualizations",
}


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


def _normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _latest_workspace_root(transcript_path: Any) -> Path | None:
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        return None
    path = Path(transcript_path)
    try:
        with path.open("rb") as file:
            position = file.seek(0, os.SEEK_END)
            remainder = b""
            while position > 0:
                size = min(65536, position)
                position -= size
                file.seek(position)
                block = file.read(size) + remainder
                lines = block.splitlines()
                if position > 0:
                    remainder = lines.pop(0) if lines else block
                else:
                    remainder = b""
                for line in reversed(lines):
                    try:
                        record = json.loads(line.decode("utf-8-sig"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if record.get("type") != "turn_context":
                        continue
                    roots = record.get("payload", {}).get("workspace_roots")
                    if isinstance(roots, list) and roots and isinstance(roots[0], str):
                        return Path(roots[0])
    except OSError:
        return None
    return None


def _project_catalog(codex_home: Path) -> dict[str, str]:
    try:
        databases = sorted(
            codex_home.glob("state_*.sqlite"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    except OSError:
        return {}
    for database_path in databases:
        try:
            uri = f"file:{database_path.as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=1)) as database:
                rows = database.execute(
                    """
                    SELECT project_roots.path, projects.name
                    FROM project_roots
                    JOIN projects ON projects.id = project_roots.project_id
                    ORDER BY project_roots.position
                    """
                )
                return {
                    _normalized_path(root): name
                    for root, name in rows
                    if isinstance(root, str)
                    and root.strip()
                    and isinstance(name, str)
                    and name.strip()
                }
        except (OSError, sqlite3.Error):
            continue
    return {}


def _is_codex_internal(path: Path, codex_home: Path) -> bool:
    try:
        relative = path.resolve(strict=False).relative_to(
            codex_home.resolve(strict=False)
        )
    except (OSError, ValueError):
        return False
    return bool(relative.parts and relative.parts[0] in _CODEX_INTERNAL_DIRS)


def _git_root(path: Path) -> Path:
    candidate = path.resolve(strict=False)
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return candidate


def project_from_payload(
    payload: dict[str, Any], *, codex_home: Path | None = None
) -> str:
    home = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    workspace = _latest_workspace_root(payload.get("transcript_path"))
    if workspace is None:
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            candidate = Path(cwd)
            if not _is_codex_internal(candidate, home):
                workspace = _git_root(candidate)
    if workspace is not None:
        name = _project_catalog(home).get(_normalized_path(workspace))
        return name or workspace.name or "未知專案"
    return "未知專案"


def spawn(status: str, project: str) -> None:
    command = [
        sys.executable,
        str(TOOL),
        "--config",
        str(CONFIG),
        "--ide",
        "Codex",
        "--project",
        project,
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
        spawn(status, project_from_payload(payload))
    if os.environ.get("AI_STATUS_NOTIFY_DRY") == "1":
        print(f"STATUS={status or 'none'}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
