import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

if sys.platform == "win32":
    import msvcrt


Status = Literal["AI_wait", "AI_fail", "AI_done", "AI_testWait", "AI_testDone"]
IDE = Literal["CLI", "Codex", "Cursor"]
Lane = Literal["real", "test"]
WINDOW_SECONDS = 10.0
UNKNOWN_PROJECT = "未知專案"
REAL_STATUSES = ("AI_wait", "AI_fail", "AI_done")
TEST_STATUSES = ("AI_testWait", "AI_testDone")
STATUSES = REAL_STATUSES + TEST_STATUSES
DEFAULT_MESSAGES = {
    "AI_wait": "{platform}上的{IDE} A.I.正準備執行外部指令.",
    "AI_fail": "{platform}上的{IDE} A.I.執行指令失敗.",
    "AI_done": "{platform}上的{IDE} A.I.的工作已完成.",
    "AI_testWait": "{platform}上的{IDE} A.I.測試發送寫檔訊息.",
    "AI_testDone": "{platform}上的{IDE} A.I.測試發送完成訊息.",
}


def current_platform() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "Mac"
    if sys.platform.startswith("linux"):
        return "Linux"
    return sys.platform


def render_message(
    template: str,
    ide: IDE,
    platform_name: str | None = None,
    *,
    project: str = UNKNOWN_PROJECT,
) -> str:
    """Replace only the documented notification placeholders."""
    return (
        template.replace("{platform}", platform_name or current_platform())
        .replace("{IDE}", ide)
        .replace("{project}", project or UNKNOWN_PROJECT)
    )


def _lane(status: Status) -> Lane:
    if status in TEST_STATUSES:
        return "test"
    return "real"


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str
    AI_wait: str
    AI_fail: str
    AI_done: str
    AI_testWait: str
    AI_testDone: str
    coalesce_seconds: float
    auto_delete_seconds: float

    def message_for(
        self,
        status: Status,
        *,
        ide: IDE = "CLI",
        project: str = UNKNOWN_PROJECT,
        platform_name: str | None = None,
    ) -> str:
        return render_message(
            getattr(self, status), ide, platform_name, project=project
        )


def _parse_positive_seconds(data: dict, field: str, *, default: float) -> float:
    """Parse a positive seconds field; missing/blank/invalid uses `default`."""
    if field not in data:
        return default
    value = data[field]
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            value = float(text)
        except ValueError:
            return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    seconds = float(value)
    if seconds <= 0:
        return default
    return seconds


def _parse_coalesce_seconds(data: dict) -> float:
    """Use WINDOW_SECONDS when the field is missing, blank, or not a positive number."""
    return _parse_positive_seconds(data, "coalesce_seconds", default=WINDOW_SECONDS)


def _parse_auto_delete_seconds(data: dict) -> float:
    """Return 0.0 (disabled) when missing, blank, zero, or not a positive number."""
    return _parse_positive_seconds(data, "auto_delete_seconds", default=0.0)


def _string_or_default(data: dict, field: str, default: str | None = None) -> str:
    value = data.get(field, default)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if default is not None:
        return default
    raise ValueError(f"設定檔缺少非空白字串欄位：{field}")


def load_config(config_file: str) -> TelegramConfig:
    """Read and validate the Telegram notification JSON file."""
    path = Path(config_file)

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise ValueError(f"找不到設定檔：{path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"設定檔不是有效的 JSON：{path} ({error.msg})"
        ) from error

    if not isinstance(data, dict):
        raise ValueError("設定檔最外層必須是 JSON 物件")

    return TelegramConfig(
        token=_string_or_default(data, "token"),
        chat_id=_string_or_default(data, "chat_id"),
        AI_wait=_string_or_default(data, "AI_wait", DEFAULT_MESSAGES["AI_wait"]),
        AI_fail=_string_or_default(data, "AI_fail", DEFAULT_MESSAGES["AI_fail"]),
        AI_done=_string_or_default(data, "AI_done", DEFAULT_MESSAGES["AI_done"]),
        AI_testWait=_string_or_default(
            data, "AI_testWait", DEFAULT_MESSAGES["AI_testWait"]
        ),
        AI_testDone=_string_or_default(
            data, "AI_testDone", DEFAULT_MESSAGES["AI_testDone"]
        ),
        coalesce_seconds=_parse_coalesce_seconds(data),
        auto_delete_seconds=_parse_auto_delete_seconds(data),
    )


def _telegram_post(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(token: str, chat_id: str, message: str) -> int:
    """Send one message through the Telegram Bot API; return message_id."""
    result = _telegram_post(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": message},
    )
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 傳送失敗：{result}")
    message_id = result.get("result", {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError(f"Telegram 回應缺少 message_id：{result}")
    return message_id


def delete_message(token: str, chat_id: str, message_id: int) -> None:
    """Delete one bot message through the Telegram Bot API."""
    result = _telegram_post(
        token,
        "deleteMessage",
        {"chat_id": chat_id, "message_id": message_id},
    )
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 刪除失敗：{result}")


def notify(
    config_file: str,
    status: Status,
    *,
    ide: IDE = "CLI",
    project: str = UNKNOWN_PROJECT,
    state_dir: Path | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    config = load_config(config_file)
    message_id = send_message(
        config.token,
        config.chat_id,
        config.message_for(status, ide=ide, project=project),
    )
    arm_auto_delete(
        config,
        state_dir or Path(__file__).resolve().parent,
        message_id,
        config_file=config_file,
        clock=clock,
        sleep=sleep,
    )


def deliver_free_message(
    config_file: str,
    text: str,
    *,
    state_dir: Path | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Send one free-form Telegram message now. Does not join status coalesce."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("自由訊息不可空白")
    clock = clock or time.time
    directory = state_dir or Path(__file__).resolve().parent
    from local_prompt import write_prompt

    write_prompt(directory / "local_prompt.txt", "message", cleaned, clock())
    config = load_config(config_file)
    message_id = send_message(config.token, config.chat_id, cleaned)
    arm_auto_delete(
        config,
        directory,
        message_id,
        config_file=config_file,
        clock=clock,
        sleep=sleep,
    )


@dataclass(frozen=True)
class _Batch:
    token: str
    deadline: float
    status: Status
    ide: IDE
    project: str


@dataclass(frozen=True)
class PendingStatus:
    status: Status
    ide: IDE
    project: str = UNKNOWN_PROJECT


@dataclass(frozen=True)
class SubmitResult:
    role: Literal["leader", "follower"]
    token: str
    deadline: float
    immediate: Status | None = None
    immediate_ide: IDE = "CLI"
    immediate_project: str = UNKNOWN_PROJECT


class _FileLock:
    """Lock one byte so overlapping calls share one quiet window."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a+b")
        self._file.seek(0, os.SEEK_END)
        if self._file.tell() == 0:
            self._file.write(b"\0")
            self._file.flush()
        self._file.seek(0)
        if sys.platform == "win32":
            msvcrt.locking(self._file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._file is None:
            return
        self._file.seek(0)
        if sys.platform == "win32":
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None


def _batch_paths(state_dir: Path, lane: Lane = "real") -> tuple[Path, Path]:
    name = "notify_batch" if lane == "real" else "notify_batch_test"
    return state_dir / f"{name}.state", state_dir / f"{name}.lock"


def _read_batch(path: Path) -> _Batch | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    values = text.splitlines()
    if len(values) == 3:
        token, deadline, status = values
        ide = "CLI"
        project = UNKNOWN_PROJECT
    elif len(values) == 4:
        token, deadline, status, ide = values
        project = UNKNOWN_PROJECT
    else:
        token, deadline, status, ide, project = values[:5]
    if status not in STATUSES:
        raise ValueError(f"無法辨認的通知狀態：{status}")
    if ide not in ("CLI", "Codex", "Cursor"):
        raise ValueError(f"無法辨認的通知來源：{ide}")
    return _Batch(token, float(deadline), status, ide, project or UNKNOWN_PROJECT)


def _write_batch(path: Path, batch: _Batch) -> None:
    path.write_text(
        f"{batch.token}\n{batch.deadline}\n{batch.status}\n{batch.ide}\n{batch.project}\n",
        encoding="utf-8",
    )


def _clear_batch(path: Path) -> None:
    path.unlink(missing_ok=True)


def submit_status(
    state_dir: Path,
    status: Status,
    *,
    ide: IDE = "CLI",
    project: str = UNKNOWN_PROJECT,
    now: float,
    window: float = WINDOW_SECONDS,
) -> SubmitResult:
    """Keep the latest status and push the deadline out by `window` seconds."""
    state_path, lock_path = _batch_paths(state_dir, _lane(status))
    with _FileLock(lock_path):
        current = _read_batch(state_path)
        immediate = None
        if current is not None and now >= current.deadline:
            immediate = PendingStatus(current.status, current.ide, current.project)
            _clear_batch(state_path)
            current = None
        if current is None:
            batch = _Batch(uuid.uuid4().hex, now + window, status, ide, project)
            _write_batch(state_path, batch)
            return SubmitResult(
                "leader",
                batch.token,
                batch.deadline,
                immediate.status if immediate else None,
                immediate.ide if immediate else "CLI",
                immediate.project if immediate else UNKNOWN_PROJECT,
            )
        batch = _Batch(current.token, now + window, status, ide, project)
        _write_batch(state_path, batch)
        return SubmitResult(
            "follower",
            batch.token,
            batch.deadline,
            immediate.status if immediate else None,
            immediate.ide if immediate else "CLI",
            immediate.project if immediate else UNKNOWN_PROJECT,
        )


def _claim(state_dir: Path, lane: Lane, token: str, now: float) -> PendingStatus | None:
    state_path, lock_path = _batch_paths(state_dir, lane)
    with _FileLock(lock_path):
        current = _read_batch(state_path)
        if current is None or current.token != token:
            return None
        if now < current.deadline:
            return None
        _clear_batch(state_path)
        return PendingStatus(current.status, current.ide, current.project)


def take_ready_notification(
    state_dir: Path, token: str, *, now: float
) -> PendingStatus | None:
    """Claim this window once its deadline has arrived."""
    for lane in ("real", "test"):
        ready = _claim(state_dir, lane, token, now)
        if ready is not None:
            return ready
    return None


def take_ready(state_dir: Path, token: str, *, now: float) -> Status | None:
    """Compatibility wrapper returning only the claimed status."""
    ready = take_ready_notification(state_dir, token, now=now)
    return ready.status if ready else None


def _peek_deadline(state_dir: Path, token: str) -> float | None:
    for lane in ("real", "test"):
        state_path, lock_path = _batch_paths(state_dir, lane)
        with _FileLock(lock_path):
            current = _read_batch(state_path)
            if current is not None and current.token == token:
                return current.deadline
    return None


@dataclass(frozen=True)
class _DeleteBatch:
    token: str
    deadline: float
    message_ids: tuple[int, ...]
    phase: Literal["waiting", "deleting"]


@dataclass(frozen=True)
class DeleteSubmitResult:
    token: str
    deadline: float


def _delete_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "notify_delete.state", state_dir / "notify_delete.lock"


def _read_delete_batch(path: Path) -> _DeleteBatch | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("待清空狀態必須是 JSON 物件")
    token = data.get("token")
    deadline = data.get("deadline")
    message_ids = data.get("message_ids")
    phase = data.get("phase", "waiting")
    if not isinstance(token, str) or not token:
        raise ValueError("待清空狀態缺少 token")
    if not isinstance(deadline, (int, float)) or isinstance(deadline, bool):
        raise ValueError("待清空狀態缺少 deadline")
    if phase not in ("waiting", "deleting"):
        raise ValueError("待清空狀態 phase 無效")
    if not isinstance(message_ids, list) or not message_ids:
        raise ValueError("待清空狀態缺少 message_ids")
    ids: list[int] = []
    for item in message_ids:
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError("待清空狀態 message_ids 必須是整數清單")
        ids.append(item)
    return _DeleteBatch(token, float(deadline), tuple(ids), phase)


def _write_delete_batch(path: Path, batch: _DeleteBatch) -> None:
    path.write_text(
        json.dumps(
            {
                "token": batch.token,
                "deadline": batch.deadline,
                "message_ids": list(batch.message_ids),
                "phase": batch.phase,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _clear_delete_batch(path: Path) -> None:
    path.unlink(missing_ok=True)


def submit_delete(
    state_dir: Path,
    message_id: int,
    *,
    now: float,
    window: float,
) -> DeleteSubmitResult:
    """Append a message id. Reset the quiet window unless a delete is in flight.

    While `deleting`, only enqueue the id so the in-flight job finishes first;
    leftover ids (including this one) get a new waiting window afterwards.
    """
    state_path, lock_path = _delete_paths(state_dir)
    with _FileLock(lock_path):
        current = _read_delete_batch(state_path)
        ids = list(current.message_ids) if current is not None else []
        ids.append(message_id)
        if current is not None and current.phase == "deleting":
            batch = _DeleteBatch(
                current.token, current.deadline, tuple(ids), "deleting"
            )
            _write_delete_batch(state_path, batch)
            return DeleteSubmitResult(batch.token, batch.deadline)
        batch = _DeleteBatch(
            uuid.uuid4().hex, now + window, tuple(ids), "waiting"
        )
        _write_delete_batch(state_path, batch)
        return DeleteSubmitResult(batch.token, batch.deadline)


def _peek_delete_deadline(state_dir: Path, token: str) -> float | None:
    state_path, lock_path = _delete_paths(state_dir)
    with _FileLock(lock_path):
        current = _read_delete_batch(state_path)
        if current is None or current.token != token:
            return None
        if current.phase == "deleting":
            return None
        return current.deadline


def begin_delete(
    state_dir: Path, token: str, *, now: float
) -> tuple[int, ...] | None:
    """Move waiting → deleting and return a snapshot of ids to remove."""
    state_path, lock_path = _delete_paths(state_dir)
    with _FileLock(lock_path):
        current = _read_delete_batch(state_path)
        if current is None or current.token != token:
            return None
        if current.phase != "waiting":
            return None
        if now < current.deadline:
            return None
        batch = _DeleteBatch(
            current.token, current.deadline, current.message_ids, "deleting"
        )
        _write_delete_batch(state_path, batch)
        return current.message_ids


def finish_delete(
    state_dir: Path,
    snapshot: tuple[int, ...],
    succeeded: set[int],
    *,
    now: float,
    window: float,
) -> DeleteSubmitResult | None:
    """Drop successfully deleted ids; re-arm waiting if any ids remain."""
    state_path, lock_path = _delete_paths(state_dir)
    with _FileLock(lock_path):
        current = _read_delete_batch(state_path)
        if current is None:
            return None
        remaining = [item for item in current.message_ids if item not in succeeded]
        if not remaining:
            _clear_delete_batch(state_path)
            return None
        batch = _DeleteBatch(
            uuid.uuid4().hex, now + window, tuple(remaining), "waiting"
        )
        _write_delete_batch(state_path, batch)
        return DeleteSubmitResult(batch.token, batch.deadline)


def flush_delete_scheduled(
    config_file: str,
    state_dir: Path,
    token: str,
    deadline: float,
    *,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Serially delete all queued local message ids after each quiet window."""
    clock = clock or time.time
    sleep = sleep or time.sleep
    error_log = state_dir / "notify_delete.err"
    config = load_config(config_file)
    window = config.auto_delete_seconds
    if window <= 0:
        return
    try:
        while True:
            delay = deadline - clock()
            if delay > 0:
                sleep(delay)
            next_deadline = _peek_delete_deadline(state_dir, token)
            if next_deadline is None:
                # Token replaced, idle, or another worker is deleting.
                return
            if next_deadline > clock():
                deadline = next_deadline
                continue
            snapshot = begin_delete(state_dir, token, now=clock())
            if snapshot is None:
                return
            failures: list[str] = []
            succeeded: set[int] = set()
            for message_id in snapshot:
                try:
                    delete_message(config.token, config.chat_id, message_id)
                    succeeded.add(message_id)
                except Exception as error:
                    failures.append(f"{message_id}:{type(error).__name__}: {error}")
            if failures:
                try:
                    error_log.write_text(
                        "\n".join(failures) + "\n", encoding="utf-8"
                    )
                except OSError:
                    pass
            follow = finish_delete(
                state_dir,
                snapshot,
                succeeded,
                now=clock(),
                window=window,
            )
            if follow is None:
                return
            # New ids were queued during delete (or retries remain): keep working.
            token = follow.token
            deadline = follow.deadline
            if sleep is not None:
                continue
            try:
                _spawn_deleter(config_file, state_dir, token, deadline)
            except OSError:
                continue
            return
    except Exception as error:
        try:
            error_log.write_text(
                f"{type(error).__name__}: {error}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        raise


def _spawn_deleter(
    config_file: str, state_dir: Path, token: str, deadline: float
) -> None:
    """Ask a detached process to clear tracked messages when the window closes."""
    _detached_popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--delete-flush",
            "--config",
            config_file,
            "--state-dir",
            str(state_dir),
            "--token",
            token,
            "--deadline",
            repr(float(deadline)),
        ]
    )


def arm_auto_delete(
    config: TelegramConfig,
    state_dir: Path,
    message_id: int,
    *,
    config_file: str | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> DeleteSubmitResult | None:
    """Record a sent message and arm quiet-window deletion when enabled."""
    if config.auto_delete_seconds <= 0:
        return None
    clock = clock or time.time
    result = submit_delete(
        state_dir,
        message_id,
        now=clock(),
        window=config.auto_delete_seconds,
    )
    path = config_file or str(Path(__file__).resolve().with_name("config.json"))
    # While another delete is in flight, only enqueue; that worker re-arms after.
    state_path, lock_path = _delete_paths(state_dir)
    with _FileLock(lock_path):
        current = _read_delete_batch(state_path)
        if current is not None and current.phase == "deleting":
            return result
    if sleep is not None:
        flush_delete_scheduled(
            path,
            state_dir,
            result.token,
            result.deadline,
            clock=clock,
            sleep=sleep,
        )
        return result
    try:
        _spawn_deleter(path, state_dir, result.token, result.deadline)
    except OSError:
        flush_delete_scheduled(
            path,
            state_dir,
            result.token,
            result.deadline,
            clock=clock,
        )
    return result


def flush_scheduled(
    config_file: str,
    state_dir: Path,
    token: str,
    deadline: float,
    *,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Send the latest status once quiet for the full window after the last update."""
    clock = clock or time.time
    sleep = sleep or time.sleep
    error_log = state_dir / "notify_flush.err"
    try:
        while True:
            delay = deadline - clock()
            if delay > 0:
                sleep(delay)
            next_deadline = _peek_deadline(state_dir, token)
            if next_deadline is None:
                return
            if next_deadline > clock():
                deadline = next_deadline
                continue
            ready = take_ready_notification(state_dir, token, now=clock())
            if ready is None:
                return
            try:
                notify(
                    config_file,
                    ready.status,
                    ide=ready.ide,
                    project=ready.project,
                    state_dir=state_dir,
                )
            except Exception as error:
                error_log.write_text(
                    f"{type(error).__name__}: {error}\n",
                    encoding="utf-8",
                )
                raise
            return
    except Exception as error:
        try:
            error_log.write_text(
                f"{type(error).__name__}: {error}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        raise


def _release_parent(process: subprocess.Popen[bytes]) -> None:
    """Drop the handle without treating a still-running child as our job."""
    if process.poll() is None:
        process.returncode = 0


def _detached_popen(command: list[str]) -> None:
    """Start a process the hook runner will not wait for."""
    shared = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # DETACHED + breakaway so Cursor/hook job exit does not kill the flusher.
        flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
            | 0x01000000
        )
        try:
            process = subprocess.Popen(command, creationflags=flags, **shared)
        except OSError:
            process = subprocess.Popen(
                command,
                creationflags=(
                    subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                ),
                **shared,
            )
        _release_parent(process)
        return
    process = subprocess.Popen(command, start_new_session=True, **shared)
    _release_parent(process)


def _spawn_flusher(
    config_file: str, state_dir: Path, token: str, deadline: float
) -> None:
    """Ask a detached process to send this window when it closes."""
    # Use the same interpreter as this process. pythonw hides flush errors.
    _detached_popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--flush",
            "--config",
            config_file,
            "--state-dir",
            str(state_dir),
            "--token",
            token,
            "--deadline",
            repr(float(deadline)),
        ]
    )


def deliver(
    config_file: str,
    status: Status,
    *,
    ide: IDE = "CLI",
    project: str = UNKNOWN_PROJECT,
    state_dir: Path | None = None,
    window: float | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Update the desktop prompt now, and fold Telegram into one later send.

    The hook process returns as soon as the status is recorded. Sleeping here
    would make the next hook start only after this send, so every status would
    become its own Telegram message. Each new status resets the quiet window and
    replaces the pending Telegram status with the latest one. Every call also
    arms a detached flusher for the new deadline, so a killed earlier waiter
    cannot strand the batch. Quiet seconds come from config `coalesce_seconds`
    unless `window` is passed explicitly.
    """
    clock = clock or time.time
    directory = state_dir or Path(__file__).resolve().parent
    config = load_config(config_file)
    quiet = config.coalesce_seconds if window is None else window
    from local_prompt import write_prompt

    write_prompt(
        directory / "local_prompt.txt",
        status,
        config.message_for(status, ide=ide, project=project),
        clock(),
    )
    result = submit_status(
        directory,
        status,
        ide=ide,
        project=project,
        now=clock(),
        window=quiet,
    )
    if result.immediate is not None:
        notify(
            config_file,
            result.immediate,
            ide=result.immediate_ide,
            project=result.immediate_project,
            state_dir=directory,
        )
    if sleep is not None:
        if result.role == "leader":
            flush_scheduled(
                config_file,
                directory,
                result.token,
                result.deadline,
                clock=clock,
                sleep=sleep,
            )
        return
    try:
        _spawn_flusher(config_file, directory, result.token, result.deadline)
    except OSError:
        if result.role == "leader":
            flush_scheduled(
                config_file,
                directory,
                result.token,
                result.deadline,
                clock=clock,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="依設定檔 coalesce_seconds 收束後送出最後一則 AI 狀態；也可用 message 立刻送自由文字"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().with_name("config.json")),
        help="JSON 設定檔路徑",
    )
    parser.add_argument("--flush", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--delete-flush", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--state-dir",
        default=str(Path(__file__).resolve().parent),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ide",
        choices=("CLI", "Codex", "Cursor"),
        default="CLI",
        help="通知來源；Hook 會自動傳入 Codex 或 Cursor",
    )
    parser.add_argument(
        "--project",
        default=Path.cwd().name or UNKNOWN_PROJECT,
        help="專案名稱；Hook 會自動傳入工作目錄名稱",
    )
    parser.add_argument("--token", default="", help=argparse.SUPPRESS)
    parser.add_argument("--deadline", type=float, default=0.0, help=argparse.SUPPRESS)
    parser.add_argument(
        "status",
        nargs="?",
        help="正式用 AI_wait、AI_fail、AI_done；測試用 AI_testWait、AI_testDone；或 message",
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        help="搭配 message 使用的自由文字",
    )
    args = parser.parse_args()
    if args.flush and args.delete_flush:
        parser.error("不可同時使用 --flush 與 --delete-flush")
    if args.flush:
        if not args.token:
            parser.error("缺少視窗識別")
        flush_scheduled(
            args.config,
            Path(args.state_dir),
            args.token,
            args.deadline,
        )
        return
    if args.delete_flush:
        if not args.token:
            parser.error("缺少清除識別")
        flush_delete_scheduled(
            args.config,
            Path(args.state_dir),
            args.token,
            args.deadline,
        )
        return
    if args.status == "message":
        if args.text is None:
            parser.error("message 需要一段文字")
        deliver_free_message(args.config, args.text, state_dir=Path(args.state_dir))
        return
    if args.status is None:
        parser.error("需要狀態短名或 message")
    if args.status not in STATUSES:
        parser.error(f"無法辨認的狀態：{args.status}")
    if args.text is not None:
        parser.error("狀態短名後面不要再跟文字；自由訊息請用 message")
    deliver(args.config, args.status, ide=args.ide, project=args.project)


if __name__ == "__main__":
    main()
