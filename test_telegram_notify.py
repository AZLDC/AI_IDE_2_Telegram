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

    def test_reserved_strings_render_platform_and_ide(self) -> None:
        data = dict(SAMPLE_CONFIG)
        data["AI_done"] = "{platform}上的{IDE} A.I.的工作已完成."
        config = telegram_notify.load_config(self.write_config(data))

        self.assertEqual(
            config.message_for("AI_done", ide="Codex", platform_name="Windows"),
            "Windows上的Codex A.I.的工作已完成.",
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
    @patch("telegram_notify.submit_status")
    def test_free_message_sends_immediately_without_coalesce(
        self, submit_mock, send_message_mock
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

        submit_mock.assert_not_called()
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


class NotifyBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.state_dir = Path(temporary_directory.name)

    def play(self, calls: list[tuple[float, str]]) -> list[tuple[float, str]]:
        pending = None
        sends: list[tuple[float, str]] = []
        for now, status in calls:
            if pending is not None and now >= pending.deadline:
                ready = telegram_notify.take_ready(
                    self.state_dir,
                    pending.token,
                    now=pending.deadline,
                )
                if ready is not None:
                    sends.append((pending.deadline, ready))
                pending = None
            result = telegram_notify.submit_status(
                self.state_dir,
                status,
                now=now,
            )
            if result.immediate is not None:
                sends.append((now, result.immediate))
            pending = result
        if pending is not None:
            ready = telegram_notify.take_ready(
                self.state_dir,
                pending.token,
                now=pending.deadline,
            )
            if ready is not None:
                sends.append((pending.deadline, ready))
        return sends

    def test_each_call_resets_the_window_and_keeps_the_last_status(self) -> None:
        sends = self.play(
            [
                (0, "AI_done"),
                (2, "AI_wait"),
                (4, "AI_done"),
                (6, "AI_done"),
                (8, "AI_wait"),
            ]
        )

        self.assertEqual(sends, [(18, "AI_wait")])

    def test_later_call_extends_the_window(self) -> None:
        sends = self.play([(0, "AI_done"), (2.9, "AI_done")])

        self.assertEqual(sends, [(12.9, "AI_done")])

    def test_test_statuses_do_not_join_the_real_window(self) -> None:
        real = telegram_notify.submit_status(self.state_dir, "AI_done", now=0)
        trial = telegram_notify.submit_status(self.state_dir, "AI_testWait", now=1)

        self.assertEqual(trial.role, "leader")
        self.assertNotEqual(trial.token, real.token)
        self.assertEqual(
            telegram_notify.take_ready(self.state_dir, real.token, now=10),
            "AI_done",
        )
        self.assertEqual(
            telegram_notify.take_ready(self.state_dir, trial.token, now=11),
            "AI_testWait",
        )

    def test_last_status_wins_inside_the_test_window(self) -> None:
        sends = self.play([(0, "AI_testDone"), (1, "AI_testWait"), (2, "AI_testDone")])

        self.assertEqual(sends, [(12, "AI_testDone")])

    def test_latest_ide_is_kept_with_coalesced_status(self) -> None:
        first = telegram_notify.submit_status(
            self.state_dir, "AI_wait", ide="Cursor", now=0
        )
        telegram_notify.submit_status(
            self.state_dir, "AI_done", ide="Codex", now=1
        )

        ready = telegram_notify.take_ready_notification(
            self.state_dir, first.token, now=11
        )

        self.assertEqual(
            ready,
            telegram_notify.PendingStatus("AI_done", "Codex"),
        )

    def test_last_status_wins_when_both_statuses_share_a_window(self) -> None:
        sends = self.play([(0, "AI_done"), (1, "AI_wait"), (2, "AI_done")])

        self.assertEqual(sends, [(12, "AI_done")])

    def test_only_one_leader_when_calls_arrive_together(self) -> None:
        barrier = threading.Barrier(5)
        results = []

        def worker(status: str) -> None:
            barrier.wait()
            results.append(
                telegram_notify.submit_status(self.state_dir, status, now=0)
            )

        threads = [
            threading.Thread(target=worker, args=(status,))
            for status in ("AI_done", "AI_done", "AI_wait", "AI_done", "AI_wait")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        leaders = [result for result in results if result.role == "leader"]
        self.assertEqual(len(leaders), 1)
        status = telegram_notify.take_ready(
            self.state_dir,
            leaders[0].token,
            now=10,
        )
        self.assertIn(status, telegram_notify.REAL_STATUSES)

    def test_expired_batch_is_sent_once_then_a_new_window_starts(self) -> None:
        first = telegram_notify.submit_status(self.state_dir, "AI_wait", now=0)
        second = telegram_notify.submit_status(self.state_dir, "AI_done", now=11)

        self.assertEqual(second.immediate, "AI_wait")
        self.assertEqual(second.role, "leader")
        self.assertIsNone(
            telegram_notify.take_ready(self.state_dir, first.token, now=11)
        )
        self.assertEqual(
            telegram_notify.take_ready(self.state_dir, second.token, now=21),
            "AI_done",
        )

    @patch("telegram_notify.notify")
    def test_leader_waits_for_the_window_before_sending(self, notify_mock) -> None:
        clock = {"now": 0.0}
        config_file = self.write_config()

        def now() -> float:
            return clock["now"]

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        telegram_notify.deliver(
            config_file,
            "AI_done",
            state_dir=self.state_dir,
            clock=now,
            sleep=sleep,
        )

        self.assertEqual(clock["now"], 10)
        notify_mock.assert_called_once_with(
            config_file, "AI_done", ide="CLI", state_dir=self.state_dir
        )

    @patch("telegram_notify.notify")
    def test_follower_returns_without_sending(self, notify_mock) -> None:
        config_file = self.write_config()
        first = telegram_notify.submit_status(self.state_dir, "AI_done", now=0)

        telegram_notify.deliver(
            config_file,
            "AI_wait",
            state_dir=self.state_dir,
            clock=lambda: 1,
            sleep=lambda seconds: self.fail("follower must not wait"),
        )

        notify_mock.assert_not_called()
        self.assertEqual(
            telegram_notify.take_ready(
                self.state_dir,
                first.token,
                now=11,
            ),
            "AI_wait",
        )

    @patch("telegram_notify.notify")
    def test_desktop_prompt_updates_before_telegram_waits(self, notify_mock) -> None:
        import local_prompt

        config_file = self.write_config()
        prompt_file = self.state_dir / "local_prompt.txt"
        clock = {"now": 1000.0}
        nested = {"done": False}

        def sleep(seconds: float) -> None:
            seen = local_prompt.read_prompt(prompt_file)
            self.assertIsNotNone(seen)
            assert seen is not None
            if not nested["done"]:
                self.assertEqual(seen[1:], ("AI_done", "已完成"))
                self.nested_wait(config_file, prompt_file)
                nested["done"] = True
            else:
                self.assertEqual(seen[1:], ("AI_wait", "處理中"))
            clock["now"] += seconds

        telegram_notify.deliver(
            config_file,
            "AI_done",
            state_dir=self.state_dir,
            clock=lambda: clock["now"],
            sleep=sleep,
        )

        notify_mock.assert_called_once_with(
            config_file, "AI_wait", ide="CLI", state_dir=self.state_dir
        )
        self.assertEqual(clock["now"], 1011.0)

    @patch("telegram_notify.notify")
    def test_hook_returns_before_send_so_the_next_status_joins_the_window(
        self, notify_mock
    ) -> None:
        import local_prompt

        config_file = self.write_config()
        prompt_file = self.state_dir / "local_prompt.txt"
        spawned = []

        def boom(_seconds: float) -> None:
            raise AssertionError("掛鉤行程不能自己睡到視窗結束")

        def record(*args: object) -> None:
            spawned.append(args)

        with patch("telegram_notify.time.sleep", side_effect=boom):
            with patch("telegram_notify._spawn_flusher", side_effect=record):
                telegram_notify.deliver(
                    config_file,
                    "AI_done",
                    state_dir=self.state_dir,
                    clock=lambda: 0.0,
                )
                telegram_notify.deliver(
                    config_file,
                    "AI_wait",
                    state_dir=self.state_dir,
                    clock=lambda: 1.0,
                )

        self.assertEqual(len(spawned), 2)
        notify_mock.assert_not_called()
        seen = local_prompt.read_prompt(prompt_file)
        self.assertEqual(seen[1:], ("AI_wait", "處理中"))
        _config_file, _state_dir, token, deadline = spawned[0]
        self.assertEqual(deadline, 10.0)
        self.assertEqual(spawned[1][3], 11.0)
        clock = {"now": 0.0}

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        telegram_notify.flush_scheduled(
            config_file,
            self.state_dir,
            token,
            deadline,
            clock=lambda: clock["now"],
            sleep=sleep,
        )
        self.assertEqual(clock["now"], 11.0)
        notify_mock.assert_called_once_with(
            config_file, "AI_wait", ide="CLI", state_dir=self.state_dir
        )

    def test_window_seconds_default_constant_is_ten(self) -> None:
        self.assertEqual(telegram_notify.WINDOW_SECONDS, 10.0)

    @patch("telegram_notify.notify")
    def test_deliver_uses_coalesce_seconds_from_config(self, notify_mock) -> None:
        clock = {"now": 0.0}
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

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        telegram_notify.deliver(
            config_file,
            "AI_done",
            state_dir=self.state_dir,
            clock=lambda: clock["now"],
            sleep=sleep,
        )

        self.assertEqual(clock["now"], 2)
        notify_mock.assert_called_once_with(
            config_file, "AI_done", ide="CLI", state_dir=self.state_dir
        )

    def test_detached_flusher_is_not_waited_on(self) -> None:
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

    def nested_wait(self, config_file: str, prompt_file: Path) -> None:
        import local_prompt

        telegram_notify.deliver(
            config_file,
            "AI_wait",
            state_dir=self.state_dir,
            clock=lambda: 1001.0,
            sleep=lambda waited: self.fail("follower must not wait"),
        )
        seen = local_prompt.read_prompt(prompt_file)
        self.assertEqual(seen[1:], ("AI_wait", "處理中"))

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
