# -*- coding: utf-8 -*-
"""고정 배분 리밸런싱 신호 테스트 (네트워크·운영 DB 불필요)

실행: python -m unittest test_fixed_allocation -v
"""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from database import Base, ETFPrice, RebalanceSignal, UserPortfolio
from rebalance_engine import RebalanceEngine
import scheduler

D = date(2026, 11, 20)
PORT = {"AAA": {"name": "A", "target_weight": 50.0},
        "BBB": {"name": "B", "target_weight": 30.0},
        "CCC": {"name": "C", "target_weight": 20.0},
        "CASH": {"name": "현금", "target_weight": 0.0}}
PRICES = {"AAA": 10000, "BBB": 20000, "CCC": 5000, "OLD": 10000}
KEYS = {"ticker", "account_type", "signal_date", "target_weight", "current_weight",
        "weight_diff", "current_price", "total_assets", "target_amount",
        "current_amount", "rebalance_amount", "rebalance_quantity", "action",
        "needs_rebalance"}


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for ticker, price in PRICES.items():
        db.add(ETFPrice(ticker=ticker, price_date=D, close_price=price))
    db.commit()
    return db


def hold(db, account, ticker, qty):
    db.add(UserPortfolio(ticker=ticker, quantity=qty, avg_buy_price=0.0,
                         account_type=account, is_active=True))
    db.commit()


def by_ticker(signals):
    return {s["ticker"]: s for s in signals}


class FixedSignalTest(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        self.engine = RebalanceEngine(self.db)

    def tearDown(self):
        self.db.close()

    def calc(self, account="연금저축", portfolio=PORT):
        return self.engine.calculate_fixed_rebalance_signal(D, account, portfolio)

    def test_within_band_is_hold(self):
        hold(self.db, "연금저축", "AAA", 52)
        hold(self.db, "연금저축", "BBB", 14)
        hold(self.db, "연금저축", "CCC", 40)
        signals = self.calc()
        self.assertTrue(all(s["action"] == "HOLD" for s in signals))
        self.assertTrue(all(s["rebalance_quantity"] == 0 for s in signals))

    def test_transition_from_two_holdings(self):
        hold(self.db, "연금저축", "AAA", 50)
        hold(self.db, "연금저축", "OLD", 50)
        signals = self.calc()
        self.assertEqual([s["ticker"] for s in signals],
                         ["AAA", "BBB", "CCC", "CASH", "OLD"])
        s = by_ticker(signals)
        self.assertEqual(s["OLD"]["target_weight"], 0.0)
        self.assertEqual(s["OLD"]["action"], "SELL")
        self.assertAlmostEqual(s["OLD"]["rebalance_quantity"], 50)
        self.assertEqual(s["AAA"]["action"], "HOLD")
        self.assertEqual(s["BBB"]["action"], "BUY")
        self.assertAlmostEqual(s["BBB"]["rebalance_quantity"], 15)
        self.assertEqual(s["CCC"]["action"], "BUY")
        self.assertAlmostEqual(s["CCC"]["rebalance_quantity"], 40)

    def test_other_account_holdings_are_ignored(self):
        hold(self.db, "연금저축", "AAA", 100)
        hold(self.db, "IRP", "AAA", 1000)
        signals = self.calc()
        self.assertTrue(all(s["total_assets"] == 1_000_000 for s in signals))
        self.assertEqual(by_ticker(signals)["AAA"]["current_weight"], 100.0)

    def test_empty_account_has_no_division_error(self):
        hold(self.db, "IRP", "AAA", 1000)
        signals = self.calc()
        self.assertEqual(len(signals), 4)
        for s in signals:
            self.assertEqual(s["action"], "HOLD")
            self.assertFalse(s["needs_rebalance"])
            self.assertEqual(s["current_weight"], 0.0)
            self.assertEqual(s["rebalance_quantity"], 0)
            self.assertEqual(s["total_assets"], 0.0)

    def test_missing_price_gives_zero_quantity(self):
        port = dict(PORT)
        port["ZZZ"] = {"name": "Z", "target_weight": 10.0}
        hold(self.db, "연금저축", "AAA", 100)
        s = by_ticker(self.calc(portfolio=port))
        self.assertEqual(s["ZZZ"]["rebalance_quantity"], 0)
        self.assertEqual(s["ZZZ"]["current_price"], 0.0)

    def test_signal_keys_and_account_type(self):
        hold(self.db, "연금저축", "AAA", 10)
        for s in self.calc():
            self.assertEqual(set(s), KEYS)
            self.assertEqual(s["account_type"], "연금저축")

    def test_irp_wrapper_matches_generic(self):
        hold(self.db, "IRP", "360750", 10)
        self.db.add(ETFPrice(ticker="360750", price_date=D, close_price=20000))
        self.db.commit()
        self.assertEqual(
            self.engine.calculate_rebalance_signal(D),
            self.engine.calculate_fixed_rebalance_signal(D, "IRP", config.IRP_PORTFOLIO))
        self.assertEqual(self.engine.total_assets, 200000)


class StrategySwitchTest(unittest.TestCase):
    def test_fixed_includes_both_accounts(self):
        accounts = config.fixed_allocation_accounts()
        self.assertEqual(list(accounts), ["연금저축", "IRP"])
        self.assertIs(accounts["연금저축"], accounts["IRP"])
        self.assertIs(config.PENSION_PORTFOLIO, config.IRP_PORTFOLIO)

    def test_momentum_includes_irp_only(self):
        original = config.PENSION_STRATEGY
        config.PENSION_STRATEGY = "momentum"
        try:
            self.assertEqual(list(config.fixed_allocation_accounts()), ["IRP"])
        finally:
            config.PENSION_STRATEGY = original


class SchedulerFixedTest(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        hold(self.db, "연금저축", "AAA", 10)
        self.job = scheduler.JobScheduler()

    def tearDown(self):
        self.db.close()

    @patch("scheduler.SignalAccuracyEngine")
    @patch("scheduler.WebhookNotifier")
    @patch("scheduler.TelegramNotificationManager")
    def test_run_fixed_rebalance_sends_alert_with_account_label(self, tg, wh, acc):
        acc.return_value.record_rebalance_signal.return_value = {
            "signal_id": "x", "direction": "BUY", "confidence": 0.5}
        signals = self.job._run_fixed_rebalance(self.db, "연금저축", PORT, D)

        self.assertTrue(signals)
        send = tg.return_value.send_rebalance_alert
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["label"], "연금저축")
        wh.return_value.send_webhook.assert_called_once()
        event, payload = wh.return_value.send_webhook.call_args.args
        self.assertEqual(event, "rebalance_signal")
        self.assertEqual(payload["label"], "연금저축")
        rows = self.db.query(RebalanceSignal).all()
        self.assertEqual(len(rows), len(signals))
        self.assertTrue(all(r.account_type == "연금저축" for r in rows))
        self.assertEqual(acc.return_value.record_rebalance_signal.call_count, len(signals))

    def test_one_account_failure_does_not_stop_the_other(self):
        calls = []

        def fake(db, account, portfolio, signal_date):
            calls.append(account)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return []

        with patch.object(self.job, "_run_fixed_rebalance", side_effect=fake):
            self.job._check_fixed_accounts(self.db, D)
        self.assertEqual(calls, ["연금저축", "IRP"])

    def test_momentum_job_is_skipped_when_fixed(self):
        with patch("scheduler.get_db") as get_db:
            self.job._job_calculate_momentum()
        get_db.assert_not_called()

    def test_pension_price_map_follows_strategy(self):
        original = config.PENSION_STRATEGY
        try:
            config.PENSION_STRATEGY = "fixed"
            self.assertIs(scheduler.pension_price_map(), config.PENSION_PORTFOLIO)
            config.PENSION_STRATEGY = "momentum"
            self.assertIs(scheduler.pension_price_map(), config.PENSION_ETFS)
        finally:
            config.PENSION_STRATEGY = original


if __name__ == "__main__":
    unittest.main()
