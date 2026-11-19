# -*- coding: utf-8 -*-
"""NAS API 서버 상태 확인"""

import sys
import os
from pathlib import Path

# Windows UTF-8 인코딩 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
import requests
from datetime import datetime

# .env와 .env.local 로드
load_dotenv('.env')
load_dotenv('.env.local', override=True)

NAS_IP = os.getenv("NAS_IP", "192.168.0.46")
NAS_API_PORT = os.getenv("NAS_API_PORT", "8000")

def check_nas_api():
    """NAS API 서버 상태 확인"""

    print("=" * 60)
    print("NAS API SERVER STATUS CHECK")
    print("=" * 60)

    api_url = f"http://{NAS_IP}:{NAS_API_PORT}"

    urls_to_check = [
        ("/health", "GET", "Health Check"),
        ("/api/v1/etfs", "GET", "ETF List"),
        ("/api/v1/momentum/latest", "GET", "Latest Momentum"),
        ("/api/v1/portfolio", "GET", "Portfolio"),
        ("/api/v1/signals/accuracy/stats", "GET", "Signal Accuracy Stats"),
    ]

    print(f"\nTarget: {api_url}\n")

    for endpoint, method, description in urls_to_check:
        full_url = api_url + endpoint
        print(f"[{description}]")
        print(f"  {method} {endpoint}")

        try:
            if method == "GET":
                response = requests.get(full_url, timeout=5)
            else:
                response = requests.post(full_url, timeout=5)

            if response.status_code == 200:
                print(f"  ✅ Status: 200 OK")
                try:
                    data = response.json()
                    # 응답 프리뷰 (최대 3줄)
                    import json
                    preview = json.dumps(data, ensure_ascii=False)[:100]
                    print(f"  Response preview: {preview}...")
                except:
                    pass
            else:
                print(f"  ⚠️  Status: {response.status_code}")

        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout (5s)")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection failed")
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

        print()

    print("=" * 60)
    print("STATUS CHECK COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    check_nas_api()
