# -*- coding: utf-8 -*-
"""ReBalancer - 신호 신뢰도 평가 엔진"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import SignalAccuracy, ETFPrice, MomentumScore
from portfolio_engine import PortfolioEngine

logger = logging.getLogger(__name__)

class SignalAccuracyEngine:
    """신호 신뢰도 평가 엔진 (Method 1: 간단한 정확도 추적)"""

    def __init__(self, db: Session):
        self.db = db
        self.portfolio_engine = PortfolioEngine(db)

    def record_momentum_signal(self, ticker: str, momentum_score: dict,
                               signal_date: str) -> dict:
        """모멘텀 신호 기록"""

        # 신호 방향 결정 (모멘텀 스코어 기반)
        weighted_score = momentum_score.get('weighted_score', 0)
        signal_direction = "BUY" if weighted_score > 0 else "HOLD"
        signal_confidence = min(abs(weighted_score) / 100, 1.0)  # 0~1 범위로 정규화

        # 현재 가격 조회
        current_price = self.portfolio_engine.get_latest_price(ticker)

        # 신호 ID 생성
        signal_id = f"MOM_{ticker}_{signal_date}"

        # 신호 기록 생성
        signal = SignalAccuracy(
            signal_id=signal_id,
            signal_type="momentum",
            signal_date=datetime.strptime(signal_date, "%Y-%m-%d").date() if isinstance(signal_date, str) else signal_date,
            ticker=ticker,
            signal_direction=signal_direction,
            signal_confidence=signal_confidence,
            price_at_signal=current_price,
            created_at=datetime.now()
        )

        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)

        logger.info(f"Momentum signal recorded: {signal_id} - {signal_direction} (confidence: {signal_confidence:.2f})")

        return {
            "signal_id": signal_id,
            "signal_type": "momentum",
            "ticker": ticker,
            "direction": signal_direction,
            "confidence": signal_confidence,
            "price": current_price,
        }

    def record_rebalance_signal(self, ticker: str, action: str,
                                signal_date: str, current_price: float) -> dict:
        """리밸런싱 신호 기록"""

        # 신호 방향 매핑
        signal_direction = action  # BUY, SELL, HOLD
        signal_confidence = 0.8  # 리밸런싱은 고정 신뢰도

        # 신호 ID 생성
        signal_id = f"REB_{ticker}_{signal_date}"

        # 신호 기록 생성
        signal = SignalAccuracy(
            signal_id=signal_id,
            signal_type="rebalance",
            signal_date=datetime.strptime(signal_date, "%Y-%m-%d").date() if isinstance(signal_date, str) else signal_date,
            ticker=ticker,
            signal_direction=signal_direction,
            signal_confidence=signal_confidence,
            price_at_signal=current_price,
            created_at=datetime.now()
        )

        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)

        logger.info(f"Rebalance signal recorded: {signal_id} - {signal_direction} (confidence: {signal_confidence:.2f})")

        return {
            "signal_id": signal_id,
            "signal_type": "rebalance",
            "ticker": ticker,
            "direction": signal_direction,
            "confidence": signal_confidence,
            "price": current_price,
        }

    def evaluate_signal(self, signal_id: str) -> dict:
        """신호 평가 (신호 발송 후 30일 뒤)"""

        # 신호 조회
        signal = self.db.query(SignalAccuracy).filter(
            SignalAccuracy.signal_id == signal_id
        ).first()

        if not signal:
            logger.warning(f"Signal not found: {signal_id}")
            return {"error": "Signal not found"}

        if signal.evaluation_date:
            logger.warning(f"Signal already evaluated: {signal_id}")
            return {"error": "Signal already evaluated"}

        # 30일 뒤 가격 조회
        evaluation_date = signal.signal_date + timedelta(days=30)

        price_at_eval = self.db.query(ETFPrice).filter(
            ETFPrice.ticker == signal.ticker,
            ETFPrice.price_date >= evaluation_date
        ).order_by(ETFPrice.price_date.asc()).first()

        if not price_at_eval:
            logger.warning(f"Price data not available for evaluation: {signal.ticker} on {evaluation_date}")
            return {"error": "Price data not available"}

        # 수익률 계산
        actual_return_pct = (
            (price_at_eval.close_price - signal.price_at_signal) / signal.price_at_signal * 100
        )

        # 신호 정확도 판정
        signal_correct = False
        if signal.signal_direction == "BUY" and actual_return_pct > 0:
            signal_correct = True
        elif signal.signal_direction == "SELL" and actual_return_pct < 0:
            signal_correct = True
        elif signal.signal_direction == "HOLD":
            signal_correct = abs(actual_return_pct) < 5.0

        # 정확도 점수 계산
        if signal_correct:
            accuracy_score = signal.signal_confidence * (1 + min(abs(actual_return_pct) / 100, 1.0))
            accuracy_score = min(accuracy_score, 1.0)
        else:
            accuracy_score = signal.signal_confidence * 0.5

        # 신호 업데이트
        signal.evaluation_date = evaluation_date
        signal.price_at_evaluation = price_at_eval.close_price
        signal.actual_return_pct = actual_return_pct
        signal.signal_correct = signal_correct
        signal.accuracy_score = accuracy_score
        signal.updated_at = datetime.now()

        self.db.commit()
        self.db.refresh(signal)

        logger.info(f"Signal evaluated: {signal_id} - Correct: {signal_correct}, Accuracy: {accuracy_score:.2f}")

        return {
            "signal_id": signal_id,
            "signal_date": signal.signal_date.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "price_at_signal": signal.price_at_signal,
            "price_at_evaluation": price_at_eval.close_price,
            "actual_return_pct": actual_return_pct,
            "signal_correct": signal_correct,
            "accuracy_score": accuracy_score,
        }

    def get_accuracy_stats(self, signal_type: str = None, limit_days: int = 90) -> dict:
        """신뢰도 통계 조회"""

        # 기간 필터링
        from_date = (datetime.now() - timedelta(days=limit_days)).date()

        # 쿼리 빌드
        query = self.db.query(SignalAccuracy).filter(
            SignalAccuracy.evaluation_date >= from_date,
            SignalAccuracy.signal_correct.isnot(None)
        )

        if signal_type:
            query = query.filter(SignalAccuracy.signal_type == signal_type)

        evaluated_signals = query.all()

        if not evaluated_signals:
            return {
                "total_signals": 0,
                "evaluated_signals": 0,
                "accuracy_rate": 0.0,
                "avg_accuracy_score": 0.0,
                "by_type": {}
            }

        # 통계 계산
        total_correct = sum(1 for s in evaluated_signals if s.signal_correct)
        accuracy_rate = total_correct / len(evaluated_signals) * 100
        avg_accuracy_score = sum(s.accuracy_score for s in evaluated_signals) / len(evaluated_signals)

        # 신호 타입별 통계
        by_type = {}
        for sig_type in ["momentum", "rebalance"]:
            type_signals = [s for s in evaluated_signals if s.signal_type == sig_type]
            if type_signals:
                type_correct = sum(1 for s in type_signals if s.signal_correct)
                by_type[sig_type] = {
                    "total": len(type_signals),
                    "correct": type_correct,
                    "accuracy_rate": type_correct / len(type_signals) * 100,
                    "avg_score": sum(s.accuracy_score for s in type_signals) / len(type_signals)
                }

        return {
            "total_signals": len(evaluated_signals),
            "evaluated_signals": len(evaluated_signals),
            "accuracy_rate": round(accuracy_rate, 2),
            "avg_accuracy_score": round(avg_accuracy_score, 3),
            "by_type": by_type,
            "period_days": limit_days,
        }

    def get_pending_evaluations(self) -> list:
        """평가 대기 중인 신호 조회 (발송 후 30일 이상 경과)"""

        cutoff_date = (datetime.now() - timedelta(days=30)).date()

        pending_signals = self.db.query(SignalAccuracy).filter(
            SignalAccuracy.evaluation_date.is_(None),
            SignalAccuracy.signal_date <= cutoff_date
        ).all()

        return [
            {
                "signal_id": s.signal_id,
                "signal_type": s.signal_type,
                "ticker": s.ticker,
                "signal_date": s.signal_date.isoformat(),
                "days_elapsed": (datetime.now().date() - s.signal_date).days,
            }
            for s in pending_signals
        ]
