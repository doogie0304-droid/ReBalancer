# -*- coding: utf-8 -*-
"""ReBalancer - 설정 및 상수 정의"""
import os
from dotenv import load_dotenv

# .env.local 우선 로드 (비밀번호 관리)
load_dotenv('.env.local', override=True)
# 다음 .env 로드 (기본 설정)
load_dotenv('.env')

# API 설정
API_TITLE = "ReBalancer"
API_DESCRIPTION = "ETF 모멘텀 기반 자동 리밸런싱 시스템"
API_VERSION = "1.0.0"
API_PREFIX = "/api/v1"

DEBUG = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 데이터베이스
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "rebalancer")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "rebalance_db")
DB_SOCKET = os.getenv("DB_SOCKET", "")

# Unix 소켓이 있으면 사용, 없으면 TCP 연결
if DB_SOCKET:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}?unix_socket={DB_SOCKET}"
else:
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 모멘텀 파라미터 (확정)
MOMENTUM_WEIGHTS = {
    "R3": 0.20,   # 3개월
    "R6": 0.30,   # 6개월
    "R12": 0.50,  # 12개월
}

MOMENTUM_POSITIVE_THRESHOLD = 0.0
MA_PERIOD_MONTHS = 10
MOMENTUM_TOP_N = 2

# IRP 리밸런싱 파라미터 (확정)
REBALANCE_BAND_PCT = 5.0
REBALANCE_CHECK_DATES = [("01", "01"), ("07", "01")]
REBALANCE_CHECK_HOUR = 9

# 크롤링 파라미터
CRAWL_SCHEDULE_HOUR = 18
CRAWL_RETRY_COUNT = 3
CRAWL_RETRY_DELAY = 5

# 스케줄 설정
MOMENTUM_SCHEDULE_MONTH_DAY = 2
MOMENTUM_SCHEDULE_HOUR = 9

# 알림 설정
NOTIFICATION_CHANNELS = ["console", "telegram"]
FCM_API_KEY = os.getenv("FCM_API_KEY", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 관리 종목 (연금저축펀드)
PENSION_ETFS = {
    "379800": {"name": "KODEX 200", "type": "domestic_stock"},
    "360750": {"name": "TIGER 미국S&P500", "type": "foreign_stock"},
    "402970": {"name": "ACE 미국배당다우존스", "type": "foreign_stock"},
    "449170": {"name": "TIGER KOFR금리액티브(합성)", "type": "safe_asset"},
}

# IRP 포트폴리오 (고정비중)
# 수정: "072r0" → "0072R0" (선행 0 추가, 소문자 r → 대문자 R)
# 확인자: 김동건
IRP_PORTFOLIO = {
    "360750": {"name": "TIGER 미국S&P500", "target_weight": 25.0},
    "379810": {"name": "KODEX 미국나스닥100", "target_weight": 15.0},
    "402970": {"name": "ACE 미국배당다우존스", "target_weight": 15.0},
    "0072R0": {"name": "TIGER KRX금현물", "target_weight": 15.0},
    "453850": {"name": "ACE 미국30년국채액티브(H)", "target_weight": 15.0},
    "214980": {"name": "KODEX 단기채권PLUS", "target_weight": 15.0},
}

# 로깅 설정
TIMEZONE = "Asia/Seoul"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 네이버 크롤러
NAVER_CRAWLER_SELECTORS = {
    "table": "table.type2",
    "row": "tr",
    "skip_rows": 2,  # 헤더(행1) + 빈행(행2) 제외
    "date": "td:nth-child(1)",
    "close_price": "td:nth-child(2)",
}

# 시장 정보
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 16

# 한국 증시 휴장일
MARKET_HOLIDAYS = [
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
    "2024-03-01", "2024-04-10", "2024-05-05", "2024-05-15", "2024-06-06",
    "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-03",
    "2024-10-09", "2024-12-25",
]
