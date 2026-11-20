# -*- coding: utf-8 -*-
"""수정주가 기반 모멘텀 점수 테스트 (네트워크·운영 DB 불필요)

실행: python -m unittest test_adjusted_momentum -v
"""

import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import adjusted_prices as ap
import momentum_engine as me
from database import Base, ETFPrice
from momentum_engine import MomentumEngine, create_momentum_engine

CALC = date(2026, 8, 3)
LAST = date(2026, 7, 31)


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def seed(db, ticker, price_of):
    """LAST까지 400일치 평일 종가를 넣는다. price_of(날짜) -> 종가"""
    for d in weekdays(LAST - timedelta(days=400), LAST):
        db.add(ETFPrice(ticker=ticker, price_date=d, close_price=price_of(d)))
    db.commit()


def series_from(price_of, start=LAST - timedelta(days=400), end=LAST):
    days = list(weekdays(start, end))
    return (days, [price_of(d) for d in days])


class ParseYahooChartTest(unittest.TestCase):
    def payload(self, rows, offset=32400):
        # 야후는 KRX 장 시작 시각(09:00 KST = 00:00 UTC)을 타임스탬프로 준다
        ts = [int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) for d, _, _ in rows]
        return {'chart': {'result': [{
            'meta': {'gmtoffset': offset},
            'timestamp': ts,
            'indicators': {
                'quote': [{'close': [c for _, c, _ in rows]}],
                'adjclose': [{'adjclose': [a for _, _, a in rows]}],
            },
        }]}}

    def test_rows_sorted_with_local_dates(self):
        rows = [(date(2026, 7, 31), 15410.0, 15285.0), (date(2026, 7, 30), 15300.0, 15176.0)]
        out = ap.parse_yahoo_chart(self.payload(rows))
        self.assertEqual(out, [(date(2026, 7, 30), 15300.0, 15176.0), (date(2026, 7, 31), 15410.0, 15285.0)])

    def test_rows_with_missing_values_are_dropped(self):
        rows = [(date(2026, 7, 30), None, None), (date(2026, 7, 31), 15410.0, 15285.0)]
        self.assertEqual(len(ap.parse_yahoo_chart(self.payload(rows))), 1)

    def test_unexpected_payload_raises(self):
        with self.assertRaises(ValueError):
            ap.parse_yahoo_chart({'chart': {'result': None, 'error': {'code': 'Not Found'}}})


class VerifyAgainstDbTest(unittest.TestCase):
    def setUp(self):
        self.days = list(weekdays(date(2026, 7, 1), LAST))
        self.db_closes = {d: 15000.0 + i for i, d in enumerate(self.days)}
        self.rows = [(d, p, p * 0.99) for d, p in self.db_closes.items()]

    def test_matching_data_passes(self):
        self.assertIsNone(ap.verify_against_db(self.rows, self.db_closes, CALC))

    def test_small_rounding_difference_passes(self):
        rows = [(d, c * 1.0005, a) for d, c, a in self.rows]
        self.assertIsNone(ap.verify_against_db(rows, self.db_closes, CALC))

    def test_close_mismatch_is_reported(self):
        rows = list(self.rows)
        d, c, a = rows[-3]
        rows[-3] = (d, c * 1.01, a)
        self.assertIn("종가 불일치", ap.verify_against_db(rows, self.db_closes, CALC))

    def test_yahoo_missing_latest_db_day_is_reported(self):
        self.assertIn("자료가 없음", ap.verify_against_db(self.rows[:-1], self.db_closes, CALC))

    def test_empty_inputs_are_reported(self):
        self.assertIsNotNone(ap.verify_against_db([], self.db_closes, CALC))
        self.assertIsNotNone(ap.verify_against_db(self.rows, {}, CALC))

    def test_too_few_common_days_is_reported(self):
        self.assertIn("겹치는", ap.verify_against_db(self.rows[-2:], self.db_closes, CALC))


class LoadAdjustedPricesTest(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        seed(self.db, "AAA", lambda d: 10000.0)
        seed(self.db, "BBB", lambda d: 20000.0)

    def fetch_ok(self, ticker, start, end):
        base = 10000.0 if ticker == "AAA" else 20000.0
        return [(d, base, base * 0.9) for d in weekdays(start, end) if d <= LAST]

    def test_all_tickers_loaded(self):
        adjusted, reason = ap.load_adjusted_prices(self.db, ["AAA", "BBB"], CALC, fetch=self.fetch_ok)
        self.assertIsNone(reason)
        self.assertEqual(set(adjusted), {"AAA", "BBB"})
        self.assertEqual(adjusted["AAA"][0][-1], LAST)
        self.assertEqual(adjusted["AAA"][1][-1], 9000.0)

    def test_one_failure_falls_back_for_everything(self):
        def fetch(ticker, start, end):
            if ticker == "BBB":
                raise ConnectionError("boom")
            return self.fetch_ok(ticker, start, end)
        adjusted, reason = ap.load_adjusted_prices(self.db, ["AAA", "BBB"], CALC, fetch=fetch)
        self.assertEqual(adjusted, {})
        self.assertIn("BBB", reason)
        self.assertIn("조회 실패", reason)

    def test_mismatch_falls_back_for_everything(self):
        def fetch(ticker, start, end):
            rows = self.fetch_ok(ticker, start, end)
            return [(d, c * 1.05, a) for d, c, a in rows] if ticker == "AAA" else rows
        adjusted, reason = ap.load_adjusted_prices(self.db, ["AAA", "BBB"], CALC, fetch=fetch)
        self.assertEqual(adjusted, {})
        self.assertIn("AAA", reason)

    def test_yahoo_rows_after_latest_db_day_are_not_used(self):
        def fetch(ticker, start, end):
            return self.fetch_ok(ticker, start, end) + [(CALC, 99999.0, 99999.0)]
        adjusted, reason = ap.load_adjusted_prices(self.db, ["AAA"], CALC, fetch=fetch)
        self.assertIsNone(reason)
        self.assertEqual(adjusted["AAA"][0][-1], LAST)


class PriceOnOrBeforeTest(unittest.TestCase):
    def test_lookup_rules(self):
        s = ([date(2026, 7, 30), date(2026, 7, 31)], [1.0, 2.0])
        self.assertEqual(ap.price_on_or_before(s, date(2026, 8, 3)), 2.0)   # 주말을 건너 직전 거래일
        self.assertEqual(ap.price_on_or_before(s, date(2026, 7, 30)), 1.0)  # 당일 포함
        self.assertIsNone(ap.price_on_or_before(s, date(2026, 7, 29)))      # 그 이전은 없음


class MomentumEngineBasisTest(unittest.TestCase):
    """종가는 평평한데 분배금만 나온 종목: 종가 기준 점수는 0, 수정주가 기준은 양수여야 한다."""

    def setUp(self):
        self.db = make_db()
        seed(self.db, "DIV", lambda d: 10000.0)
        # 수정주가: 과거로 갈수록 낮다(하루 0.01%씩 분배금이 쌓인 것과 같은 모양)
        self.adj = series_from(lambda d: 10000.0 * (1 - 0.0001 * (LAST - d).days))

    def test_raw_basis_is_unchanged_behaviour(self):
        r = MomentumEngine(self.db).calculate_momentum_score("DIV", CALC)
        self.assertEqual(r['price_basis'], "raw")
        self.assertEqual(r['current_price'], 10000.0)
        self.assertAlmostEqual(r['weighted_score'], 0.0)
        self.assertFalse(r['passed_condition'])   # 점수가 0보다 크지 않고 현재가가 MA10과 같다

    def test_adjusted_basis_scores_on_adjusted_but_shows_raw_close(self):
        r = MomentumEngine(self.db, adjusted_prices={"DIV": self.adj}).calculate_momentum_score("DIV", CALC)
        self.assertEqual(r['price_basis'], "adjusted")
        self.assertEqual(r['current_price'], 10000.0)   # 화면·매매 수량용 가격은 실제 종가 그대로

        def adj_at(days_back):
            return ap.price_on_or_before(self.adj, CALC - timedelta(days=days_back))
        cur = adj_at(0)
        expected = sum(w * (cur / adj_at(n) - 1) * 100 for w, n in ((0.2, 60), (0.3, 120), (0.5, 240)))
        self.assertAlmostEqual(r['weighted_score'], expected, places=6)
        self.assertGreater(r['weighted_score'], 0)
        self.assertAlmostEqual(r['ma10'], sum(adj_at(30 * i) for i in range(10)) / 10, places=6)
        self.assertTrue(r['passed_condition'])

    def test_ranking_can_change_with_basis(self):
        # GRO: 종가가 조금 오르고 분배금 없음. DIV: 종가는 평평하지만 분배금이 더 큼.
        seed(self.db, "GRO", lambda d: 10000.0 * (1 - 0.00005 * (LAST - d).days))
        gro_adj = series_from(lambda d: 10000.0 * (1 - 0.00005 * (LAST - d).days))
        raw = MomentumEngine(self.db)
        adj = MomentumEngine(self.db, adjusted_prices={"DIV": self.adj, "GRO": gro_adj})
        self.assertGreater(raw.calculate_momentum_score("GRO", CALC)['weighted_score'],
                           raw.calculate_momentum_score("DIV", CALC)['weighted_score'])
        self.assertGreater(adj.calculate_momentum_score("DIV", CALC)['weighted_score'],
                           adj.calculate_momentum_score("GRO", CALC)['weighted_score'])

    def test_ticker_without_adjusted_series_uses_db_close(self):
        # 현금처럼 수정주가 대상이 아닌 종목은 엔진이 수정주가 기준이어도 DB 종가로 계산된다
        seed(self.db, "OTH", lambda d: 5000.0)
        r = MomentumEngine(self.db, adjusted_prices={"DIV": self.adj}).calculate_momentum_score("OTH", CALC)
        self.assertEqual(r['current_price'], 5000.0)
        self.assertAlmostEqual(r['weighted_score'], 0.0)


class CreateMomentumEngineTest(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        self.calls = []

    def loader_ok(self, db, tickers, calc_date):
        self.calls.append(list(tickers))
        return {t: ([LAST], [1.0]) for t in tickers}, None

    def test_uses_adjusted_and_skips_cash(self):
        engine, reason = create_momentum_engine(self.db, CALC, loader=self.loader_ok)
        self.assertIsNone(reason)
        self.assertEqual(engine.price_basis, "adjusted")
        self.assertNotIn("CASH", self.calls[0])
        self.assertIn("402970", self.calls[0])

    def test_loader_reported_failure_falls_back_to_raw(self):
        engine, reason = create_momentum_engine(self.db, CALC, loader=lambda db, t, c: ({}, "402970: 야후 조회 실패"))
        self.assertEqual(engine.price_basis, "raw")
        self.assertIn("402970", reason)

    def test_loader_exception_falls_back_to_raw(self):
        def boom(db, tickers, calc_date):
            raise RuntimeError("unexpected")
        engine, reason = create_momentum_engine(self.db, CALC, loader=boom)
        self.assertEqual(engine.price_basis, "raw")
        self.assertIn("RuntimeError", reason)

    def test_flag_off_never_calls_loader(self):
        original = me.MOMENTUM_USE_ADJUSTED_PRICES
        me.MOMENTUM_USE_ADJUSTED_PRICES = False
        try:
            engine, reason = create_momentum_engine(self.db, CALC, loader=self.loader_ok)
        finally:
            me.MOMENTUM_USE_ADJUSTED_PRICES = original
        self.assertEqual((engine.price_basis, reason, self.calls), ("raw", None, []))


if __name__ == "__main__":
    unittest.main()
