# -*- coding: utf-8 -*-
"""ReBalancer - 웹훅 알림 (범용 자동화 연동용)

전송 계층만 담당한다. 페이로드(data dict) 조립은 호출부(scheduler.py)의 책임.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime

import requests
from pytz import timezone
from sqlalchemy.orm import Session

from config import WEBHOOK_URL, WEBHOOK_SECRET, WEBHOOK_TIMEOUT_SECONDS, TIMEZONE
from database import NotificationHistory

logger = logging.getLogger(__name__)
tz = timezone(TIMEZONE)


class WebhookNotifier:
    """웹훅 알림 관리자 - 단일 URL, 구조화 JSON 전송"""

    def __init__(self, db: Session, webhook_url: str = None, secret: str = None):
        self.db = db
        self.webhook_url = webhook_url or WEBHOOK_URL
        self.secret = secret or WEBHOOK_SECRET

    def _sign(self, body: bytes) -> str:
        """HMAC-SHA256 서명 (hex)"""
        return hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def _save_notification_history(self, notification_type: str, title: str, message: str,
                                    status: str = "pending", error_message: str = None):
        history = NotificationHistory(
            notification_type=notification_type,
            title=title,
            message=message,
            channel="webhook",
            status=status,
            sent_at=datetime.now(),
            error_message=error_message,
            created_at=datetime.now()
        )
        self.db.add(history)
        self.db.commit()
        return history

    def send_webhook(self, event_type: str, data: dict, notification_type: str = None) -> bool:
        """구조화 JSON 웹훅 전송. WEBHOOK_URL 미설정 시 스킵(에러 아님)."""
        if not self.webhook_url:
            return False

        notification_type = notification_type or event_type
        envelope = {
            "event_type": event_type,
            "timestamp": datetime.now(tz).isoformat(),
            "data": data,
        }
        body = json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_type,
        }
        if self.secret:
            headers["X-Webhook-Signature"] = f"sha256={self._sign(body)}"
        else:
            logger.warning("WEBHOOK_SECRET not configured - sending unsigned webhook")

        message = json.dumps(data, ensure_ascii=False, default=str)

        try:
            response = requests.post(
                self.webhook_url, data=body, headers=headers, timeout=WEBHOOK_TIMEOUT_SECONDS
            )
            if 200 <= response.status_code < 300:
                self._save_notification_history(notification_type, event_type, message, status="success")
                logger.info(f"Webhook sent: {event_type}")
                return True
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"Webhook send failed: {error_msg}")
                self._save_notification_history(
                    notification_type, event_type, message, status="failed", error_message=error_msg
                )
                return False
        except Exception as e:
            logger.error(f"Webhook send error: {str(e)}")
            self._save_notification_history(
                notification_type, event_type, message, status="failed", error_message=str(e)
            )
            return False
