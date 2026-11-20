# -*- coding: utf-8 -*-
"""ReBalancer - 모멘텀 점수용 수정주가(분배금 재투자 반영) 조회

DB의 etf_prices.close_price는 분배금이 빠진 실제 종가다. 평가금액·알림·매매 수량에는
그 값이 맞지만, 모멘텀 점수를 그 값으로 내면 분배금을 많이 주는 ETF가 불리해진다.
그래서 점수 계산에만 야후 파이낸스의 수정주가를 쓴다.

수정주가는 분배금이 나올 때마다 과거 값이 통째로 바뀌므로 DB에 쌓지 않고,
계산할 때마다 필요한 기간을 새로 받는다.

안전장치: 야후의 미수정 종가가 DB 종가와 다르거나 조회가 실패하면 수정주가를 쓰지 않는다.
종목끼리 점수를 비교하므로 한 종목이라도 실패하면 전 종목을 기존 방식(DB 종가)으로 계산한다.
"""

import logging
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from database import ETFPrice

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
YAHOO_TIMEOUT = 15

# 점수 계산에 필요한 과거 기간: 12개월(240일) 조회와 MA10(30일 x 9) 중 긴 쪽 + 여유
LOOKBACK_DAYS = 330
# DB 종가와 대조할 최근 거래일 수, 최소 겹침 수, 허용 오차
VERIFY_RECENT_DAYS = 30
VERIFY_MIN_COMMON = 5
VERIFY_TOLERANCE = 0.001

# (날짜, 미수정 종가, 수정주가)
YahooRow = Tuple[date, float, float]
# 종목별 (날짜 오름차순 목록, 같은 순서의 수정주가 목록)
AdjustedSeries = Tuple[List[date], List[float]]


def yahoo_symbol(ticker: str) -> str:
    """KRX 상장 ETF의 야후 심볼"""
    return f"{ticker}.KS"


def parse_yahoo_chart(payload: dict) -> List[YahooRow]:
    """야후 차트 API 응답에서 (날짜, 종가, 수정주가)를 날짜 오름차순으로 뽑는다.

    종가나 수정주가가 비어 있는 날은 버린다. 형식이 예상과 다르면 ValueError.
    """
    try:
        result = payload['chart']['result'][0]
        timestamps = result['timestamp']
        offset = result['meta'].get('gmtoffset', 0)
        closes = result['indicators']['quote'][0]['close']
        adj_closes = result['indicators']['adjclose'][0]['adjclose']
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"unexpected Yahoo chart payload: {type(e).__name__}") from e

    rows = {}
    for ts, close, adj in zip(timestamps, closes, adj_closes):
        if close is None or adj is None:
            continue
        # 거래소 현지 날짜로 바꾼다 (KRX는 UTC+9)
        day = (datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(seconds=offset)).date()
        rows[day] = (float(close), float(adj))
    return [(d, c, a) for d, (c, a) in sorted(rows.items())]


def fetch_yahoo_rows(ticker: str, start: date, end: date) -> List[YahooRow]:
    """야후에서 start~end 일별 시세를 받는다. 실패하면 예외를 던진다."""
    params = {
        'period1': int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
        'period2': int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()) + 86400,
        'interval': '1d',
        'events': 'div,splits',
    }
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=yahoo_symbol(ticker)),
        params=params, headers=YAHOO_HEADERS, timeout=YAHOO_TIMEOUT,
    )
    response.raise_for_status()
    return parse_yahoo_chart(response.json())


def verify_against_db(rows: List[YahooRow], db_closes: Dict[date, float], calc_date: date) -> Optional[str]:
    """야후 자료가 DB 종가와 맞는지 확인한다. 문제가 없으면 None, 있으면 사유 문자열.

    - DB의 최신 거래일(calc_date 이하)이 야후에도 있어야 한다(야후가 뒤처지지 않았는지).
    - 최근 거래일들의 야후 미수정 종가가 DB 종가와 허용 오차 안에서 같아야 한다.
    """
    db_dates = sorted(d for d in db_closes if d <= calc_date)
    if not db_dates:
        return "DB에 종가가 없음"
    if not rows:
        return "야후 자료가 비어 있음"

    yahoo_close = {d: c for d, c, _ in rows}
    latest_db = db_dates[-1]
    if latest_db not in yahoo_close:
        return f"야후에 {latest_db.isoformat()} 자료가 없음"

    common = [d for d in db_dates[-VERIFY_RECENT_DAYS:] if d in yahoo_close]
    if len(common) < VERIFY_MIN_COMMON:
        return f"DB와 겹치는 최근 거래일이 {len(common)}일뿐임"

    for d in common:
        db_price = db_closes[d]
        if db_price <= 0 or abs(yahoo_close[d] / db_price - 1) > VERIFY_TOLERANCE:
            return (
                f"{d.isoformat()} 종가 불일치 (DB {db_price:,.0f}원, 야후 {yahoo_close[d]:,.0f}원)"
            )
    return None


def load_adjusted_prices(db, tickers, calc_date: date, fetch=fetch_yahoo_rows) -> Tuple[Dict[str, AdjustedSeries], Optional[str]]:
    """점수 계산용 수정주가를 종목별로 받아 검증한다.

    Returns:
        (종목별 수정주가, None)  전 종목 성공
        ({}, 사유)               한 종목이라도 실패 -> 호출 쪽은 DB 종가로 계산해야 한다
    """
    start = calc_date - timedelta(days=LOOKBACK_DAYS)
    adjusted: Dict[str, AdjustedSeries] = {}

    for ticker in tickers:
        db_rows = db.query(ETFPrice.price_date, ETFPrice.close_price).filter(
            ETFPrice.ticker == ticker,
            ETFPrice.price_date >= start,
            ETFPrice.price_date <= calc_date,
        ).all()
        db_closes = {d: float(p) for d, p in db_rows}

        try:
            rows = fetch(ticker, start, calc_date)
        except Exception as e:
            reason = f"{ticker}: 야후 조회 실패 ({type(e).__name__})"
            logger.error(f"[Adjusted Prices] {reason}: {e}")
            return {}, reason

        problem = verify_against_db(rows, db_closes, calc_date)
        if problem:
            reason = f"{ticker}: {problem}"
            logger.error(f"[Adjusted Prices] {reason}")
            return {}, reason

        # DB의 최신 거래일까지만 쓴다. 점수의 현재가 날짜를 DB 종가의 날짜와 맞추기 위해서다.
        latest_db = max(db_closes)
        kept = [(d, a) for d, _, a in rows if d <= latest_db]
        adjusted[ticker] = ([d for d, _ in kept], [a for _, a in kept])

    logger.info(f"[Adjusted Prices] Loaded for {list(adjusted)} (calc_date {calc_date})")
    return adjusted, None


def price_on_or_before(series: AdjustedSeries, target: date) -> Optional[float]:
    """target 이하의 가장 최근 수정주가. 없으면 None (DB 조회 get_price_on_date와 같은 규칙)."""
    dates, prices = series
    i = bisect_right(dates, target)
    return prices[i - 1] if i > 0 else None
