# -*- coding: utf-8 -*-
"""ReBalancer - 알림 관리"""

import logging
from sqlalchemy.orm import Session
from config import NOTIFICATION_CHANNELS

logger = logging.getLogger(__name__)

class NotificationManager:
    """알림 관리자"""

    def __init__(self, db: Session):
        self.db = db

    def create_momentum_notification(self, selected_tickers: list, calc_date):
        """모멘텀 알림"""
        title = f"[모멘텀] 월별 포트폴리오 업데이트"
        message = f"기준일: {calc_date}\n선정 종목: {', '.join(selected_tickers)}"
        logger.info(f"✅ 알림 생성: {title}")

    def create_rebalance_notification(self, needs_rebalance: bool, signal_date):
        """리밸런싱 알림"""
        title = "⚠️  [리밸런싱]" if needs_rebalance else "✅ [리밸런싱]"
        logger.info(f"✅ 알림 생성: {title}")
