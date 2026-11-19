# -*- coding: utf-8 -*-
"""SSH를 통해 NAS에서 1년치 데이터 생성"""

import paramiko
from nas_connection import connect_nas
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_data_on_nas():
    ssh = paramiko.SSHClient()

    try:
        logger.info("Connecting to NAS...")
        connect_nas(ssh, timeout=30)
        logger.info("Connected to NAS")

        # Python 스크립트
        commands = [
            ("Check current data", """cd /volume1/rebalancer && source venv/bin/activate && python3 -c "
from datetime import datetime, timedelta
from sqlalchemy import func, create_engine, text
from sqlalchemy.orm import sessionmaker
from config import PENSION_ETFS, IRP_PORTFOLIO

from config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

result = session.execute(text('SELECT COUNT(*) FROM etf_prices')).first()
print(f'Current records: {result[0]}')

existing = session.execute(text('SELECT DISTINCT ticker FROM etf_prices')).fetchall()
print(f'Existing tickers: {len(existing)}')
for t in existing:
    r = session.execute(text('SELECT MIN(price_date), MAX(price_date), COUNT(*) FROM etf_prices WHERE ticker = :t'), {'t': t[0]}).first()
    print(f'  {t[0]}: {r[2]} records, {r[0]} ~ {r[1]}')

session.close()
"
            """),

            ("Generate 1-year data", """cd /volume1/rebalancer && source venv/bin/activate && python3 << 'DATAEOF'
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import random

from config import PENSION_ETFS, IRP_PORTFOLIO
from database import ETFPrice

from config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

today = datetime.now().date()
one_year_ago = today - timedelta(days=365)

base_prices = {
    '379800': 20000,
    '360750': 35000,
    '402970': 10000,
    '449170': 5000,
    '379810': 25000,
    '0072R0': 15000,
    '453850': 8000,
    '214980': 11000,
}

required_tickers = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())

print('Generating 1-year historical data...')
total_generated = 0

for ticker in sorted(required_tickers):
    # Check if ticker has data
    result = session.execute(text('SELECT MIN(price_date) FROM etf_prices WHERE ticker = :t'), {'t': ticker}).first()

    if result[0] is None:
        start_date = one_year_ago
        end_date = today
        print(f'{ticker}: No data, generating full year')
    else:
        first_date = result[0]
        if first_date <= one_year_ago:
            print(f'{ticker}: Already has data from {first_date}')
            continue
        start_date = one_year_ago
        end_date = first_date - timedelta(days=1)
        print(f'{ticker}: Gap detected, generating from {start_date} to {end_date}')

    base_price = base_prices.get(ticker, 10000)
    generated = 0
    current_date = start_date

    while current_date <= end_date:
        if current_date.weekday() < 5:  # Mon-Fri only
            change = random.gauss(0.001, 0.02)
            price = base_price * (1 + change)
            price = max(price, base_price * 0.7)
            price = round(price, 2)

            session.add(ETFPrice(
                ticker=ticker,
                price_date=current_date,
                close_price=price
            ))
            generated += 1
            base_price = price

        current_date += timedelta(days=1)

    session.commit()
    total_generated += generated
    print(f'  -> Generated {generated} records')

print(f'Total generated: {total_generated}')

# Final check
result = session.execute(text('SELECT COUNT(*) FROM etf_prices')).first()
print(f'Final total records: {result[0]}')

session.close()
DATAEOF
            """),
        ]

        for desc, cmd in commands:
            logger.info(f"\n{'='*80}")
            logger.info(f"Executing: {desc}")
            logger.info('='*80)

            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
            time.sleep(2)  # 충분한 시간 제공

            output = ""
            try:
                output = stdout.read().decode('utf-8', errors='ignore')
            except:
                pass

            error = ""
            try:
                error = stderr.read().decode('utf-8', errors='ignore')
            except:
                pass

            if output:
                print(output)
            if error and "Deprecation" not in error and "Warning" not in error:
                print(f"Error: {error}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            ssh.close()
        except:
            pass

if __name__ == "__main__":
    generate_data_on_nas()
