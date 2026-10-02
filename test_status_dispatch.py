import tempfile
import time
import unittest
from pathlib import Path

import local_prompt


class LocalPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.config_file = self.directory / "config.json"
        self.prompt_file = self.directory / "local_prompt.txt"
        self.config_file.write_text(
            """{
  "token": "bot-token",
  "chat_id": "123456",
  "AI_wait": "處理中",
  "AI_done": "已完成",
  "AI_testWait": "測試等待",
  "AI_testDone": "測試完成",
  "coalesce_seconds": 10
}
""",
            encoding="utf-8",
        )

    def test_each_push_replaces_the_prompt_without_waiting(self) -> None:
        started = time.monotonic()
        local_prompt.push_status(self.config_file, self.prompt_file, "AI_wait", when=1_700_000_000.125)
        first = local_prompt.read_prompt(self.prompt_file)
        local_prompt.push_status(self.config_file, self.prompt_file, "AI_done", when=1_700_000_000.325)
        second = local_prompt.read_prompt(self.prompt_file)

        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(first[0], local_prompt.format_stamp(1_700_000_000.125))
        self.assertEqual(first[1:], ("AI_wait", "處理中"))
        self.assertEqual(second[0], local_prompt.format_stamp(1_700_000_000.325))
        self.assertEqual(second[1:], ("AI_done", "已完成"))
        self.assertNotIn("處理中", second[2])


if __name__ == "__main__":
    unittest.main()
