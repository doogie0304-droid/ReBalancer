# -*- coding: utf-8 -*-
"""텔레그램 명령어 봇 - /portfolio, /momentum 명령으로 웹 폼 링크 안내

기존 notification.py는 발송 전용(sendMessage만 호출)이라 사용자가 보낸
명령어에 반응할 수 없음. 이 스크립트는 별도 프로세스로 getUpdates 롱폴링을
돌며 등록된 chat_id에서 온 명령어에만 응답한다 (그 외 chat_id는 무시).
"""
import logging
import time
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BASE_URL, LOG_LEVEL

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

COMMANDS = {
    "/portfolio": lambda: f"포트폴리오 관리 (로그인 필요):\n{BASE_URL}/portfolio/edit",
    "/momentum": lambda: f"모멘텀 상세:\n{BASE_URL}/momentum/view",
    "/report": lambda: f"성과 리포트 (로그인 필요):\n{BASE_URL}/report/view",
    "/deposit": lambda: f"입금 기록 (로그인 필요):\n{BASE_URL}/report/deposit",
    "/start": lambda: "사용 가능한 명령어\n/portfolio - 포트폴리오 관리\n/momentum - 모멘텀 상세\n/report - 성과 리포트\n/deposit - 입금 기록",
    "/help": lambda: "사용 가능한 명령어\n/portfolio - 포트폴리오 관리\n/momentum - 모멘텀 상세\n/report - 성과 리포트\n/deposit - 입금 기록",
}


def send_message(text: str) -> None:
    try:
        resp = requests.post(
            f"{API_BASE}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


def handle_update(update: dict) -> None:
    message = update.get("message")
    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(TELEGRAM_CHAT_ID):
        logger.warning(f"Ignoring message from unauthorized chat_id: {chat_id}")
        return

    text = (message.get("text") or "").strip()
    command = text.split()[0] if text else ""
    handler = COMMANDS.get(command)
    if handler:
        send_message(handler())
    else:
        logger.info(f"Ignoring unrecognized text: {text!r}")


def poll_loop() -> None:
    offset = None
    logger.info("Telegram command bot started (long polling)")
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(f"{API_BASE}/getUpdates", params=params, timeout=35)
            resp.raise_for_status()
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                handle_update(update)
        except requests.exceptions.RequestException as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll_loop()
