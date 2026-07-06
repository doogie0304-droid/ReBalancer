# -*- coding: utf-8 -*-
"""ReBalancer - IRP 리밸런싱 엔진"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
from config import REBALANCE_BAND_PCT, IRP_PORTFOLIO
from database import ETFPrice, RebalanceSignal

logger = logging.getLogger(__name__)

class RebalanceEngine:
    """리밸런싱 계산"""

    def __init__(self, db: Session, total_assets: float = 10000000.0):
        self.db = db
        self.total_assets = total_assets  # Default: 1000만원

    def get_latest_price(self, ticker: str):
        """최신 종가 조회"""
        price_record = self.db.query(ETFPrice).filter(
            ETFPrice.ticker == ticker
        ).order_by(desc(ETFPrice.price_date)).first()

        if not price_record:
            logger.warning(f"No price data found for {ticker}")
            return None

        return {
            'ticker': ticker,
            'price': price_record.close_price,
            'date': price_record.price_date
        }

    def calculate_current_weights(self):
        """현재 자산 배분 계산"""
        current_distribution = {}
        total_value = 0.0

        for ticker in IRP_PORTFOLIO.keys():
            price_info = self.get_latest_price(ticker)
            if not price_info:
                current_distribution[ticker] = {
                    'price': 0.0,
                    'amount': 0.0,
                    'weight': 0.0
                }
                continue

            # 목표 비중 기반 수량 계산 (동일하게 배분된 포트폴리오 가정)
            target_weight = IRP_PORTFOLIO[ticker]['target_weight']
            target_amount = (self.total_assets * target_weight) / 100
            quantity = target_amount / price_info['price']
            current_value = quantity * price_info['price']

            current_distribution[ticker] = {
                'price': price_info['price'],
                'quantity': quantity,
                'amount': current_value,
                'weight': (current_value / self.total_assets) * 100
            }
            total_value += current_value

        return current_distribution

    def calculate_rebalance_signal(self, signal_date, total_assets: float = None):
        """리밸런싱 신호 계산

        신호 판정:
        - weight_diff > BAND_PCT: SELL (과매수)
        - weight_diff < -BAND_PCT: BUY (과매도)
        - 그 외: HOLD
        """
        if total_assets:
            self.total_assets = total_assets

        signals = []
        current_weights = self.calculate_current_weights()

        for ticker, target_info in IRP_PORTFOLIO.items():
            target_weight = target_info['target_weight']

            if ticker not in current_weights:
                logger.warning(f"Missing current weight for {ticker}")
                continue

            current_data = current_weights[ticker]
            current_weight = current_data['weight']
            weight_diff = current_weight - target_weight

            # 신호 판정
            if weight_diff > REBALANCE_BAND_PCT:
                action = "SELL"
                needs_rebalance = True
                rebalance_amount = current_data['amount'] - (self.total_assets * target_weight / 100)
            elif weight_diff < -REBALANCE_BAND_PCT:
                action = "BUY"
                needs_rebalance = True
                rebalance_amount = (self.total_assets * target_weight / 100) - current_data['amount']
            else:
                action = "HOLD"
                needs_rebalance = False
                rebalance_amount = 0.0

            # 수량 계산
            rebalance_quantity = abs(rebalance_amount / current_data['price']) if current_data['price'] > 0 else 0

            signal = {
                'ticker': ticker,
                'signal_date': signal_date,
                'target_weight': target_weight,
                'current_weight': current_weight,
                'weight_diff': weight_diff,
                'current_price': current_data['price'],
                'total_assets': self.total_assets,
                'target_amount': self.total_assets * target_weight / 100,
                'current_amount': current_data['amount'],
                'rebalance_amount': rebalance_amount,
                'rebalance_quantity': rebalance_quantity,
                'action': action,
                'needs_rebalance': needs_rebalance
            }
            signals.append(signal)

        return signals

    def save_rebalance_signals(self, signals: list):
        """리밸런싱 신호를 DB에 저장"""
        saved_count = 0

        for signal in signals:
            try:
                rebalance_record = RebalanceSignal(
                    ticker=signal['ticker'],
                    signal_date=signal['signal_date'],
                    target_weight=signal['target_weight'],
                    current_weight=signal['current_weight'],
                    weight_diff=signal['weight_diff'],
                    current_price=signal['current_price'],
                    total_assets=signal['total_assets'],
                    target_amount=signal['target_amount'],
                    current_amount=signal['current_amount'],
                    rebalance_amount=signal['rebalance_amount'],
                    rebalance_quantity=signal['rebalance_quantity'],
                    action=signal['action'],
                    needs_rebalance=signal['needs_rebalance']
                )
                self.db.add(rebalance_record)
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving signal for {signal['ticker']}: {str(e)}")

        try:
            self.db.commit()
            logger.info(f"Saved {saved_count} rebalance signals")
        except Exception as e:
            logger.error(f"Error committing rebalance signals: {str(e)}")
            self.db.rollback()
            raise

        return saved_count
