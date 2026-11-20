# -*- coding: utf-8 -*-
"""ReBalancer - 알림 관리"""

import logging
import requests
from datetime import datetime
from sqlalchemy.orm import Session
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PENSION_ETFS, IRP_PORTFOLIO, BASE_URL
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

    @staticmethod
    def _sign_emoji(value: float) -> str:
        """국내 증시 관행(상승=빨강/하락=파랑)을 텔레그램 색상 미지원 환경에서 이모지로 대체."""
        if value > 0:
            return "🔴"
        if value < 0:
            return "🔵"
        return ""

    def send_price_alert(self, date_str: str, accounts: list) -> bool:
        """일일 종가 알림 - 계좌별 관리종목 시세/등락률, 보유종목은 굵게+평가금액(전일대비 증감액) 병기,
        계좌 합계도 굵게+전일대비 증감액/수익률 표시.

        accounts: [{"label": "연금저축", "items": [{"ticker", "name", "price",
                    "change_pct"(Optional), "held"(bool), "current_value"(Optional),
                    "value_change"(Optional)}], "total_value", "prev_total_value"(Optional)}, ...]
        """
        title = "Daily ETF Prices"
        blocks = []

        for acc in accounts:
            lines = [f"*<{acc['label']}>*", ""]
            for item in acc['items']:
                mark = "▶ " if item['held'] else "  "
                name = f"*{item['name']}*" if item['held'] else item['name']
                if not item['held']:
                    name += " (미보유)"

                change_pct = item.get('change_pct')
                if change_pct is None:
                    change_str = "—"
                else:
                    change_str = f"{self._sign_emoji(change_pct)}{change_pct:+.1f}%"

                lines.append(mark + name)
                lines.append(f"    • {item['price']:,.0f}원  ({change_str})")

                if item['held']:
                    value_change = item.get('value_change')
                    change_val_str = (
                        f"  ({self._sign_emoji(value_change)}{value_change:+,.0f}원)"
                        if value_change is not None else ""
                    )
                    lines.append(f"    • 평가 {item['current_value']:,.0f}원{change_val_str}")

                lines.append("")

            total_value = acc['total_value']
            prev_total_value = acc.get('prev_total_value')
            if prev_total_value:
                diff = total_value - prev_total_value
                diff_pct = diff / prev_total_value * 100
                lines.append(
                    f"*계* {total_value:,.0f}원 "
                    f"({self._sign_emoji(diff)}{diff:+,.0f}원 {diff_pct:+.2f}%)"
                )
            else:
                lines.append(f"*계* {total_value:,.0f}원")

            blocks.append("\n".join(lines))

        body = "\n\n".join(blocks)
        message = f"Date: {date_str}\n\n{body}\n\n상세: {BASE_URL}/report/view"

        return self.send_telegram_message(title, message, "price_alert")

    def send_momentum_alert(self, all_scores: list, selected_tickers: list, calc_date, price_basis: str = "raw") -> bool:
        """모멘텀 알림 (종목별 리스트 + 전체 상세 링크)

        모바일 텔레그램 코드블록은 고정폭 폰트가 아니고 화면 폭에서 줄바꿈되어
        열 정렬이 깨지므로, 표 대신 종목당 한 줄(이름) + 한 줄(가격/점수) 형식을 쓴다.
        """
        title = "Monthly Momentum Update"
        selected_set = set(selected_tickers)

        blocks = []
        for s in all_scores:
            full_name = PENSION_ETFS.get(s['ticker'], {}).get('name', s['ticker'])
            mark = "▶ " if s['ticker'] in selected_set else "　 "
            blocks.append(
                f"{mark}{full_name}\n"
                f"    {s['current_price']:,.0f}원 · {s['weighted_score']:.1f}점"
            )

        body = "\n\n".join(blocks)

        # 가격은 실제 종가, 점수는 price_basis에 따라 분배금 포함(수정주가) 또는 제외(종가) 기준
        basis_label = "분배금 포함(수정주가)" if price_basis == "adjusted" else "분배금 제외(종가)"

        message = (
            f"Date: {calc_date}\n\n{body}\n\n"
            f"▶ = 선정된 TOP {len(selected_tickers)} 종목\n"
            f"점수 기준: {basis_label}\n\n"
            f"전체 상세: {BASE_URL}/momentum/view"
        )

        return self.send_telegram_message(title, message, "momentum_alert")

    def send_rebalance_alert(self, needs_rebalance: bool, signal_date, signals: list, label: str = "IRP") -> bool:
        """리밸런싱 알림 - 구체적 거래 지시 포함

        신호에 ticker, action(BUY/SELL/HOLD), rebalance_quantity를 포함하고
        사람이 읽을 수 있는 형식으로 변환: "KODEX 미국S&P500 100주 매도"
        """
        if needs_rebalance:
            title = f"Action Required: {label} Rebalancing Needed"
        else:
            title = f"Rebalance Check Complete ({label}): No Action Needed"

        lines = [f"Date: {signal_date}"]

        if needs_rebalance and signals:
            lines.append("")
            for signal in signals:
                action = signal.get('action', 'HOLD')
                if action == 'HOLD':
                    continue

                ticker = signal.get('ticker', 'N/A')
                quantity = signal.get('rebalance_quantity', 0)
                price = signal.get('current_price', 0)

                # ETF 이름 조회
                etf_info = IRP_PORTFOLIO.get(ticker) or PENSION_ETFS.get(ticker, {})
                etf_name = etf_info.get('name', ticker)

                # 액션 한글화
                action_kr = "매도" if action == "SELL" else "매수" if action == "BUY" else "유지"

                lines.append(f"• {etf_name}: {quantity:,.0f}주 {action_kr} (@{price:,.0f}원)")
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
