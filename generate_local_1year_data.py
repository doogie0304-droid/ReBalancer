# -*- coding: utf-8 -*-
"""로컬 DB에 1년치 과거 시세 데이터 생성 (모멘텀 신호 검증용)"""

import random
import logging
from datetime import datetime, timedelta

from database import SessionLocal, ETFPrice
from config import PENSION_ETFS, IRP_PORTFOLIO, MARKET_HOLIDAYS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_PRICES = {
    "379800": 20000,
    "360750": 35000,
    "402970": 10000,
    "449170": 5000,
    "379810": 25000,
    "0072R0": 15000,
    "453850": 8000,
    "214980": 11000,
}

def main():
    db = SessionLocal()
    try:
        required_tickers = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())
        today = datetime.now().date()
        one_year_ago = today - timedelta(days=365)
        holidays = set(MARKET_HOLIDAYS)

        generated_count = 0
        for ticker in sorted(required_tickers):
            first_existing = (
                db.query(ETFPrice.price_date)
                .filter(ETFPrice.ticker == ticker)
                .order_by(ETFPrice.price_date.asc())
                .first()
            )
            first_date = first_existing[0] if first_existing else today
            end_date = first_date - timedelta(days=1)

            if one_year_ago >= end_date:
                logger.info(f"{ticker}: no gap to fill")
                continue

            logger.info(f"{ticker}: generating {one_year_ago} ~ {end_date}")

            base_price = BASE_PRICES.get(ticker, 10000)
            current_date = one_year_ago
            ticker_count = 0
            while current_date <= end_date:
                if current_date.weekday() < 5 and str(current_date) not in holidays:
                    change_pct = random.gauss(0.001, 0.02)
                    price = max(base_price * (1 + change_pct), base_price * 0.7)
                    price = round(price, 2)

                    db.add(ETFPrice(ticker=ticker, price_date=current_date, close_price=price))
                    base_price = price
                    ticker_count += 1
                    generated_count += 1
                current_date += timedelta(days=1)

            logger.info(f"  -> {ticker}: {ticker_count} records generated")

        db.commit()
        logger.info(f"Committed {generated_count} new records")

        logger.info("=== Final data range ===")
        for ticker in sorted(required_tickers):
            row = (
                db.query(ETFPrice.price_date, ETFPrice.price_date)
                .filter(ETFPrice.ticker == ticker)
            )
            from sqlalchemy import func
            result = db.query(
                func.min(ETFPrice.price_date),
                func.max(ETFPrice.price_date),
                func.count(ETFPrice.id),
            ).filter(ETFPrice.ticker == ticker).first()
            if result[0]:
                logger.info(f"{ticker}: {result[2]} records, {result[0]} ~ {result[1]}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
