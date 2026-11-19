# -*- coding: utf-8 -*-
"""NAS 데이터베이스 데이터 현황 확인"""

import paramiko
from nas_connection import connect_nas
import logging
from io import StringIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_nas_db():
    """NAS의 MariaDB 데이터 현황 확인"""

    ssh = paramiko.SSHClient()

    try:
        # NAS 접속
        logger.info("NAS에 접속 중...")
        connect_nas(ssh, timeout=10)
        logger.info("✅ NAS 접속 성공")

        # 데이터 확인 스크립트 실행
        python_script = """
import os
os.chdir('/volume1/rebalancer')
import sys
sys.path.insert(0, '/volume1/rebalancer')

from datetime import datetime, timedelta
from sqlalchemy import func, create_engine
from sqlalchemy.orm import sessionmaker
from database import ETFPrice
from config import PENSION_ETFS, IRP_PORTFOLIO

from config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

try:
    total_count = session.query(ETFPrice).count()
    print(f'=== NAS 데이터베이스 현황 ===')
    print(f'총 데이터: {total_count}개\\n')

    ticker_stats = session.query(
        ETFPrice.ticker,
        func.count(ETFPrice.id).label('count'),
        func.min(ETFPrice.price_date).label('min_date'),
        func.max(ETFPrice.price_date).label('max_date')
    ).group_by(ETFPrice.ticker).all()

    print('티커별 데이터 현황:')
    print('-' * 90)
    print(f'{"Ticker":<12} {"ETF Name":<35} {"Count":<8} {"From":<12} {"To":<12} {"Days":<8}')
    print('-' * 90)

    all_tickers = set()
    for ticker, count, min_date, max_date in ticker_stats:
        all_tickers.add(ticker)
        etf_info = PENSION_ETFS.get(ticker, IRP_PORTFOLIO.get(ticker, {}))
        etf_name = etf_info.get('name', 'Unknown')[:33]
        days = (max_date - min_date).days if min_date and max_date else 0
        print(f'{ticker:<12} {etf_name:<35} {count:<8} {str(min_date):<12} {str(max_date):<12} {days:<8}')

    print('-' * 90)

    # 1년 데이터 필요성 체크
    required_tickers = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())
    missing_tickers = required_tickers - all_tickers

    print(f'\\n필요한 티커: {len(required_tickers)}개')
    print(f'보유 중인 티커: {len(all_tickers)}개')
    if missing_tickers:
        print(f'부족한 티커: {len(missing_tickers)}개 - {missing_tickers}')

    # 데이터 부족 분석
    print(f'\\n데이터 부족 분석:')
    today = datetime.now().date()
    one_year_ago = today - timedelta(days=365)

    for ticker, count, min_date, max_date in ticker_stats:
        days_coverage = (max_date - min_date).days if min_date and max_date else 0
        if days_coverage < 365:
            if min_date > one_year_ago:
                days_missing = (one_year_ago - min_date).days
                print(f'  ⚠️  {ticker}: {days_coverage}일분만 있음 (필요: {one_year_ago} ~ {today})')
            else:
                print(f'  ❌ {ticker}: 데이터 부족')

    session.close()

except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
"""

        logger.info("데이터 확인 중...")
        stdin, stdout, stderr = ssh.exec_command(
            f"cd /volume1/rebalancer && source venv/bin/activate && python3 << 'EOF'\n{python_script}\nEOF"
        )

        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')

        print(output)
        if error:
            print(f"⚠️  Error:\n{error}")

    finally:
        ssh.close()

if __name__ == "__main__":
    check_nas_db()
