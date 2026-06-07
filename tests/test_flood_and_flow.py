"""Flood-safe Telegram va ombor biznes oqimi testlari."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# DB va sozlamalar importdan oldin
_TEST_DIR = tempfile.mkdtemp(prefix="ombor_test_")
os.environ["DB_PATH"] = os.path.join(_TEST_DIR, "orders.db")
os.environ["TICK_SEC"] = "10"
os.environ["LIVE_EDIT_SEC"] = "15"
os.environ.pop("BOT_TOKEN", None)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
import live_ticker  # noqa: E402
import storage  # noqa: E402
import telegram_safe  # noqa: E402
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter  # noqa: E402
from keyboards import group_actions  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class TestTelegramSafe(unittest.TestCase):
    def setUp(self) -> None:
        telegram_safe.reset_flood_state()

    def test_success_returns_value(self) -> None:
        async def ok() -> str:
            return "ok"

        self.assertEqual(_run(telegram_safe.run_telegram(ok)), "ok")

    def test_not_modified_returns_none(self) -> None:
        async def bad() -> None:
            raise TelegramBadRequest(method="editMessageText", message="message is not modified")

        self.assertIsNone(_run(telegram_safe.run_telegram(bad)))

    def test_retry_after_sleeps_and_retries(self) -> None:
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TelegramRetryAfter(method="editMessageText", message="Flood", retry_after=0.05)
            return "done"

        with patch("telegram_safe.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
            result = _run(telegram_safe.run_telegram(flaky, label="test"))
        self.assertEqual(result, "done")
        self.assertEqual(calls["n"], 2)
        sleep_mock.assert_awaited_once()

    def test_double_retry_after_returns_none(self) -> None:
        async def always_flood() -> str:
            raise TelegramRetryAfter(method="editMessageText", message="Flood", retry_after=0.01)

        with patch("telegram_safe.asyncio.sleep", new_callable=AsyncMock):
            self.assertIsNone(_run(telegram_safe.run_telegram(always_flood)))

    def test_flood_pause_blocks_background_calls(self) -> None:
        telegram_safe.pause_for_flood(60.0)
        called = {"v": False}

        async def action() -> bool:
            called["v"] = True
            return True

        self.assertIsNone(_run(telegram_safe.run_telegram(action)))
        self.assertFalse(called["v"])

    def test_force_waits_through_flood_pause(self) -> None:
        telegram_safe.pause_for_flood(0.08)
        called = {"v": False}

        async def action() -> str:
            called["v"] = True
            return "forced"

        t0 = time.monotonic()
        result = _run(telegram_safe.run_telegram(action, force=True))
        elapsed = time.monotonic() - t0
        self.assertEqual(result, "forced")
        self.assertTrue(called["v"])
        self.assertGreaterEqual(elapsed, 0.05)


class TestLiveTickerThrottle(unittest.TestCase):
    def setUp(self) -> None:
        telegram_safe.reset_flood_state()
        live_ticker.reset_edit_throttle()
        config.settings.cache_clear()
        storage.init_db()
        conn = storage._conn()
        conn.execute("DELETE FROM order_staff")
        conn.execute("DELETE FROM orders")
        conn.commit()
        conn.close()

    def _make_order(self, *, status: str = "yangi", msg_id: int = 100) -> dict:
        oid = storage.create_order(
            user_id=111,
            username="u",
            full_name="Test User",
            request_type="call_staff",
            kind_label="Xizmat",
            text="Test",
        )
        storage.set_group_message(oid, msg_id)
        if status == "jarayonda":
            storage.assign_to_staff(oid, 222, "Worker")
        order = storage.get_order(oid)
        assert order is not None
        return order

    def test_throttle_limits_edits_per_order(self) -> None:
        order = self._make_order(msg_id=501)
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)
        group_id = -1001

        async def burst() -> int:
            n = 0
            for _ in range(30):
                if await live_ticker.refresh_order_message(bot, group_id, order):
                    n += 1
            return n

        edits = _run(burst())
        self.assertEqual(edits, 1)
        self.assertEqual(bot.edit_message_text.await_count, 1)

    def test_force_bypasses_throttle(self) -> None:
        order = self._make_order(msg_id=502)
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)
        group_id = -1001

        async def twice() -> int:
            n = 0
            if await live_ticker.refresh_order_message(bot, group_id, order, force=True):
                n += 1
            if await live_ticker.refresh_order_message(bot, group_id, order, force=True):
                n += 1
            return n

        self.assertEqual(_run(twice()), 2)
        self.assertEqual(bot.edit_message_text.await_count, 2)

    def test_many_orders_low_edit_count_under_pressure(self) -> None:
        orders = [self._make_order(msg_id=600 + i) for i in range(12)]
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)
        group_id = -1001

        async def simulate_ticks() -> tuple[int, int]:
            total_edits = 0
            for _ in range(20):
                total_edits += await live_ticker.refresh_all_live(bot, group_id)
            return total_edits, bot.edit_message_text.await_count

        edits, api_calls = _run(simulate_ticks())
        self.assertEqual(edits, 12)
        self.assertEqual(api_calls, 12)

    def test_flood_pause_skips_ticker_but_force_works(self) -> None:
        order = self._make_order(msg_id=700)
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)
        telegram_safe.pause_for_flood(30.0)
        group_id = -1001

        async def run() -> tuple[bool, bool]:
            skipped = await live_ticker.refresh_order_message(bot, group_id, order)
            forced = await live_ticker.refresh_order_message(
                bot, group_id, order, force=True
            )
            return skipped, forced

        skipped, forced = _run(run())
        self.assertFalse(skipped)
        self.assertTrue(forced)
        self.assertEqual(bot.edit_message_text.await_count, 1)

    def test_completed_order_stops_refresh(self) -> None:
        order = self._make_order(status="jarayonda", msg_id=800)
        storage.complete_order(order["id"], 222)
        finished = storage.get_order(order["id"])
        assert finished is not None
        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)

        ok = _run(
            live_ticker.refresh_order_message(bot, -1001, finished, force=True)
        )
        self.assertFalse(ok)
        bot.edit_message_text.assert_not_awaited()


class TestStorageFlow(unittest.TestCase):
    def setUp(self) -> None:
        storage.init_db()
        conn = storage._conn()
        conn.execute("DELETE FROM order_staff")
        conn.execute("DELETE FROM orders")
        conn.commit()
        conn.close()

    def test_assign_join_complete_happy_path(self) -> None:
        oid = storage.create_order(
            user_id=1,
            username="c",
            full_name="Client",
            request_type="product_order",
            kind_label="Buyurtma",
            text="2 ta quti",
        )
        lead, err = storage.assign_to_staff(oid, 10, "Ali")
        self.assertIsNone(err)
        assert lead is not None
        self.assertEqual(lead["status"], "jarayonda")

        helper, err2 = storage.join_staff(oid, 11, "Vali")
        self.assertIsNone(err2)
        assert helper is not None
        self.assertIn(11, helper["staff_ids"])

        done, err3 = storage.complete_order(oid, 10)
        self.assertIsNone(err3)
        assert done is not None
        self.assertEqual(done["status"], "bajarildi")
        self.assertGreater(done.get("service_seconds", 0), 0)

    def test_complete_rejects_non_team_member(self) -> None:
        oid = storage.create_order(
            user_id=1,
            username=None,
            full_name="C",
            request_type="call_staff",
            kind_label="Xizmat",
            text="Yordam",
        )
        storage.assign_to_staff(oid, 10, "Ali")
        done, err = storage.complete_order(oid, 99)
        self.assertIsNone(done)
        self.assertIn("Qo'shilaman", err or "")

    def test_second_assign_joins_when_already_in_service(self) -> None:
        oid = storage.create_order(
            user_id=1,
            username=None,
            full_name="C",
            request_type="call_staff",
            kind_label="Xizmat",
            text="Yordam",
        )
        first, err1 = storage.assign_to_staff(oid, 10, "Ali")
        second, err2 = storage.assign_to_staff(oid, 11, "Vali")
        assert first is not None
        self.assertIsNone(err1)
        self.assertIsNone(err2)
        assert second is not None
        self.assertEqual(second["status"], "jarayonda")
        self.assertIn(11, second["staff_ids"])

    def test_reject_only_new(self) -> None:
        oid = storage.create_order(
            user_id=1,
            username=None,
            full_name="C",
            request_type="info",
            kind_label="Savol",
            text="Savol",
        )
        self.assertIsNotNone(storage.reject_order(oid))
        self.assertIsNone(storage.reject_order(oid))


class TestKeyboards(unittest.TestCase):
    def test_jarayonda_viewer_on_team_sees_finish_only(self) -> None:
        order = {
            "status": "jarayonda",
            "staff_ids": {10, 11},
        }
        kb = group_actions(1, order, viewer_id=10)
        texts = [b.text for row in kb.inline_keyboard for b in row]
        self.assertEqual(len(texts), 1)
        self.assertIn("tugadi", kb.inline_keyboard[0][0].callback_data)

    def test_jarayonda_outsider_sees_join_only(self) -> None:
        order = {"status": "jarayonda", "staff_ids": {10}}
        kb = group_actions(1, order, viewer_id=99)
        texts = [b.text for row in kb.inline_keyboard for b in row]
        self.assertEqual(len(texts), 1)
        self.assertIn("qoshil", kb.inline_keyboard[0][0].callback_data)


class TestConfigBounds(unittest.TestCase):
    def test_tick_and_live_edit_clamped(self) -> None:
        os.environ["TICK_SEC"] = "3"
        os.environ["LIVE_EDIT_SEC"] = "5"
        config.settings.cache_clear()
        s = config.settings()
        self.assertEqual(s["tick_sec"], 10)
        self.assertEqual(s["live_edit_sec"], 15)
        os.environ["TICK_SEC"] = "10"
        os.environ["LIVE_EDIT_SEC"] = "15"
        config.settings.cache_clear()


class TestLoadSimulation(unittest.TestCase):
    """Yuqori bosim — API chaqiruvlari cheklanganligi."""

    def setUp(self) -> None:
        telegram_safe.reset_flood_state()
        live_ticker.reset_edit_throttle()
        storage.init_db()
        conn = storage._conn()
        conn.execute("DELETE FROM order_staff")
        conn.execute("DELETE FROM orders")
        conn.commit()
        conn.close()

    def test_mixed_user_actions_and_ticker(self) -> None:
        orders = []
        for i in range(8):
            oid = storage.create_order(
                user_id=100 + i,
                username="u",
                full_name=f"U{i}",
                request_type="call_staff",
                kind_label="Xizmat",
                text=f"Req {i}",
            )
            storage.set_group_message(oid, 1000 + i)
            orders.append(storage.get_order(oid))

        bot = MagicMock()
        bot.edit_message_text = AsyncMock(return_value=True)
        gid = -1001877019294
        api_calls = 0

        async def mixed_pressure() -> int:
            nonlocal api_calls
            count = 0
            for cycle in range(15):
                for j, order in enumerate(orders[:3]):
                    if cycle % 4 == j:
                        storage.assign_to_staff(order["id"], 500 + j, f"W{j}")
                        order = storage.get_order(order["id"])
                        assert order
                        if await live_ticker.refresh_order_message(
                            bot, gid, order, viewer_id=500 + j, force=True
                        ):
                            count += 1
                count += await live_ticker.refresh_all_live(bot, gid)
            api_calls = bot.edit_message_text.await_count
            return count

        total = _run(mixed_pressure())
        self.assertLessEqual(api_calls, total + 5)
        self.assertLess(api_calls, 15 * 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
