# -*- coding: utf-8 -*-
"""텔레그람 연동 테스트"""

import sys
import os
from pathlib import Path

# 프로젝트 디렉토리 추가
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Windows UTF-8 인코딩 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import requests
from datetime import datetime

def test_telegram():
    """텔레그람 봇 연동 테스트"""

    print("=" * 50)
    print("TELEGRAM CONNECTIVITY TEST")
    print("=" * 50)

    # 설정 확인
    print(f"\nBot Token: {TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"Chat ID: {TELEGRAM_CHAT_ID}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\nERROR: Telegram configuration not found. Check .env file.")
        return False

    # API 호출
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    test_message = f"""*ReBalancer Telegram Integration Test*

Status: CONNECTED

Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Project: ReBalancer Phase 2"""

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": test_message,
        "parse_mode": "Markdown"
    }

    try:
        print(f"\nSending test message...")
        response = requests.post(api_url, json=payload, timeout=10)

        if response.status_code == 200:
            print("SUCCESS: Message sent!")
            print(f"\nResponse: {response.json()}")
            return True
        else:
            print(f"FAILED: {response.status_code}")
            print(f"Error: {response.text}")
            return False

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_telegram()
    sys.exit(0 if success else 1)
