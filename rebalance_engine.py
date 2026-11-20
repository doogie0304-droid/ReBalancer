# -*- coding: utf-8 -*-
"""ReBalancer - 리밸런싱 엔진 (고정 배분 계좌: IRP, 연금저축)"""

import logging
import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
from config import REBALANCE_BAND_PCT, IRP_PORTFOLIO, PENSION_REBALANCE_BAND_PCT
from database import ETFPrice, MomentumScore, RebalanceSignal, UserPortfolio

logger = logging.getLogger(__name__)

CASH_TICKER = "CASH"  # UserPortfolio에서 현금은 이 티커, quantity = 원화 금액

class RebalanceEngine:
    """리밸런싱 계산"""

    def __init__(self, db: Session):
        self.db = db
        self.total_assets = 0.0  # calculate_fixed_rebalance_signal()이 실제 보유액으로 채움

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

    def calculate_fixed_rebalance_signal(self, signal_date, account_type: str, portfolio: dict,
                                         band_pct: float = REBALANCE_BAND_PCT):
        """계좌별 고정 목표비중 리밸런싱 신호 계산

        - 대상: 목표표 순서대로, 그 뒤에 목표표 밖 보유 종목(목표 0%, 티커 정렬)
        - weight_diff > band_pct: SELL / weight_diff < -band_pct: BUY / 그 외: HOLD
        - 보유 합계가 0이면 전부 HOLD (0으로 나누지 않는다)
        - 시세가 없는 종목은 평가액 0, 수량 0
        - "CASH"는 1원으로 평가해 총자산에 넣고, 그 줄은 항상 HOLD (매매 대상 아님)
        - 수량은 정수: 매수는 내림, 매도는 올림(보유 수량 한도). 1주 미만 매수는 HOLD로 낮춘다.
        """
        holdings = {
            h.ticker: h for h in self.db.query(UserPortfolio).filter(
                UserPortfolio.account_type == account_type,
                UserPortfolio.is_active == True
            ).all()
        }

        tickers = list(portfolio.keys()) + sorted(t for t in holdings if t not in portfolio)

        distribution = {}
        total_value = 0.0
        for ticker in tickers:
            if ticker == CASH_TICKER:
                price = 1.0  # 현금은 수량이 곧 원화 금액 (ETFPrice 행 없음)
            else:
                price_info = self.get_latest_price(ticker)
                price = price_info['price'] if price_info else 0.0
            holding = holdings.get(ticker)
            quantity = holding.quantity if holding else 0.0
            amount = quantity * price
            distribution[ticker] = {'price': price, 'amount': amount, 'quantity': quantity}
            total_value += amount

        self.total_assets = total_value

        signals = []
        for ticker in tickers:
            data = distribution[ticker]
            target_weight = portfolio[ticker]['target_weight'] if ticker in portfolio else 0.0
            current_weight = (data['amount'] / total_value * 100) if total_value > 0 else 0.0
            weight_diff = current_weight - target_weight
            target_amount = total_value * target_weight / 100

            if total_value <= 0 or ticker == CASH_TICKER:
                action, needs_rebalance, rebalance_amount = "HOLD", False, 0.0
            elif weight_diff > band_pct:
                action, needs_rebalance = "SELL", True
                rebalance_amount = data['amount'] - target_amount
            elif weight_diff < -band_pct:
                action, needs_rebalance = "BUY", True
                rebalance_amount = target_amount - data['amount']
            else:
                action, needs_rebalance, rebalance_amount = "HOLD", False, 0.0

            rebalance_quantity = 0.0
            if action != "HOLD" and data['price'] > 0:
                if action == "BUY":
                    rebalance_quantity = float(math.floor(rebalance_amount / data['price']))
                elif target_weight <= 0:
                    rebalance_quantity = data['quantity']  # 목표 0%: 전량 매도
                else:
                    rebalance_quantity = float(min(
                        math.ceil(rebalance_amount / data['price']), data['quantity']))
            if action == "BUY" and rebalance_quantity <= 0:
                action, needs_rebalance = "HOLD", False  # 1주도 못 사는 금액이면 신호를 내지 않는다

            signals.append({
                'ticker': ticker,
                'account_type': account_type,
                'signal_date': signal_date,
                'target_weight': target_weight,
                'current_weight': current_weight,
                'weight_diff': weight_diff,
                'current_price': data['price'],
                'total_assets': total_value,
                'target_amount': target_amount,
                'current_amount': data['amount'],
                'rebalance_amount': rebalance_amount,
                'rebalance_quantity': rebalance_quantity,
                'action': action,
                'needs_rebalance': needs_rebalance,
            })

        return signals

    def calculate_rebalance_signal(self, signal_date):
        """IRP 고정 비중 리밸런싱 신호 (계좌 일반형 계산의 IRP 래퍼)"""
        return self.calculate_fixed_rebalance_signal(signal_date, "IRP", IRP_PORTFOLIO)

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
