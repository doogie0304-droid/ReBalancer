# -*- coding: utf-8 -*-
"""ReBalancer - 모멘텀 계산 엔진"""

import logging
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import (
    MOMENTUM_WEIGHTS, MOMENTUM_POSITIVE_THRESHOLD, MA_PERIOD_MONTHS, MOMENTUM_TOP_N, PENSION_ETFS,
    MOMENTUM_USE_ADJUSTED_PRICES,
)
from database import ETFPrice, MomentumScore
from adjusted_prices import price_on_or_before, load_adjusted_prices

logger = logging.getLogger(__name__)

def create_momentum_engine(db: Session, calc_date: date, loader=load_adjusted_prices):
    """설정에 따라 수정주가를 받아 모멘텀 엔진을 만든다.

    Returns:
        (engine, fallback_reason). 수정주가를 쓰도록 설정됐는데 조회·검증에 실패하면
        engine은 DB 종가 기준이고 fallback_reason에 사유가 담긴다. 그 외에는 None.
    """
    if not MOMENTUM_USE_ADJUSTED_PRICES:
        return MomentumEngine(db), None

    # 현금처럼 시세가 없는 항목은 점수 대상이 아니므로 조회하지 않는다
    tickers = [t for t, info in PENSION_ETFS.items() if info.get('type') != 'cash']
    try:
        adjusted, reason = loader(db, tickers, calc_date)
    except Exception as e:
        logger.error(f"[Adjusted Prices] Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        adjusted, reason = {}, f"수정주가 조회 중 오류 ({type(e).__name__})"
    return MomentumEngine(db, adjusted_prices=adjusted), reason


class MomentumEngine:
    """모멘텀 계산"""

    def __init__(self, db: Session, adjusted_prices: dict = None):
        """adjusted_prices: 종목별 수정주가(adjusted_prices.load_adjusted_prices의 결과).

        주어지면 점수(R3/R6/R12)와 MA10을 분배금이 재투자된 수정주가로 계산한다.
        비어 있으면 기존처럼 DB의 실제 종가로 계산한다. 종목끼리 점수를 비교하므로
        한 엔진 안에서는 전 종목이 같은 기준을 쓴다(현금처럼 시세가 없는 종목 제외).
        """
        self.db = db
        self.adjusted_prices = adjusted_prices or {}
        self.price_basis = "adjusted" if self.adjusted_prices else "raw"

    def get_price_on_date(self, ticker: str, target_date: date) -> float:
        """특정 날짜의 종가 조회 (정확한 날짜 또는 가장 가까운 이전 거래일)"""
        price = self.db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker,
            ETFPrice.price_date <= target_date
        ).order_by(ETFPrice.price_date.desc()).first()

        return price.close_price if price else None

    def get_score_price(self, ticker: str, target_date: date) -> float:
        """점수 계산용 가격. 수정주가가 있으면 그 값, 없으면 DB 종가."""
        series = self.adjusted_prices.get(ticker)
        if series is not None:
            return price_on_or_before(series, target_date)
        return self.get_price_on_date(ticker, target_date)

    def calculate_return(self, start_price: float, end_price: float) -> float:
        """수익률 계산: ((종가 - 시작가) / 시작가) * 100"""
        if start_price is None or end_price is None or start_price == 0:
            return 0.0
        return ((end_price - start_price) / start_price) * 100

    def get_moving_average(self, ticker: str, calc_date: date, period_months: int = MA_PERIOD_MONTHS) -> float:
        """N개월 이동평균 계산 (당월 포함, 매 30일 간격 스냅샷 종가의 평균)"""
        prices = []
        for i in range(period_months):
            snapshot_date = calc_date - timedelta(days=i * 30)
            price = self.get_score_price(ticker, snapshot_date)
            if price is not None:
                prices.append(price)

        if len(prices) < period_months:
            return 0.0

        return sum(prices) / len(prices)

    def calculate_momentum_score(self, ticker: str, calc_date: date):
        """모멘텀 스코어 계산"""
        result = {
            'ticker': ticker,
            'calc_date': calc_date,
            'current_price': 0.0,
            'r3': 0.0,
            'r6': 0.0,
            'r12': 0.0,
            'weighted_score': 0.0,
            'ma10': 0.0,
            'passed_condition': False,
            'price_basis': self.price_basis
        }

        try:
            # 현재 가격 (calc_date 기준)
            current_price = self.get_price_on_date(ticker, calc_date)
            if current_price is None:
                logger.warning(f"No price data for {ticker} on {calc_date}")
                return result

            # current_price는 화면·알림·매매 수량에 쓰는 실제 종가다. 점수는 score_price로 낸다.
            result['current_price'] = current_price
            score_price = self.get_score_price(ticker, calc_date)
            if score_price is None:
                logger.warning(f"No score price for {ticker} on {calc_date}")
                return result

            # 3개월(약 60일) 전 가격
            date_3m = calc_date - timedelta(days=60)
            price_3m = self.get_score_price(ticker, date_3m)
            result['r3'] = self.calculate_return(price_3m, score_price) if price_3m else 0.0

            # 6개월(약 120일) 전 가격
            date_6m = calc_date - timedelta(days=120)
            price_6m = self.get_score_price(ticker, date_6m)
            result['r6'] = self.calculate_return(price_6m, score_price) if price_6m else 0.0

            # 12개월(약 240일) 전 가격
            date_12m = calc_date - timedelta(days=240)
            price_12m = self.get_score_price(ticker, date_12m)
            result['r12'] = self.calculate_return(price_12m, score_price) if price_12m else 0.0

            # MA_PERIOD_MONTHS개월 이동평균 (절대모멘텀 필터용)
            result['ma10'] = self.get_moving_average(ticker, calc_date, period_months=MA_PERIOD_MONTHS)

            # 가중 평균 계산
            weighted_score = (
                result['r3'] * MOMENTUM_WEIGHTS['R3'] +
                result['r6'] * MOMENTUM_WEIGHTS['R6'] +
                result['r12'] * MOMENTUM_WEIGHTS['R12']
            )
            result['weighted_score'] = weighted_score

            # 가중 모멘텀 점수가 양(+)이고, 현재가가 MA10 위에 있어야 통과 (MA10=0.0은 데이터 부족으로 미통과 처리)
            result['passed_condition'] = (
                weighted_score > MOMENTUM_POSITIVE_THRESHOLD
                and result['ma10'] > 0
                and score_price > result['ma10']
            )

            logger.debug(f"{ticker}: r3={result['r3']:.2f}%, r6={result['r6']:.2f}%, r12={result['r12']:.2f}%, weighted={weighted_score:.2f}%")

        except Exception as e:
            logger.error(f"Error calculating momentum for {ticker}: {e}")

        return result

    def select_top_n_passed(self, calc_date: date, n: int = MOMENTUM_TOP_N) -> list:
        """모멘텀 조건 통과한 종목 중 TOP N 선정"""
        logger.info(f"Selecting TOP {n} stocks on {calc_date}")

        try:
            scores = []

            # 모든 관리 종목에 대해 모멘텀 계산
            for ticker in PENSION_ETFS.keys():
                score = self.calculate_momentum_score(ticker, calc_date)
                scores.append(score)

            # 조건 통과한 종목만 필터링
            passed_scores = [s for s in scores if s['passed_condition']]

            if not passed_scores:
                logger.warning(f"No stocks passed momentum condition on {calc_date}")
                return []

            # weighted_score 기준 내림차순 정렬
            passed_scores.sort(key=lambda x: x['weighted_score'], reverse=True)

            # 상위 N개 선택
            top_n = passed_scores[:n]

            # rank_in_month 추가
            for rank, score in enumerate(top_n, 1):
                score['rank_in_month'] = rank
                score['is_selected'] = True

            logger.info(
                f"Selected {len(top_n)} stocks: {[s['ticker'] for s in top_n]}"
            )

            return top_n

        except Exception as e:
            logger.error(f"Error selecting top N stocks: {e}")
            return []

    def save_momentum_scores(self, scores: list, calc_date: date) -> int:
        """모멘텀 스코어를 DB에 저장"""
        saved_count = 0

        try:
            for score in scores:
                # 기존 데이터 확인
                existing = self.db.query(MomentumScore).filter(
                    MomentumScore.ticker == score['ticker'],
                    MomentumScore.calc_date == calc_date
                ).first()

                if existing:
                    # 기존 데이터 업데이트
                    existing.r3 = score['r3']
                    existing.r6 = score['r6']
                    existing.r12 = score['r12']
                    existing.weighted_score = score['weighted_score']
                    existing.ma10 = score['ma10']
                    existing.passed_condition = score['passed_condition']
                    existing.rank_in_month = score.get('rank_in_month')
                    existing.is_selected = score.get('is_selected', False)
                else:
                    # 새 데이터 추가
                    new_record = MomentumScore(
                        ticker=score['ticker'],
                        calc_date=calc_date,
                        r3=score['r3'],
                        r6=score['r6'],
                        r12=score['r12'],
                        weighted_score=score['weighted_score'],
                        ma10=score['ma10'],
                        passed_condition=score['passed_condition'],
                        rank_in_month=score.get('rank_in_month'),
                        is_selected=score.get('is_selected', False)
                    )
                    self.db.add(new_record)

                saved_count += 1

            # 커밋
            self.db.commit()
            logger.info(f"Saved {saved_count} momentum scores for {calc_date}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving momentum scores: {e}")
            saved_count = 0

        return saved_count
