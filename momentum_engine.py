# -*- coding: utf-8 -*-
"""ReBalancer - 모멘텀 계산 엔진"""

import logging
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import MOMENTUM_WEIGHTS, MOMENTUM_POSITIVE_THRESHOLD, MA_PERIOD_MONTHS, MOMENTUM_TOP_N, PENSION_ETFS
from database import ETFPrice, MomentumScore

logger = logging.getLogger(__name__)

class MomentumEngine:
    """모멘텀 계산"""

    def __init__(self, db: Session):
        self.db = db

    def get_price_on_date(self, ticker: str, target_date: date) -> float:
        """특정 날짜의 종가 조회 (정확한 날짜 또는 가장 가까운 이전 거래일)"""
        price = self.db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker,
            ETFPrice.price_date <= target_date
        ).order_by(ETFPrice.price_date.desc()).first()

        return price.close_price if price else None

    def calculate_return(self, start_price: float, end_price: float) -> float:
        """수익률 계산: ((종가 - 시작가) / 시작가) * 100"""
        if start_price is None or end_price is None or start_price == 0:
            return 0.0
        return ((end_price - start_price) / start_price) * 100

    def get_moving_average(self, ticker: str, calc_date: date, period: int = 10) -> float:
        """이동평균 계산"""
        start_date = calc_date - timedelta(days=period * 2)  # 충분한 기간 조회

        prices = self.db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker,
            ETFPrice.price_date >= start_date,
            ETFPrice.price_date <= calc_date
        ).order_by(ETFPrice.price_date.desc()).limit(period).all()

        if not prices or len(prices) < period:
            return 0.0

        avg = sum(p.close_price for p in prices) / len(prices)
        return avg

    def calculate_momentum_score(self, ticker: str, calc_date: date):
        """모멘텀 스코어 계산"""
        result = {
            'ticker': ticker,
            'calc_date': calc_date,
            'r3': 0.0,
            'r6': 0.0,
            'r12': 0.0,
            'weighted_score': 0.0,
            'ma10': 0.0,
            'passed_condition': False
        }

        try:
            # 현재 가격 (calc_date 기준)
            current_price = self.get_price_on_date(ticker, calc_date)
            if current_price is None:
                logger.warning(f"No price data for {ticker} on {calc_date}")
                return result

            # 3개월(약 60일) 전 가격
            date_3m = calc_date - timedelta(days=60)
            price_3m = self.get_price_on_date(ticker, date_3m)
            result['r3'] = self.calculate_return(price_3m, current_price) if price_3m else 0.0

            # 6개월(약 120일) 전 가격
            date_6m = calc_date - timedelta(days=120)
            price_6m = self.get_price_on_date(ticker, date_6m)
            result['r6'] = self.calculate_return(price_6m, current_price) if price_6m else 0.0

            # 12개월(약 240일) 전 가격
            date_12m = calc_date - timedelta(days=240)
            price_12m = self.get_price_on_date(ticker, date_12m)
            result['r12'] = self.calculate_return(price_12m, current_price) if price_12m else 0.0

            # 10일 이동평균
            result['ma10'] = self.get_moving_average(ticker, calc_date, period=10)

            # 가중 평균 계산
            weighted_score = (
                result['r3'] * MOMENTUM_WEIGHTS['R3'] +
                result['r6'] * MOMENTUM_WEIGHTS['R6'] +
                result['r12'] * MOMENTUM_WEIGHTS['R12']
            )
            result['weighted_score'] = weighted_score
            result['passed_condition'] = weighted_score > MOMENTUM_POSITIVE_THRESHOLD

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
