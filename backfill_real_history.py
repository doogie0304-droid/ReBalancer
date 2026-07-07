# -*- coding: utf-8 -*-
"""네이버 금융 페이지네이션으로 실제 1년치 시세를 백필 (합성 데이터 대체용)"""

import time
import logging
from datetime import date, timedelta

from database import SessionLocal, ETFPrice
from crawler import NaverETFCrawler
from config import PENSION_ETFS, IRP_PORTFOLIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 페이지당 약 10거래일 -> 30페이지 ~= 300거래일(약 14개월), R12(240일) 여유 확보
MAX_PAGES = 30
TARGET_START = date.today() - timedelta(days=380)


def backfill_ticker(crawler: NaverETFCrawler, db, ticker: str) -> int:
    total_saved = 0
    oldest_seen = date.today()

    for page in range(1, MAX_PAGES + 1):
        html = crawler.fetch_page(ticker, page=page)
        if html is None:
            logger.warning(f"{ticker}: page {page} fetch failed, stopping")
            break

        prices = crawler.parse_price_data(html)
        if not prices:
            logger.info(f"{ticker}: page {page} returned no rows, stopping")
            break

        saved = crawler.save_prices_to_db(db, ticker, prices)
        total_saved += saved

        page_dates = [p[0] for p in prices if p[0]]
        if page_dates:
            oldest_on_page = min(page_dates)
            oldest_seen = date.fromisoformat(oldest_on_page)

        logger.info(f"{ticker}: page {page} -> {len(prices)} rows (oldest so far: {oldest_seen})")

        if oldest_seen <= TARGET_START:
            logger.info(f"{ticker}: reached target start date, stopping")
            break

        time.sleep(0.5)  # 네이버 요청 간격

    return total_saved


def main():
    required_tickers = sorted(set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys()))
    crawler = NaverETFCrawler()
    db = SessionLocal()

    try:
        logger.info(f"=== Wiping existing (synthetic) data for {len(required_tickers)} tickers ===")
        deleted = db.query(ETFPrice).filter(ETFPrice.ticker.in_(required_tickers)).delete(synchronize_session=False)
        db.commit()
        logger.info(f"Deleted {deleted} existing rows")

        logger.info("=== Backfilling real historical data from Naver ===")
        for ticker in required_tickers:
            name = PENSION_ETFS.get(ticker, IRP_PORTFOLIO.get(ticker, {})).get("name", ticker)
            logger.info(f"--- {ticker} ({name}) ---")
            saved = backfill_ticker(crawler, db, ticker)
            logger.info(f"{ticker}: total saved {saved}")

        logger.info("=== Final data range ===")
        from sqlalchemy import func
        for ticker in required_tickers:
            result = db.query(
                func.min(ETFPrice.price_date),
                func.max(ETFPrice.price_date),
                func.count(ETFPrice.id),
            ).filter(ETFPrice.ticker == ticker).first()
            if result[0]:
                logger.info(f"{ticker}: {result[2]} records, {result[0]} ~ {result[1]}")
            else:
                logger.warning(f"{ticker}: NO DATA (crawl failed)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
