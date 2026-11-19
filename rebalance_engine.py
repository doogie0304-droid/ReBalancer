# -*- coding: utf-8 -*-
"""ReBalancer - IRP 리밸런싱 엔진"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
from config import REBALANCE_BAND_PCT, IRP_PORTFOLIO, PENSION_REBALANCE_BAND_PCT
from database import ETFPrice, MomentumScore, RebalanceSignal, UserPortfolio

logger = logging.getLogger(__name__)

class RebalanceEngine:
    """리밸런싱 계산"""

    def __init__(self, db: Session):
        self.db = db
        self.total_assets = 0.0  # calculate_current_weights()가 실제 보유액으로 채움

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
        """실제 보유 수량(UserPortfolio) 기반 현재 자산 배분 계산"""
        holdings = {
            h.ticker: h for h in self.db.query(UserPortfolio).filter(
                UserPortfolio.account_type == "IRP",
                UserPortfolio.is_active == True
            ).all()
        }

        current_distribution = {}
        total_value = 0.0

        for ticker in IRP_PORTFOLIO.keys():
            price_info = self.get_latest_price(ticker)
            price = price_info['price'] if price_info else 0.0
            holding = holdings.get(ticker)
            quantity = holding.quantity if holding else 0.0
            amount = quantity * price

            current_distribution[ticker] = {
                'price': price,
                'quantity': quantity,
                'amount': amount,
            }
            total_value += amount

        self.total_assets = total_value
        for data in current_distribution.values():
            data['weight'] = (data['amount'] / total_value * 100) if total_value > 0 else 0.0

        return current_distribution

    def calculate_rebalance_signal(self, signal_date):
        """리밸런싱 신호 계산

        신호 판정:
        - weight_diff > BAND_PCT: SELL (과매수)
        - weight_diff < -BAND_PCT: BUY (과매도)
        - 그 외: HOLD
        """
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
                'account_type': 'IRP',
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

    def calculate_pension_rebalance_signal(self, signal_date, band_pct: float = PENSION_REBALANCE_BAND_PCT):
        """연저펀 Top2 밴드형 재조정 신호 계산

        - 가장 최근 모멘텀 계산일에 is_selected=True로 선정된 Top2 종목: 목표 비중 각 50%
        - Top2에서 탈락했는데도 여전히 보유 중인 종목: 목표 비중 0% (전량 매도 신호)
        - weight_diff > band_pct: SELL / weight_diff < -band_pct: BUY / 그 외: HOLD
        """
        latest_calc_date = self.db.query(MomentumScore.calc_date).order_by(
            MomentumScore.calc_date.desc()
        ).first()
        if not latest_calc_date:
            logger.warning("[Pension Rebalance] No momentum score found, skipping")
            return []
        calc_date = latest_calc_date[0]

        selected_tickers = {
            s.ticker for s in self.db.query(MomentumScore).filter(
                MomentumScore.calc_date == calc_date,
                MomentumScore.is_selected == True
            ).all()
        }
        if not selected_tickers:
            logger.warning(f"[Pension Rebalance] No selected tickers for {calc_date}, skipping")
            return []

        holdings = {
            h.ticker: h for h in self.db.query(UserPortfolio).filter(
                UserPortfolio.account_type == "연금저축",
                UserPortfolio.is_active == True
            ).all()
        }

        # 현재 선정된 Top2 + (Top2에서 빠졌지만 아직 보유 중인) 종목까지 포함한 전체 유니버스
        universe = selected_tickers | set(holdings.keys())
        target_weight = {
            ticker: (100.0 / len(selected_tickers)) if ticker in selected_tickers else 0.0
            for ticker in universe
        }

        current_distribution = {}
        total_value = 0.0
        for ticker in universe:
            price_info = self.get_latest_price(ticker)
            price = price_info['price'] if price_info else 0.0
            holding = holdings.get(ticker)
            quantity = holding.quantity if holding else 0.0
            amount = quantity * price
            current_distribution[ticker] = {'price': price, 'quantity': quantity, 'amount': amount}
            total_value += amount

        signals = []
        for ticker in universe:
            current_data = current_distribution[ticker]
            current_weight = (current_data['amount'] / total_value * 100) if total_value > 0 else 0.0
            weight_diff = current_weight - target_weight[ticker]

            if weight_diff > band_pct:
                action = "SELL"
                needs_rebalance = True
                rebalance_amount = current_data['amount'] - (total_value * target_weight[ticker] / 100)
            elif weight_diff < -band_pct:
                action = "BUY"
                needs_rebalance = True
                rebalance_amount = (total_value * target_weight[ticker] / 100) - current_data['amount']
            else:
                action = "HOLD"
                needs_rebalance = False
                rebalance_amount = 0.0

            rebalance_quantity = abs(rebalance_amount / current_data['price']) if current_data['price'] > 0 else 0

            signals.append({
                'ticker': ticker,
                'account_type': '연금저축',
                'signal_date': signal_date,
                'target_weight': target_weight[ticker],
                'current_weight': current_weight,
                'weight_diff': weight_diff,
                'current_price': current_data['price'],
                'total_assets': total_value,
                'target_amount': total_value * target_weight[ticker] / 100,
                'current_amount': current_data['amount'],
                'rebalance_amount': rebalance_amount,
                'rebalance_quantity': rebalance_quantity,
                'action': action,
                'needs_rebalance': needs_rebalance,
            })

        return signals

    def save_rebalance_signals(self, signals: list):
        """리밸런싱 신호를 DB에 저장"""
        saved_count = 0

        for signal in signals:
            try:
                rebalance_record = RebalanceSignal(
                    ticker=signal['ticker'],
                    account_type=signal.get('account_type', 'IRP'),
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
