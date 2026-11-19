# -*- coding: utf-8 -*-
"""NAS에서 Python으로 직접 데이터 확인"""

import paramiko
from nas_connection import connect_nas
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_data_on_nas():
    ssh = paramiko.SSHClient()

    try:
        logger.info("Connecting to NAS...")
        connect_nas(ssh, timeout=10)
        logger.info("Connected to NAS")

        # NAS 내에서 Python 스크립트 실행
        python_code = r"""
import sys
sys.path.insert(0, '/volume1/rebalancer')
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
from sqlalchemy import func, create_engine, text
from sqlalchemy.orm import sessionmaker
from config import PENSION_ETFS, IRP_PORTFOLIO

from config import DATABASE_URL

try:
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    result = session.execute(text("SELECT COUNT(*) as cnt FROM etf_prices")).first()
    total = result[0]
    print(f"Total records: {total}")

    results = session.execute(text("""SELECT ticker, COUNT(*) as cnt, MIN(price_date) as min_date, MAX(price_date) as max_date, DATEDIFF(MAX(price_date), MIN(price_date)) as days FROM etf_prices GROUP BY ticker ORDER BY ticker""")).fetchall()

    print("\n" + "="*100)
    print(f"{'Ticker':<12} {'ETF Name':<35} {'Count':<10} {'From':<12} {'To':<12} {'Days':<8}")
    print("="*100)

    existing_tickers = set()
    for ticker, cnt, min_date, max_date, days in results:
        existing_tickers.add(ticker)
        etf_info = PENSION_ETFS.get(ticker, IRP_PORTFOLIO.get(ticker, {}))
        etf_name = etf_info.get('name', 'Unknown')[:33]
        print(f"{ticker:<12} {etf_name:<35} {cnt:<10} {str(min_date):<12} {str(max_date):<12} {days:<8}")

    required = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())
    missing = required - existing_tickers

    print("="*100)
    print(f"\nRequired tickers: {len(required)}")
    print(f"Existing tickers: {len(existing_tickers)}")

    if missing:
        print(f"Missing tickers ({len(missing)}): {sorted(missing)}")

    print("\n" + "="*100)
    print("Data requirement analysis:")
    print("="*100)

    today = datetime.now().date()
    one_year_ago = today - timedelta(days=365)

    for ticker, cnt, min_date, max_date, days in results:
        status = "OK" if days >= 365 else "NEED_DATA"
        data_gap = ""
        if min_date > one_year_ago:
            gap_days = (one_year_ago - min_date).days
            data_gap = f" | Missing {gap_days} days before {min_date}"
        print(f"{ticker}: {days} days {status}{data_gap}")

    session.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
"""

        logger.info("Running database check on NAS...")
        cmd = f"cd /volume1/rebalancer && source venv/bin/activate && python3 << 'PYEOF'\n{python_code}\nPYEOF"
        stdin, stdout, stderr = ssh.exec_command(cmd)

        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')

        print(output)
        if error and "Deprecation" not in error and "Warning" not in error:
            print(f"\nError output:\n{error}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    check_data_on_nas()
