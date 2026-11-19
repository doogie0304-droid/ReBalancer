# -*- coding: utf-8 -*-
"""ReBalancer - 네이버 ETF 시세 크롤러"""

import json
import requests
import logging
import time
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from config import PENSION_ETFS, IRP_PORTFOLIO, CRAWL_RETRY_COUNT, CRAWL_RETRY_DELAY
from database import ETFPrice

logger = logging.getLogger(__name__)

class NaverETFCrawler:
    """네이버 ETF 시세 크롤러"""

    # 2026-09 네이버가 finance.naver.com/item/sise_day.naver 페이지를 폐지(410)해
    # Npay 증권(m.stock.naver.com) JSON API로 교체. 수정주가가 아닌 실제 종가를 반환한다.
    BASE_URL = "https://m.stock.naver.com/api/stock/{ticker}/price"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    def fetch_page(self, ticker: str, page: int = 1, page_size: int = 10) -> Optional[str]:
        """네이버 일별 시세 API 호출

        Args:
            ticker: ETF 티커 코드
            page: 페이지 번호 (기본값: 1, 최신순)
            page_size: 페이지당 거래일 수 (기본값: 10, 최대 60)

        Returns:
            JSON 문자열 또는 None (실패 시)
        """
        for attempt in range(CRAWL_RETRY_COUNT):
            try:
                response = requests.get(
                    self.BASE_URL.format(ticker=ticker),
                    params={'pageSize': page_size, 'page': page},
                    headers=self.HEADERS,
                    timeout=10
                )
                response.raise_for_status()
                return response.text

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"페이지 다운로드 실패 ({ticker}, 시도 {attempt+1}/{CRAWL_RETRY_COUNT}): {e}"
                )
                if attempt < CRAWL_RETRY_COUNT - 1:
                    time.sleep(CRAWL_RETRY_DELAY)

        logger.error(f"Failed to fetch {ticker} after {CRAWL_RETRY_COUNT} retries")
        return None

    def parse_price_data(self, body: Optional[str]) -> List[Tuple[str, float]]:
        """일별 시세 API 응답(JSON)에서 시세 파싱

        Args:
            body: fetch_page가 반환한 JSON 문자열

        Returns:
            [(날짜 "YYYY-MM-DD", 종가), ...] 형태의 리스트
        """
        if not body:
            logger.warning("Price response is None or empty string")
            return []

        try:
            items = json.loads(body)
        except ValueError as e:
            logger.error(f"Price response is not valid JSON: {e}")
            return []

        if not isinstance(items, list):
            logger.warning(f"Unexpected price response shape: {type(items).__name__}")
            return []

        prices = []
        for idx, item in enumerate(items):
            try:
                date_str = item['localTradedAt'][:10]
                datetime.strptime(date_str, "%Y-%m-%d")
                price = float(str(item['closePrice']).replace(',', ''))
                if price <= 0:
                    continue
                prices.append((date_str, price))
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"Row {idx} parse error (skipped): {e}")
                continue

        return prices

    def save_prices_to_db(
        self, 
        db: Session, 
        ticker: str, 
        prices: List[Tuple[str, float]]
    ) -> int:
        """파싱된 시세를 데이터베이스에 저장
        
        Args:
            db: SQLAlchemy 세션
            ticker: ETF 티커 코드
            prices: [(날짜, 종가), ...] 리스트
            
        Returns:
            저장된 레코드 개수
        """
        saved_count = 0
        
        for date_str, close_price in prices:
            try:
                # 날짜 파싱 (예: "2024-01-15")
                price_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                
                # 중복 체크: 같은 ticker, price_date가 이미 있는지 확인
                existing = db.query(ETFPrice).filter(
                    ETFPrice.ticker == ticker,
                    ETFPrice.price_date == price_date
                ).first()
                
                if existing:
                    # 기존 레코드는 업데이트 (또는 스킵)
                    existing.close_price = close_price
                    saved_count += 1
                else:
                    # 새 레코드 추가
                    record = ETFPrice(
                        ticker=ticker,
                        price_date=price_date,
                        close_price=close_price
                    )
                    db.add(record)
                    saved_count += 1
                    
            except ValueError as e:
                logger.warning(f"날짜 파싱 실패 ({date_str}): {e}")
                continue
            except Exception as e:
                logger.error(f"DB 저장 오류 ({ticker}, {date_str}): {e}")
                continue
        
        # 트랜잭션 커밋
        try:
            db.commit()
            logger.info(f"Saved {saved_count} records for {ticker}")
        except Exception as e:
            db.rollback()
            logger.error(f"DB commit failed for {ticker}: {e}")
            saved_count = 0
        
        return saved_count

    def collect_all_prices(
        self, 
        db: Session, 
        tickers: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, int]:
        """모든 종목 시세 수집 및 저장
        
        Args:
            db: SQLAlchemy 세션
            tickers: 티커 딕셔너리 (None이면 설정 사용)
            
        Returns:
            {'success': int, 'fail': int, 'skip': int}
        """
        if tickers is None:
            tickers = PENSION_ETFS
        
        stats = {'success': 0, 'fail': 0, 'skip': 0}

        for ticker, ticker_info in tickers.items():
            ticker_name = ticker_info.get('name', ticker) if isinstance(ticker_info, dict) else ticker
            
            try:
                logger.info(f"Collecting: {ticker_name} ({ticker})")

                html = self.fetch_page(ticker)
                if html is None:
                    logger.warning(f"{ticker_name}: Page fetch failed")
                    stats['fail'] += 1
                    continue

                prices = self.parse_price_data(html)
                if not prices:
                    logger.warning(f"{ticker_name}: Price parsing failed")
                    stats['skip'] += 1
                    continue

                saved_count = self.save_prices_to_db(db, ticker, prices)
                if saved_count > 0:
                    stats['success'] += 1
                else:
                    stats['fail'] += 1

            except Exception as e:
                logger.error(f"Unexpected error collecting {ticker_name}: {type(e).__name__}: {e}")
                stats['fail'] += 1

        logger.info(
            f"Collection complete: Success={stats['success']}, Failed={stats['fail']}, Skipped={stats['skip']}"
        )
        return stats
