# -*- coding: utf-8 -*-
"""공공데이터포털 특일 정보 API로 향후 N개월 휴장일을 조회해 MARKET_HOLIDAYS와 대조

주의: 이 API는 관공서 공휴일(국경일/설날/추석/대체공휴일 등)만 반환한다.
근로자의 날(5/1), 증권시장 연말 임시휴장(12/31) 등 KRX 자체 휴장일은
이 API로 감지되지 않으므로 MARKET_HOLIDAYS에 수동으로 유지해야 한다.
"""

import logging
from datetime import date
import requests
from config import MARKET_HOLIDAYS, HOLIDAY_API_KEY

logger = logging.getLogger(__name__)

API_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"


def _fetch_month_holidays(year: int, month: int) -> list:
    """해당 연/월의 공휴일(대체공휴일 포함) 목록 조회 (YYYY-MM-DD 문자열 리스트)"""
    params = {
        "serviceKey": HOLIDAY_API_KEY,
        "solYear": str(year),
        "solMonth": f"{month:02d}",
        "numOfRows": "50",
        "_type": "json",
    }
    resp = requests.get(API_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    body = data.get("response", {}).get("body", {})
    if int(body.get("totalCount", 0)) == 0:
        return []

    items = body.get("items", {}).get("item", [])
    if isinstance(items, dict):  # 결과가 1건이면 dict로 옴
        items = [items]

    holidays = []
    for item in items:
        if item.get("isHoliday") == "Y":
            locdate = str(item["locdate"])  # YYYYMMDD
            holidays.append(f"{locdate[:4]}-{locdate[4:6]}-{locdate[6:]}")
    return holidays


def check_upcoming_holidays(months_ahead: int = 12) -> dict:
    """이번 달부터 향후 months_ahead개월간 API 기준 공휴일과 MARKET_HOLIDAYS를 비교

    반환: {"missing": [...], "checked_range": "YYYY-MM ~ YYYY-MM", "error": str|None}
    """
    if not HOLIDAY_API_KEY:
        return {"missing": [], "checked_range": "", "error": "HOLIDAY_API_KEY 미설정"}

    configured = set(MARKET_HOLIDAYS)
    api_holidays = set()
    today = date.today()

    months = []
    for i in range(months_ahead):
        mm = (today.month - 1 + i) % 12 + 1
        yy = today.year + (today.month - 1 + i) // 12
        months.append((yy, mm))

    try:
        for yy, mm in months:
            api_holidays |= set(_fetch_month_holidays(yy, mm))
    except Exception as e:
        logger.error(f"[HolidayCheck] API 조회 실패: {e}")
        return {"missing": [], "checked_range": "", "error": str(e)}

    missing = sorted(api_holidays - configured)
    start = f"{months[0][0]}-{months[0][1]:02d}"
    end = f"{months[-1][0]}-{months[-1][1]:02d}"

    return {"missing": missing, "checked_range": f"{start} ~ {end}", "error": None}
