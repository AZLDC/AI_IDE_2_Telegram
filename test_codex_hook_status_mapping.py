import importlib.util
import json
import sqlite3
import tempfile
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
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                self.hook.project_from_payload(
                    {"cwd": r"D:\interest\AI狀態通知工具"},
                    codex_home=Path(directory) / "missing-codex-home",
                ),
                "AI狀態通知工具",
            )

    def test_project_name_uses_codex_custom_name_for_workspace_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            codex_home = base / ".codex"
            codex_home.mkdir()
            workspace = base / "CatStrick_STG"
            workspace.mkdir()
            transcript = base / "rollout.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {"workspace_roots": [str(workspace)]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            database = sqlite3.connect(codex_home / "state_5.sqlite")
            with database:
                database.execute("create table projects (id text, name text)")
                database.execute(
                    "create table project_roots (project_id text, position integer, path text)"
                )
                database.execute(
                    "insert into projects values (?, ?)", ("project-1", "Cat Strick")
                )
                database.execute(
                    "insert into project_roots values (?, ?, ?)",
                    ("project-1", 0, str(workspace)),
                )
            database.close()

            self.assertEqual(
                self.hook.project_from_payload(
                    {
                        "cwd": str(codex_home / "memories"),
                        "transcript_path": str(transcript),
                    },
                    codex_home=codex_home,
                ),
                "Cat Strick",
            )

    def test_workspace_folder_name_is_used_when_codex_catalog_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "PortableProject"
            workspace.mkdir()
            transcript = base / "rollout.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {"workspace_roots": [str(workspace)]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                self.hook.project_from_payload(
                    {"transcript_path": str(transcript)},
                    codex_home=base / "missing-codex-home",
                ),
                "PortableProject",
            )

    def test_codex_internal_directory_is_not_a_project(self):
        with tempfile.TemporaryDirectory() as directory:
            codex_home = Path(directory) / ".codex"
            memories = codex_home / "memories"
            memories.mkdir(parents=True)

            self.assertEqual(
                self.hook.project_from_payload(
                    {"cwd": str(memories)}, codex_home=codex_home
                ),
                "未知專案",
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
