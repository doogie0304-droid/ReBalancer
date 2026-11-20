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


class FixedCashAndQuantityTest(unittest.TestCase):
    """최종 검토 보완: 현금 평가(F1), 정수 수량(F3)"""

    def setUp(self):
        self.db = make_db()
        self.engine = RebalanceEngine(self.db)

    def tearDown(self):
        self.db.close()

    def calc(self, account="연금저축", portfolio=PORT):
        return self.engine.calculate_fixed_rebalance_signal(D, account, portfolio)

    def test_cash_counts_in_total_and_sizes_buys(self):
        hold(self.db, "연금저축", "AAA", 50)
        hold(self.db, "연금저축", "CASH", 500000)
        signals = self.calc()
        s = by_ticker(signals)
        self.assertTrue(all(x["total_assets"] == 1_000_000 for x in signals))
        self.assertEqual(self.engine.total_assets, 1_000_000)
        self.assertEqual(s["CASH"]["current_price"], 1.0)
        self.assertEqual(s["CASH"]["current_amount"], 500000)
        self.assertAlmostEqual(s["CASH"]["current_weight"], 50.0)
        self.assertEqual(s["AAA"]["action"], "HOLD")
        self.assertEqual(s["BBB"]["action"], "BUY")
        self.assertEqual(s["BBB"]["rebalance_quantity"], 15)
        self.assertEqual(s["CCC"]["rebalance_quantity"], 40)

    def test_cash_line_is_always_hold_even_far_above_band(self):
        hold(self.db, "연금저축", "AAA", 10)
        hold(self.db, "연금저축", "CASH", 900000)
        c = by_ticker(self.calc())["CASH"]
        self.assertGreater(c["weight_diff"], 50)
        self.assertEqual(c["action"], "HOLD")
        self.assertFalse(c["needs_rebalance"])
        self.assertEqual(c["rebalance_amount"], 0.0)
        self.assertEqual(c["rebalance_quantity"], 0)

    def test_cash_only_account_buys_targets(self):
        hold(self.db, "연금저축", "CASH", 1_000_000)
        s = by_ticker(self.calc())
        self.assertEqual((s["AAA"]["action"], s["AAA"]["rebalance_quantity"]), ("BUY", 50))
        self.assertEqual((s["BBB"]["action"], s["BBB"]["rebalance_quantity"]), ("BUY", 15))
        self.assertEqual((s["CCC"]["action"], s["CCC"]["rebalance_quantity"]), ("BUY", 40))
        self.assertEqual(s["CASH"]["action"], "HOLD")
        self.assertEqual(s["CASH"]["rebalance_quantity"], 0)

    def test_cash_applies_to_irp_too(self):
        hold(self.db, "IRP", "CASH", 1_000_000)
        s = by_ticker(self.calc(account="IRP"))
        self.assertEqual(s["AAA"]["rebalance_quantity"], 50)
        self.assertEqual(s["CASH"]["action"], "HOLD")

    def test_fractional_buy_is_floored_and_partial_sell_is_ceiled(self):
        hold(self.db, "연금저축", "AAA", 33)   # 330,000
        hold(self.db, "연금저축", "BBB", 5)    # 100,000
        hold(self.db, "연금저축", "CCC", 11)   # 55,000 -> total 485,000
        s = by_ticker(self.calc())
        self.assertEqual(s["AAA"]["action"], "SELL")
        self.assertAlmostEqual(s["AAA"]["rebalance_amount"], 87500)   # 8.75주
        self.assertEqual(s["AAA"]["rebalance_quantity"], 9)
        self.assertEqual(s["BBB"]["action"], "BUY")
        self.assertAlmostEqual(s["BBB"]["rebalance_amount"], 45500)   # 2.275주
        self.assertEqual(s["BBB"]["rebalance_quantity"], 2)
        self.assertEqual(s["CCC"]["rebalance_quantity"], 8)           # 8.4주
        for x in s.values():
            self.assertEqual(x["rebalance_quantity"], int(x["rebalance_quantity"]))

    def test_sell_to_zero_target_is_capped_at_held_quantity(self):
        hold(self.db, "연금저축", "OLD", 2.5)
        hold(self.db, "연금저축", "AAA", 10)
        s = by_ticker(self.calc())
        self.assertEqual(s["OLD"]["action"], "SELL")
        self.assertEqual(s["OLD"]["rebalance_quantity"], 2.5)   # ceil(2.5)=3 이 아니라 보유 한도

    def test_buy_smaller_than_one_share_is_downgraded_to_hold(self):
        self.db.add(ETFPrice(ticker="BIG", price_date=D, close_price=400000))
        self.db.commit()
        port = dict(PORT)
        port["BIG"] = {"name": "Big", "target_weight": 10.0}
        hold(self.db, "연금저축", "CASH", 1_000_000)
        b = by_ticker(self.calc(portfolio=port))["BIG"]   # 목표 100,000원 < 1주(400,000원)
        self.assertEqual(b["action"], "HOLD")
        self.assertFalse(b["needs_rebalance"])
        self.assertEqual(b["rebalance_quantity"], 0)
        self.assertAlmostEqual(b["rebalance_amount"], 100000)


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
        recorded = [c.kwargs["ticker"] for c in acc.return_value.record_rebalance_signal.call_args_list]
        self.assertNotIn("CASH", recorded)
        self.assertEqual(len(recorded), len(signals) - 1)   # 현금 줄 제외

    @patch("scheduler.SignalAccuracyEngine")
    @patch("scheduler.WebhookNotifier")
    @patch("scheduler.TelegramNotificationManager")
    def test_cash_line_is_not_recorded_for_accuracy(self, tg, wh, acc):
        hold(self.db, "연금저축", "CASH", 500000)
        acc.return_value.record_rebalance_signal.return_value = {
            "signal_id": "x", "direction": "BUY", "confidence": 0.5}
        self.job._run_fixed_rebalance(self.db, "연금저축", PORT, D)
        recorded = [c.kwargs["ticker"] for c in acc.return_value.record_rebalance_signal.call_args_list]
        self.assertNotIn("CASH", recorded)
        self.assertIn("AAA", recorded)

    def test_failed_account_is_rolled_back_and_next_is_processed(self):
        db = MagicMock()
        calls = []

        def fake(_db, account, portfolio, signal_date):
            calls.append(account)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return []

        with patch.object(self.job, "_run_fixed_rebalance", side_effect=fake):
            self.job._check_fixed_accounts(db, D)
        db.rollback.assert_called_once()
        self.assertEqual(calls, ["연금저축", "IRP"])

    def test_rollback_failure_does_not_stop_the_loop(self):
        db = MagicMock()
        db.rollback.side_effect = RuntimeError("rollback broke")
        calls = []

        def fake(_db, account, portfolio, signal_date):
            calls.append(account)
            raise RuntimeError("boom")

        with patch.object(self.job, "_run_fixed_rebalance", side_effect=fake):
            self.job._check_fixed_accounts(db, D)
        self.assertEqual(calls, ["연금저축", "IRP"])

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
        original = config.PENSION_STRATEGY
        config.PENSION_STRATEGY = "fixed"
        try:
            with patch("scheduler.get_db") as get_db:
                self.job._job_calculate_momentum()
        finally:
            config.PENSION_STRATEGY = original
        get_db.assert_not_called()

    def test_momentum_job_runs_when_momentum(self):
        original = config.PENSION_STRATEGY
        config.PENSION_STRATEGY = "momentum"
        try:
            with patch("scheduler._is_business_day", return_value=True),                  patch("scheduler._first_business_day_of_month", return_value=date(2000, 1, 3)),                  patch("scheduler.get_db", side_effect=RuntimeError("sentinel")) as get_db:
                self.job._job_calculate_momentum()  # 센티널 예외는 잡 자체 try/except가 처리
        finally:
            config.PENSION_STRATEGY = original
        get_db.assert_called_once()

    def test_pension_price_map_follows_strategy(self):
        original = config.PENSION_STRATEGY
        try:
            config.PENSION_STRATEGY = "fixed"
            self.assertIs(scheduler.pension_price_map(), config.PENSION_PORTFOLIO)
            config.PENSION_STRATEGY = "momentum"
            self.assertIs(scheduler.pension_price_map(), config.PENSION_ETFS)
        finally:
            config.PENSION_STRATEGY = original


class ViewTargetTest(unittest.TestCase):
    def setUp(self):
        import momentum_view_server
        self.view = momentum_view_server

    def test_pension_targets_come_from_portfolio_when_fixed(self):
        original = config.PENSION_STRATEGY
        config.PENSION_STRATEGY = "fixed"
        try:
            got = self.view.target_weights_for("연금저축", [])
        finally:
            config.PENSION_STRATEGY = original
        self.assertEqual(got, {t: v["target_weight"] for t, v in config.PENSION_PORTFOLIO.items()})

    def test_pension_targets_use_top2_when_momentum(self):
        original = config.PENSION_STRATEGY
        config.PENSION_STRATEGY = "momentum"
        try:
            got = self.view.target_weights_for(
                "연금저축", [{"ticker": "X", "is_selected": True}, {"ticker": "Y", "is_selected": False}])
        finally:
            config.PENSION_STRATEGY = original
        self.assertEqual(got, {"X": 50.0, "Y": 0.0})

    def test_irp_targets_unchanged(self):
        got = self.view.target_weights_for("IRP", [{"ticker": "X", "is_selected": True}])
        self.assertEqual(got, {t: v.get("target_weight", 0) for t, v in config.IRP_PORTFOLIO.items()})


class ManualEndpointTest(unittest.TestCase):
    """httpx 없이 엔드포인트 코루틴을 직접 호출한다."""

    @classmethod
    def setUpClass(cls):
        # main 임포트는 init_db()/스케줄러 시작을 하므로 임포트 동안만 막는다
        with patch("database.init_db"), patch("scheduler.JobScheduler.start"):
            import main
        cls.main = main

    def setUp(self):
        self.db = make_db()
        hold(self.db, "연금저축", "AAA", 10)
        self.patches = [
            patch("scheduler.SignalAccuracyEngine"),
            patch("scheduler.WebhookNotifier"),
            patch("scheduler.TelegramNotificationManager"),
        ]
        self.acc, self.wh, self.tg = [p.start() for p in self.patches]
        self.acc.return_value.record_rebalance_signal.return_value = {
            "signal_id": "x", "direction": "BUY", "confidence": 0.5}
        self.orig = (config.PENSION_STRATEGY, config.PENSION_PORTFOLIO)
        config.PENSION_STRATEGY = "fixed"
        config.PENSION_PORTFOLIO = PORT
        # 핸들러가 요구하는 "직전 영업일"을 시세 날짜 D로 고정 (가드 자체는 실제 함수 사용)
        self.bd = patch.object(self.main, "_previous_business_day", return_value=D)
        self.bd.start()

    def tearDown(self):
        self.bd.stop()
        config.PENSION_STRATEGY, config.PENSION_PORTFOLIO = self.orig
        for p in self.patches:
            p.stop()
        self.db.close()

    def call(self, **kw):
        import asyncio
        return asyncio.run(self.main.trigger_check_pension_rebalance(db=self.db, **kw))

    def test_fixed_response_has_quantities_and_names(self):
        res = self.call(notify=False)
        self.assertEqual(res["strategy"], "fixed")
        self.assertEqual(res["total_signals"], len(res["signals"]))
        self.assertTrue(res["signals"])
        for s in res["signals"]:
            for key in ("name", "current_price", "rebalance_quantity"):
                self.assertIn(key, s)
        self.assertEqual({s["ticker"]: s["name"] for s in res["signals"]}["AAA"], "A")
        self.assertEqual(res["saved_count"], len(res["signals"]))

    def test_notify_false_sends_nothing(self):
        self.call(notify=False)
        self.tg.return_value.send_rebalance_alert.assert_not_called()
        self.wh.return_value.send_webhook.assert_not_called()

    def test_notify_true_sends_one_alert(self):
        res = self.call(notify=True)
        send = self.tg.return_value.send_rebalance_alert
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["label"], "연금저축")
        # 저장은 한 번만
        self.assertEqual(self.db.query(RebalanceSignal).count(), len(res["signals"]))

    def _assert_rejected(self, notify):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            self.call(notify=notify)
        self.assertEqual(cm.exception.status_code, 409)
        self.assertEqual(self.db.query(RebalanceSignal).count(), 0)
        self.tg.return_value.send_rebalance_alert.assert_not_called()
        self.wh.return_value.send_webhook.assert_not_called()
        return cm.exception.detail

    def test_missing_price_is_rejected_with_409(self):
        self.db.query(ETFPrice).filter(ETFPrice.ticker == "CCC").delete()
        self.db.commit()
        for notify in (False, True):
            detail = self._assert_rejected(notify)
            self.assertIn("CCC", detail)
            self.assertIn("없음", detail)

    def test_old_price_of_held_ticker_outside_table_is_rejected(self):
        hold(self.db, "연금저축", "STALE", 5)
        self.db.add(ETFPrice(ticker="STALE", price_date=date(2026, 11, 10), close_price=1000))
        self.db.commit()
        for notify in (False, True):
            detail = self._assert_rejected(notify)
            self.assertIn("STALE", detail)
            self.assertIn("2026-11-10", detail)

    def test_cash_holding_does_not_trigger_the_guard(self):
        hold(self.db, "연금저축", "CASH", 100000)
        res = self.call(notify=False)
        self.assertEqual(res["status"], "ok")

    def test_momentum_ignores_notify(self):
        config.PENSION_STRATEGY = "momentum"
        with patch.object(RebalanceEngine, "calculate_pension_rebalance_signal", return_value=[]) as calc:
            res = self.call(notify=True)
        calc.assert_called_once()
        self.assertEqual(res["strategy"], "momentum")
        self.tg.return_value.send_rebalance_alert.assert_not_called()


class PortfolioPerformanceTest(unittest.TestCase):
    def test_is_selected_false_for_all_when_fixed(self):
        from database import MomentumScore
        from portfolio_engine import PortfolioEngine
        db = make_db()
        hold(db, "연금저축", "AAA", 10)
        db.add(MomentumScore(ticker="AAA", calc_date=D, is_selected=True))
        db.commit()
        original = config.PENSION_STRATEGY
        try:
            config.PENSION_STRATEGY = "fixed"
            fixed = PortfolioEngine(db).calculate_portfolio_performance("연금저축")
            config.PENSION_STRATEGY = "momentum"
            mom = PortfolioEngine(db).calculate_portfolio_performance("연금저축")
        finally:
            config.PENSION_STRATEGY = original
            db.close()
        self.assertTrue(fixed["holdings"])
        self.assertFalse(any(h["is_selected"] for h in fixed["holdings"]))
        self.assertTrue(all(h["is_selected"] for h in mom["holdings"]))


if __name__ == "__main__":
    unittest.main()
