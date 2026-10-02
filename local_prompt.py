"""Write and read the latest desktop prompt. One file, no batching."""

import time
from pathlib import Path

import telegram_notify


def format_stamp(when: float) -> str:
    seconds = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when))
    millis = int(round(when * 1000)) % 1000
    return f"{seconds}.{millis:03d}"


def write_prompt(path: Path, status: str, message: str, when: float) -> None:
    """Replace the current prompt. Callers see either the old file or the new one."""
    payload = f"TIME {format_stamp(when)}\nSTATUS {status}\n---\n{message}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def read_prompt(path: Path) -> tuple[str, str, str] | None:
    """Return ``(time, status, message)`` for the latest prompt."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    lines = text.splitlines()
    if len(lines) < 3 or not lines[0].startswith("TIME ") or not lines[1].startswith("STATUS "):
        return None
    if lines[2] != "---":
        return None
    return lines[0][5:], lines[1][7:], "\n".join(lines[3:])


def push_status(
    config_file: str | Path,
    prompt_file: str | Path,
    status: telegram_notify.Status,
    when: float | None = None,
) -> None:
    """Resolve the status text and publish it at once."""
    config = telegram_notify.load_config(str(config_file))
    write_prompt(
        Path(prompt_file),
        status,
        config.message_for(status),
        time.time() if when is None else when,
    )
