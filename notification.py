# -*- coding: utf-8 -*-
"""ReBalancer - 알림 관리"""

import logging
import requests
from datetime import datetime
from sqlalchemy.orm import Session
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import NotificationHistory

logger = logging.getLogger(__name__)

class TelegramNotificationManager:
    """Telegram 알림 관리자"""

    def __init__(self, db: Session, bot_token: str = None, chat_id: str = None):
        self.db = db
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def _save_notification_history(self, notification_type: str, title: str, message: str,
                                   channel: str = "telegram", status: str = "pending",
                                   error_message: str = None, sent_at: datetime = None):
        """알림 히스토리 저장"""
        history = NotificationHistory(
            notification_type=notification_type,
            title=title,
            message=message,
            channel=channel,
            status=status,
            sent_at=sent_at or datetime.now(),
            error_message=error_message,
            created_at=datetime.now()
        )
        self.db.add(history)
        self.db.commit()
        return history

    def send_telegram_message(self, title: str, message: str, notification_type: str = "general") -> bool:
        """Telegram 메시지 발송"""
        if not self.api_url or not self.chat_id:
            logger.warning("Telegram bot token or chat ID not configured")
            return False

        try:
            full_message = f"*{title}*\n\n{message}"
            payload = {
                "chat_id": self.chat_id,
                "text": full_message,
                "parse_mode": "Markdown"
            }

            response = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=10)

            if response.status_code == 200:
                self._save_notification_history(
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    status="success",
                    sent_at=datetime.now()
                )
                logger.info(f"Telegram message sent: {title}")
                return True
            else:
                error_msg = response.text
                logger.error(f"Telegram send failed: {error_msg}")
                self._save_notification_history(
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    status="failed",
                    error_message=error_msg,
                    sent_at=datetime.now()
                )
                return False

        except Exception as e:
            logger.error(f"Telegram send error: {str(e)}")
            self._save_notification_history(
                notification_type=notification_type,
                title=title,
                message=message,
                status="failed",
                error_message=str(e),
                sent_at=datetime.now()
            )
            return False

    def send_price_alert(self, etf_data: dict) -> bool:
        """일일 종가 알림"""
        title = "Daily ETF Prices"
        lines = [f"Date: {etf_data.get('date', 'N/A')}"]
        for ticker, price in etf_data.get('prices', {}).items():
            lines.append(f"  {ticker}: {price:,.0f} KRW")
        message = "\n".join(lines)

        return self.send_telegram_message(title, message, "price_alert")

    def send_momentum_alert(self, selected_tickers: list, calc_date, momentum_data: dict) -> bool:
        """모멘텀 알림"""
        title = "Monthly Momentum Update"
        lines = [f"Date: {calc_date}", "Selected Top 2 ETFs:"]

        for ticker in selected_tickers:
            data = momentum_data.get(ticker, {})
            score = data.get('weighted_score', 0)
            lines.append(f"  {ticker}: Score {score:.2f}")

        message = "\n".join(lines)
        return self.send_telegram_message(title, message, "momentum_alert")

    def send_rebalance_alert(self, needs_rebalance: bool, signal_date, signals: list) -> bool:
        """리밸런싱 알림"""
        if needs_rebalance:
            title = "Action Required: Portfolio Rebalancing Needed"
        else:
            title = "Rebalance Check Complete: No Action Needed"

        lines = [f"Date: {signal_date}"]

        if needs_rebalance and signals:
            lines.append("Required Actions:")
            for signal in signals:
                ticker = signal.get('ticker', 'N/A')
                action = signal.get('action', 'HOLD')
                amount = signal.get('rebalance_amount', 0)
                lines.append(f"  {ticker}: {action} {amount:,.0f} KRW")
        else:
            lines.append("All positions are within rebalance bands.")

        message = "\n".join(lines)
        return self.send_telegram_message(title, message, "rebalance_alert")

    def send_portfolio_performance_alert(self, portfolio_summary: dict) -> bool:
        """포트폴리오 수익률 알림"""
        title = "Portfolio Performance Summary"
        total_value = portfolio_summary.get('total_value', 0)
        total_cost = portfolio_summary.get('total_cost', 0)
        total_return = portfolio_summary.get('total_return', 0)
        total_return_pct = portfolio_summary.get('total_return_pct', 0)

        lines = [
            f"Total Value: {total_value:,.0f} KRW",
            f"Total Cost: {total_cost:,.0f} KRW",
            f"Total Return: {total_return:,.0f} KRW ({total_return_pct:.2f}%)",
            "",
            "Individual Holdings:"
        ]

        for holding in portfolio_summary.get('holdings', []):
            ticker = holding.get('ticker', 'N/A')
            name = holding.get('name', '')
            current_value = holding.get('current_value', 0)
            return_pct = holding.get('return_pct', 0)
            lines.append(f"  {ticker} ({name}): {current_value:,.0f} KRW ({return_pct:+.2f}%)")

        message = "\n".join(lines)
        return self.send_telegram_message(title, message, "portfolio_performance")
