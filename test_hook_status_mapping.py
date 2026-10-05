"""Smoke-check hook status mapping without spawning Telegram."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


def load_hook():
    path = Path(__file__).resolve().parent / "cursor_hooks" / "ai_status_notify.py"
    spec = importlib.util.spec_from_file_location("ai_status_notify", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HookStatusMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hook = load_hook()

    def test_write_tool_sends_wait(self) -> None:
        self.assertEqual(
            self.hook.status_for("preToolUse", {"tool_name": "Write"}),
            "AI_wait",
        )

    def test_shell_sends_wait(self) -> None:
        self.assertEqual(
            self.hook.status_for("beforeShellExecution", {"command": "echo hi"}),
            "AI_wait",
        )

    def test_tool_failure_sends_fail(self) -> None:
        self.assertEqual(
            self.hook.status_for("postToolUseFailure", {"tool_name": "Shell"}),
            "AI_fail",
        )

    def test_stop_sends_done_without_marker(self) -> None:
        marker = self.hook.MARKER
        marker.unlink(missing_ok=True)
        self.assertEqual(self.hook.status_for("stop", {"status": "completed"}), "AI_done")

    @patch("subprocess.Popen")
    def test_spawn_identifies_cursor(self, popen_mock) -> None:
        self.hook.spawn("AI_wait")

        command = popen_mock.call_args.args[0]
        self.assertEqual(command[command.index("--ide") + 1], "Cursor")


if __name__ == "__main__":
    unittest.main()
