import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import telegram_notify

SAMPLE_CONFIG = {
    "token": "bot-token",
    "chat_id": "123456",
    "coalesce_seconds": 10,
    "AI_wait": "處理中",
    "AI_fail": "失敗了",
    "AI_done": "已完成",
    "AI_testWait": "A.I. 測試發送等待訊息.",
    "AI_testDone": "A.I. 測試發送完成訊息.",
}


class TelegramNotifyTests(unittest.TestCase):
    def write_config(self, data: object) -> str:
        temporary_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        with temporary_file:
            json.dump(data, temporary_file, ensure_ascii=False)
        self.addCleanup(Path(temporary_file.name).unlink, missing_ok=True)
        return temporary_file.name

    def test_load_config_and_select_message(self) -> None:
        config_file = self.write_config(SAMPLE_CONFIG)

        config = telegram_notify.load_config(config_file)

        self.assertEqual(config.message_for("AI_wait"), "處理中")
        self.assertEqual(config.message_for("AI_fail"), "失敗了")
        self.assertEqual(config.message_for("AI_done"), "已完成")
        self.assertEqual(config.message_for("AI_testWait"), "A.I. 測試發送等待訊息.")
        self.assertEqual(config.message_for("AI_testDone"), "A.I. 測試發送完成訊息.")
        self.assertEqual(config.coalesce_seconds, 10.0)
        self.assertEqual(config.auto_delete_seconds, 0.0)

    def test_reserved_strings_render_platform_ide_and_project(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["AI_done"] = "{platform}上{project}的{IDE} A.I.的工作已完成."
        config = telegram_notify.load_config(self.write_config(data))

        self.assertEqual(
            config.message_for(
                "AI_done",
                ide="Codex",
                project="AI狀態通知工具",
                platform_name="Windows",
            ),
            "Windows上AI狀態通知工具的Codex A.I.的工作已完成.",
        )

    def test_unknown_reserved_string_is_preserved(self) -> None:
        self.assertEqual(
            telegram_notify.render_message("{unknown}-{IDE}", "Cursor", "Mac"),
            "{unknown}-Cursor",
        )

    def test_missing_fail_field_uses_default(self) -> None:
        data = dict(SAMPLE_CONFIG)
        del data["AI_fail"]
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.AI_fail, telegram_notify.DEFAULT_MESSAGES["AI_fail"])

    def test_missing_required_field_is_rejected(self) -> None:
        config_file = self.write_config(
            {"token": "bot-token", "AI_wait": "處理中"}
        )

        with self.assertRaisesRegex(ValueError, "chat_id"):
            telegram_notify.load_config(config_file)

    def test_missing_test_field_uses_default(self) -> None:
        data = dict(SAMPLE_CONFIG)
        del data["AI_testDone"]
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(
            config.AI_testDone, telegram_notify.DEFAULT_MESSAGES["AI_testDone"]
        )

    def test_missing_coalesce_seconds_uses_default(self) -> None:
        data = dict(SAMPLE_CONFIG)
        del data["coalesce_seconds"]
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.coalesce_seconds, telegram_notify.WINDOW_SECONDS)

    def test_blank_coalesce_seconds_uses_default(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["coalesce_seconds"] = ""
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.coalesce_seconds, telegram_notify.WINDOW_SECONDS)

    def test_invalid_coalesce_seconds_uses_default(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["coalesce_seconds"] = 0
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.coalesce_seconds, telegram_notify.WINDOW_SECONDS)

    def test_auto_delete_seconds_positive_is_loaded(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["auto_delete_seconds"] = 10
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.auto_delete_seconds, 10.0)

    def test_missing_auto_delete_seconds_disables(self) -> None:
        config = telegram_notify.load_config(self.write_config(SAMPLE_CONFIG))
        self.assertEqual(config.auto_delete_seconds, 0.0)

    def test_zero_auto_delete_seconds_disables(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["auto_delete_seconds"] = 0
        config = telegram_notify.load_config(self.write_config(data))
        self.assertEqual(config.auto_delete_seconds, 0.0)

    @patch("telegram_notify.send_message")
    def test_notify_sends_selected_message(self, send_message_mock) -> None:
        send_message_mock.return_value = 101
        config_file = self.write_config(SAMPLE_CONFIG)

        telegram_notify.notify(config_file, "AI_testWait")

        send_message_mock.assert_called_once_with(
            "bot-token",
            "123456",
            "A.I. 測試發送等待訊息.",
        )

    def _full_config(self, **overrides: object) -> str:
        data = dict(SAMPLE_CONFIG)
        data.update(overrides)
        return self.write_config(data)

    @patch("telegram_notify.send_message")
    def test_free_message_sends_immediately_without_coalesce(
        self, send_message_mock
    ) -> None:
        import local_prompt

        send_message_mock.return_value = 202
        config_file = self._full_config()
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        state_dir = Path(temporary_directory.name)

        telegram_notify.deliver_free_message(
            config_file,
            "  你好  ",
            state_dir=state_dir,
            clock=lambda: 1_700_000_000.0,
        )

        send_message_mock.assert_called_once_with("bot-token", "123456", "你好")
        self.assertEqual(
            local_prompt.read_prompt(state_dir / "local_prompt.txt")[1:],
            ("message", "你好"),
        )

    def test_blank_free_message_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "空白"):
            telegram_notify.deliver_free_message(self._full_config(), "   ")

    @patch("telegram_notify.delete_message")
    @patch("telegram_notify.send_message")
    def test_auto_delete_clears_all_ids_after_quiet_window(
        self, send_message_mock, delete_message_mock
    ) -> None:
        send_message_mock.side_effect = [11, 22]
        config_file = self._full_config(auto_delete_seconds=10)
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        state_dir = Path(temporary_directory.name)
        clock = {"now": 0.0}

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        with patch("telegram_notify._spawn_deleter") as spawn_mock:
            telegram_notify.deliver_free_message(
                config_file,
                "第一則",
                state_dir=state_dir,
                clock=lambda: clock["now"],
            )
            first_token = spawn_mock.call_args.args[2]
            first_deadline = spawn_mock.call_args.args[3]
            clock["now"] = 3.0
            telegram_notify.deliver_free_message(
                config_file,
                "第二則",
                state_dir=state_dir,
                clock=lambda: clock["now"],
            )
            second_token = spawn_mock.call_args.args[2]
            second_deadline = spawn_mock.call_args.args[3]

        self.assertNotEqual(first_token, second_token)
        self.assertEqual(first_deadline, 10.0)
        self.assertEqual(second_deadline, 13.0)

        telegram_notify.flush_delete_scheduled(
            config_file,
            state_dir,
            first_token,
            first_deadline,
            clock=lambda: clock["now"],
            sleep=sleep,
        )
        delete_message_mock.assert_not_called()

        telegram_notify.flush_delete_scheduled(
            config_file,
            state_dir,
            second_token,
            second_deadline,
            clock=lambda: clock["now"],
            sleep=sleep,
        )
        self.assertEqual(
            [call.args[2] for call in delete_message_mock.call_args_list],
            [11, 22],
        )
        self.assertEqual(clock["now"], 13.0)

    @patch("telegram_notify.delete_message")
    def test_ids_queued_during_delete_are_kept_for_next_round(
        self, delete_message_mock
    ) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        state_dir = Path(temporary_directory.name)
        telegram_notify.submit_delete(state_dir, 11, now=0.0, window=10.0)
        second = telegram_notify.submit_delete(
            state_dir, 22, now=1.0, window=10.0
        )
        snapshot = telegram_notify.begin_delete(
            state_dir, second.token, now=20.0
        )
        self.assertEqual(snapshot, (11, 22))
        telegram_notify.submit_delete(state_dir, 33, now=21.0, window=10.0)
        follow = telegram_notify.finish_delete(
            state_dir, snapshot, {11, 22}, now=21.0, window=10.0
        )
        self.assertIsNotNone(follow)
        state_path, _lock = telegram_notify._delete_paths(state_dir)
        kept = telegram_notify._read_delete_batch(state_path)
        assert kept is not None
        self.assertEqual(kept.message_ids, (33,))
        self.assertEqual(kept.phase, "waiting")
        delete_message_mock.assert_not_called()

    @patch("telegram_notify.delete_message")
    def test_failed_delete_keeps_message_id(self, delete_message_mock) -> None:
        attempts = {"11": 0}

        def delete_side_effect(_token: str, _chat_id: str, message_id: int) -> None:
            if message_id == 11:
                attempts["11"] += 1
                if attempts["11"] == 1:
                    raise RuntimeError("boom")
            return None

        delete_message_mock.side_effect = delete_side_effect
        config_file = self._full_config(auto_delete_seconds=10)
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        state_dir = Path(temporary_directory.name)
        clock = {"now": 0.0}

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        telegram_notify.submit_delete(state_dir, 11, now=0.0, window=10.0)
        latest = telegram_notify.submit_delete(
            state_dir, 22, now=0.0, window=10.0
        )
        state_path, _lock = telegram_notify._delete_paths(state_dir)

        telegram_notify.flush_delete_scheduled(
            config_file,
            state_dir,
            latest.token,
            latest.deadline,
            clock=lambda: clock["now"],
            sleep=sleep,
        )

        self.assertIsNone(telegram_notify._read_delete_batch(state_path))
        self.assertEqual(
            [call.args[2] for call in delete_message_mock.call_args_list],
            [11, 22, 11],
        )
        self.assertEqual(attempts["11"], 2)

    @patch("telegram_notify._spawn_deleter")
    @patch("telegram_notify.send_message")
    def test_disabled_auto_delete_does_not_schedule(
        self, send_message_mock, spawn_mock
    ) -> None:
        send_message_mock.return_value = 9
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        telegram_notify.deliver_free_message(
            self._full_config(),
            "不刪",
            state_dir=Path(temporary_directory.name),
            clock=lambda: 0.0,
        )
        spawn_mock.assert_not_called()


class NotifyCooldownTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.state_dir = Path(temporary_directory.name)

    def claim(
        self,
        status: str,
        now: float,
        *,
        ide: str = "Codex",
        platform_name: str = "Windows",
        window: float = 10,
    ) -> str | None:
        return telegram_notify.claim_status_send(
            self.state_dir,
            status,
            ide=ide,
            platform_name=platform_name,
            now=now,
            window=window,
        )

    def test_first_status_is_claimed_immediately_and_duplicates_do_not_extend(self) -> None:
        self.assertIsNotNone(self.claim("AI_wait", 0))
        self.assertIsNone(self.claim("AI_wait", 2))
        self.assertIsNone(self.claim("AI_wait", 9))
        self.assertIsNotNone(self.claim("AI_wait", 10))

    def test_each_status_has_an_independent_timer(self) -> None:
        statuses = (
            "AI_wait",
            "AI_done",
            "AI_fail",
            "AI_testWait",
            "AI_testDone",
        )
        for status in statuses:
            self.assertIsNotNone(self.claim(status, 0))
        for status in statuses:
            self.assertIsNone(self.claim(status, 3))

    def test_platform_and_ide_split_cooldowns_but_project_does_not(self) -> None:
        self.assertIsNotNone(self.claim("AI_done", 0))
        self.assertIsNotNone(self.claim("AI_done", 1, platform_name="Darwin"))
        self.assertIsNotNone(self.claim("AI_done", 1, ide="Cursor"))
        self.assertIsNone(self.claim("AI_done", 1))

    def test_only_one_claim_when_identical_calls_arrive_together(self) -> None:
        barrier = threading.Barrier(5)
        results = []

        def worker() -> None:
            barrier.wait()
            results.append(self.claim("AI_done", 0))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(result is not None for result in results), 1)

    @patch("telegram_notify.notify")
    def test_first_status_sends_now_and_duplicate_only_updates_prompt(
        self, notify_mock
    ) -> None:
        import local_prompt

        config_file = self.write_config()
        telegram_notify.deliver(
            config_file,
            "AI_done",
            ide="Codex",
            project="甲專案",
            state_dir=self.state_dir,
            clock=lambda: 0,
        )
        telegram_notify.deliver(
            config_file,
            "AI_done",
            ide="Codex",
            project="乙專案",
            state_dir=self.state_dir,
            clock=lambda: 2,
        )

        notify_mock.assert_called_once_with(
            config_file,
            "AI_done",
            ide="Codex",
            project="甲專案",
            state_dir=self.state_dir,
        )
        seen = local_prompt.read_prompt(self.state_dir / "local_prompt.txt")
        self.assertEqual(seen[1:], ("AI_done", "已完成"))

    @patch("telegram_notify.notify")
    def test_failed_send_releases_claim_for_immediate_retry(self, notify_mock) -> None:
        config_file = self.write_config()
        notify_mock.side_effect = [OSError("network"), None]

        with self.assertRaisesRegex(OSError, "network"):
            telegram_notify.deliver(
                config_file, "AI_done", state_dir=self.state_dir, clock=lambda: 0
            )
        telegram_notify.deliver(
            config_file, "AI_done", state_dir=self.state_dir, clock=lambda: 1
        )

        self.assertEqual(notify_mock.call_count, 2)

    def test_window_seconds_default_constant_is_ten(self) -> None:
        self.assertEqual(telegram_notify.WINDOW_SECONDS, 10.0)

    @patch("telegram_notify.notify")
    def test_deliver_uses_coalesce_seconds_from_config(self, notify_mock) -> None:
        config_file = self.write_config()
        Path(config_file).write_text(
            json.dumps(
                {
                    "token": "bot-token",
                    "chat_id": "123456",
                    "coalesce_seconds": 2,
                    "AI_wait": "處理中",
                    "AI_done": "已完成",
                    "AI_testWait": "測試等待",
                    "AI_testDone": "測試完成",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        telegram_notify.deliver(
            config_file,
            "AI_done",
            state_dir=self.state_dir,
            clock=lambda: 0,
        )
        telegram_notify.deliver(
            config_file, "AI_done", state_dir=self.state_dir, clock=lambda: 1.9
        )
        telegram_notify.deliver(
            config_file, "AI_done", state_dir=self.state_dir, clock=lambda: 2
        )

        self.assertEqual(notify_mock.call_count, 2)

    def test_detached_process_is_not_waited_on(self) -> None:
        target = self.state_dir / "detached.txt"
        started = time.monotonic()
        telegram_notify._detached_popen(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ok', encoding='utf-8')",
                str(target),
            ]
        )
        while not target.exists():
            if time.monotonic() - started > 5:
                self.fail("detached process did not write the marker")
            time.sleep(0.05)
        self.assertEqual(target.read_text(encoding="utf-8"), "ok")
        self.assertLess(time.monotonic() - started, 5)

    def write_config(self) -> str:
        temporary_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        with temporary_file:
            json.dump(
                {
                    "token": "bot-token",
                    "chat_id": "123456",
                    "coalesce_seconds": 10,
                    "AI_wait": "處理中",
                    "AI_done": "已完成",
                    "AI_testWait": "測試等待",
                    "AI_testDone": "測試完成",
                },
                temporary_file,
                ensure_ascii=False,
            )
        self.addCleanup(Path(temporary_file.name).unlink, missing_ok=True)
        return temporary_file.name


if __name__ == "__main__":
    unittest.main()
