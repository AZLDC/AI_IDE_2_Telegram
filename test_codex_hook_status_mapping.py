import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


def load_hook_module():
    path = Path(__file__).resolve().parent / "codex_hooks" / "ai_status_notify.py"
    spec = importlib.util.spec_from_file_location("codex_ai_status_notify", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CodexHookStatusMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = load_hook_module()

    def test_wait_events(self):
        for event in (
            "UserPromptSubmit",
            "PreToolUse",
            "PermissionRequest",
            "SubagentStart",
            "SubagentStop",
        ):
            with self.subTest(event=event):
                self.assertEqual(self.hook.status_for(event, {}), "AI_wait")

    def test_stop_is_done(self):
        self.assertEqual(self.hook.status_for("Stop", {}), "AI_done")

    def test_interrupt_is_fail(self):
        self.assertEqual(self.hook.status_for("Interrupt", {}), "AI_fail")

    def test_session_end_is_not_mapped(self):
        self.assertIsNone(self.hook.status_for("SessionEnd", {}))

    @patch("subprocess.Popen")
    def test_spawn_identifies_codex(self, popen_mock):
        self.hook.spawn("AI_wait", "AI狀態通知工具")

        command = popen_mock.call_args.args[0]
        self.assertEqual(command[command.index("--ide") + 1], "Codex")
        self.assertEqual(command[command.index("--project") + 1], "AI狀態通知工具")

    def test_project_name_comes_from_codex_cwd(self):
        self.assertEqual(
            self.hook.project_from_payload({"cwd": r"D:\interest\AI狀態通知工具"}),
            "AI狀態通知工具",
        )

    def test_post_tool_use_reports_only_failures(self):
        failures = (
            {"exit_code": 1},
            {"isError": True},
            {"success": False},
            {"status": "failed"},
            "Process exited with code 2",
        )
        for response in failures:
            with self.subTest(response=response):
                payload = {"tool_response": response}
                self.assertEqual(self.hook.status_for("PostToolUse", payload), "AI_fail")
        for response in ({"exit_code": 0}, {"success": True}, "Process exited with code 0"):
            with self.subTest(response=response):
                payload = {"tool_response": response}
                self.assertIsNone(self.hook.status_for("PostToolUse", payload))


if __name__ == "__main__":
    unittest.main()
