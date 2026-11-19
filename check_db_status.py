# -*- coding: utf-8 -*-
"""데이터베이스 데이터 현황 확인"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func
from database import SessionLocal, ETFPrice
from config import PENSION_ETFS, IRP_PORTFOLIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_db_status():
    """데이터베이스 데이터 현황 확인"""
    session = SessionLocal()

    try:
        # 전체 데이터 개수
        total_count = session.query(ETFPrice).count()
        logger.info(f"📊 Total ETF Price Records: {total_count}")

        # 티커별 데이터 현황
        ticker_stats = session.query(
            ETFPrice.ticker,
            func.count(ETFPrice.id).label('count'),
            func.min(ETFPrice.price_date).label('min_date'),
            func.max(ETFPrice.price_date).label('max_date')
        ).group_by(ETFPrice.ticker).all()

        logger.info("\n📈 Ticker-wise Data Status:")
        logger.info("-" * 80)
        logger.info(f"{'Ticker':<15} {'ETF Name':<30} {'Count':<10} {'From':<12} {'To':<12}")
        logger.info("-" * 80)

        all_tickers = set()
        for ticker, count, min_date, max_date in ticker_stats:
            all_tickers.add(ticker)
            etf_name = PENSION_ETFS.get(ticker, IRP_PORTFOLIO.get(ticker, {})).get('name', 'Unknown')
            logger.info(f"{ticker:<15} {etf_name:<30} {count:<10} {str(min_date):<12} {str(max_date):<12}")

        logger.info("-" * 80)

        # 필요한 티커 확인
        required_tickers = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())
        missing_tickers = required_tickers - all_tickers

        if missing_tickers:
            logger.warning(f"\n⚠️  Missing Tickers (No Data): {missing_tickers}")

        # 1년 데이터 필요성 확인
        today = datetime.now().date()
        one_year_ago = today - timedelta(days=365)

        logger.info(f"\n📅 Data Requirement Check:")
        logger.info(f"   Today: {today}")
        logger.info(f"   1 Year Ago: {one_year_ago}")

        for ticker, count, min_date, max_date in ticker_stats:
            days_needed = 252  # 증시 영업일 기준
            days_coverage = (max_date - min_date).days if min_date and max_date else 0

            logger.info(f"\n   {ticker} ({PENSION_ETFS.get(ticker, IRP_PORTFOLIO.get(ticker, {})).get('name', 'Unknown')})")
            logger.info(f"      - Data Range: {days_coverage} days")
            logger.info(f"      - Records: {count}")
            logger.info(f"      - Status: {'✅ Complete' if days_coverage >= 365 else '❌ Need More Data'}")

            if min_date and max_date:
                if min_date > one_year_ago:
                    days_missing = (one_year_ago - min_date).days
                    logger.warning(f"      - Missing: {days_missing} days before {min_date}")

        return total_count, all_tickers, required_tickers

    finally:
        session.close()

if __name__ == "__main__":
    total, existing, required = check_db_status()
    print("\n" + "="*80)
    print(f"✅ Existing Tickers: {len(existing)}")
    print(f"📋 Required Tickers: {len(required)}")
    print(f"⏳ Total Records: {total}")
    print("="*80)
