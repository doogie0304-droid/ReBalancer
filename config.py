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
# 모멘텀 점수를 분배금이 재투자된 수정주가(야후)로 계산한다. 조회·검증에 실패하면 그 달은
# DB 종가로 계산하고 텔레그램으로 알린다. False면 항상 DB 종가(분배금 제외)로 계산한다.
MOMENTUM_USE_ADJUSTED_PRICES = True

# IRP 리밸런싱 파라미터 (확정)
REBALANCE_BAND_PCT = 5.0
REBALANCE_CHECK_DATES = [("01", "01"), ("07", "01")]
REBALANCE_CHECK_HOUR = 9

# 연저펀 Top2 밴드형 재조정 파라미터 (Top2 각 50% 목표, +/-5%p 이탈 시 신호)
PENSION_REBALANCE_BAND_PCT = 5.0

# 크롤링 파라미터
CRAWL_SCHEDULE_HOUR = 18
CRAWL_RETRY_COUNT = 3
CRAWL_RETRY_DELAY = 5

# 스케줄 설정
# 모멘텀 계산: 매월 1일 09:00, 단 휴장일이면 다음 영업일로 순연 (scheduler.py의 _job_calculate_momentum에서 매일 체크)
MOMENTUM_SCHEDULE_HOUR = 9

# 알림 설정
NOTIFICATION_CHANNELS = ["console", "telegram", "webhook"]
BASE_URL = os.getenv("BASE_URL", "http://192.168.0.46:8001")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 웹훅 알림 (범용 자동화 연동용 - n8n/Zapier 등). URL 미설정 시 전송 자체를 스킵함
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10"))

# 외부 노출 뷰 서버(8001)의 포트폴리오 편집 폼 인증 (momentum_view_server.py)
# PIN 입력 후 서명된 쿠키로 30일간 로그인 유지 (매번 재입력 불필요)
PORTFOLIO_EDIT_PIN = os.getenv("PORTFOLIO_EDIT_PIN", "")
PORTFOLIO_SESSION_SECRET = os.getenv("PORTFOLIO_SESSION_SECRET", "")

# 공공데이터포털 - 한국천문연구원 특일 정보 API (휴장일 캘린더 자동 점검용)
HOLIDAY_API_KEY = os.getenv("HOLIDAY_API_KEY", "")
# 발급일 2026-07-08, 유효기간 24개월 -> 갱신은 만료일(2028-07-08) 이전에 할 것
# 키 갱신 시 이 날짜도 함께 업데이트
HOLIDAY_API_KEY_EXPIRES = "2028-07-08"

# 모멘텀 유니버스 (PENSION_STRATEGY == "momentum"일 때만 신호 계산에 쓴다)
# 모멘텀을 다시 켜도 이력이 끊기지 않도록 시세 수집은 계속한다.
# 현재 연금저축 전략은 PENSION_STRATEGY를 따른다.
PENSION_ETFS = {
    "379800": {"name": "KODEX 미국S&P500", "type": "foreign_stock"},
    "379810": {"name": "KODEX 미국나스닥100", "type": "foreign_stock"},
    "402970": {"name": "ACE 미국배당다우존스", "type": "foreign_stock"},
    "449170": {"name": "TIGER KOFR금리액티브(합성)", "type": "safe_asset"},
    "CASH": {"name": "현금", "type": "cash"},
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
    "CASH": {"name": "현금", "target_weight": 0.0},
}

# 연금 전략: "fixed"면 연금저축도 IRP와 같은 고정 목표표를 쓴다 ("momentum"이면 연금저축은 Top2 모멘텀)
PENSION_STRATEGY = "fixed"
# 목표표는 하나만 둔다 (IRP_PORTFOLIO와 같은 객체)
PENSION_PORTFOLIO = IRP_PORTFOLIO


def fixed_allocation_accounts() -> dict:
    """고정 배분을 적용할 계좌 -> 목표표. 호출 시점의 PENSION_STRATEGY를 읽는다."""
    accounts = {}
    if PENSION_STRATEGY == "fixed":
        accounts["연금저축"] = PENSION_PORTFOLIO
    accounts["IRP"] = IRP_PORTFOLIO
    return accounts

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

# 한국 증시 휴장일 (설날/추석 등 음력 공휴일이 매년 바뀌므로 연초에 갱신 필요)
MARKET_HOLIDAYS = [
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
    "2024-03-01", "2024-04-10", "2024-05-05", "2024-05-15", "2024-06-06",
    "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-03",
    "2024-10-09", "2024-12-25",
    "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03",
    "2025-05-01", "2025-05-05", "2025-05-06", "2025-06-06", "2025-08-15",
    "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09",
    "2025-12-25", "2025-12-31",
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-25", "2026-06-06", "2026-07-17",
    "2026-08-15", "2026-08-17", "2026-09-24", "2026-09-25", "2026-09-26",
    "2026-10-03", "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
    # 제헌절(7/17)은 2026-02-10 공포, 2026-05-11 시행된 개정으로 19년 만에
    # 법정 공휴일로 재지정됨 (2027년 이후도 매년 7/17 추가 필요)
    # 2027 상반기 (공공데이터포털 특일정보 API로 확인, 2026-07-08)
    "2027-01-01", "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",
    "2027-03-01", "2027-05-01", "2027-05-03", "2027-05-05", "2027-05-13",
    "2027-06-06",
]
