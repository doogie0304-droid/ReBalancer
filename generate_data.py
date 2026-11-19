# -*- coding: utf-8 -*-
"""1년치 테스트 데이터 생성 및 부족한 데이터 채우기"""

import paramiko
from nas_connection import connect_nas
import io
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def deploy_data_script():
    """NAS에 데이터 생성 스크립트 배포 및 실행"""

    ssh = paramiko.SSHClient()

    try:
        logger.info("Connecting to NAS...")
        connect_nas(ssh, timeout=10)
        logger.info("Connected to NAS")

        # NAS에 배포할 데이터 생성 스크립트
        script_content = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '/volume1/rebalancer')

from datetime import datetime, timedelta
from sqlalchemy import func, create_engine, text
from sqlalchemy.orm import sessionmaker
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import PENSION_ETFS, IRP_PORTFOLIO
from database import ETFPrice

from config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# Step 1: 현재 데이터 확인
logger.info("=== Checking current data ===")
result = session.execute(text("SELECT COUNT(*) FROM etf_prices")).first()
current_count = result[0]
logger.info(f"Current records: {current_count}")

existing_tickers = session.execute(text("SELECT DISTINCT ticker FROM etf_prices")).fetchall()
existing_tickers = {t[0] for t in existing_tickers}
logger.info(f"Existing tickers: {existing_tickers}")

# Step 2: 필요한 티커 파악
required_tickers = set(PENSION_ETFS.keys()) | set(IRP_PORTFOLIO.keys())
missing_tickers = required_tickers - existing_tickers
logger.info(f"Required tickers: {required_tickers}")
logger.info(f"Missing tickers: {missing_tickers}")

# Step 3: 각 티커별 데이터 범위 확인
logger.info("\\n=== Data range check ===")
for ticker in sorted(required_tickers):
    result = session.execute(
        text("SELECT MIN(price_date), MAX(price_date), COUNT(*) FROM etf_prices WHERE ticker = :ticker"),
        {"ticker": ticker}
    ).first()

    if result[0]:
        min_date, max_date, cnt = result
        days = (max_date - min_date).days
        logger.info(f"{ticker}: {cnt} records, {min_date} ~ {max_date} ({days} days)")
    else:
        logger.info(f"{ticker}: No data")

# Step 4: 1년 이전 데이터 생성
logger.info("\\n=== Generating 1-year historical data ===")
today = datetime.now().date()
one_year_ago = today - timedelta(days=365)

# 한국 증시 휴장일 (간단한 목록, 실제로는 더 필요)
korean_holidays = {
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
    "2024-03-01", "2024-04-10", "2024-05-05", "2024-05-15", "2024-06-06",
    "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-03",
    "2024-10-09", "2024-12-25",
    "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-01",
    "2025-04-10", "2025-05-05", "2025-05-15", "2025-06-06", "2025-08-15",
    "2025-09-17", "2025-10-03", "2025-10-09", "2025-12-25",
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-01",
}

generated_count = 0
for ticker in required_tickers:
    # 이 티커의 첫 번째 날짜 찾기
    result = session.execute(
        text("SELECT MIN(price_date) FROM etf_prices WHERE ticker = :ticker"),
        {"ticker": ticker}
    ).first()

    first_date = result[0] if result[0] else today

    # 생성할 날짜 범위
    start_date = one_year_ago
    end_date = first_date - timedelta(days=1)

    if start_date >= end_date:
        logger.info(f"{ticker}: Already has sufficient data or no gap")
        continue

    logger.info(f"{ticker}: Generating data from {start_date} to {end_date}")

    # 기본 시세 설정 (임의의 값)
    base_prices = {
        "379800": 20000,    # KODEX 200
        "360750": 35000,    # TIGER 미국S&P500
        "402970": 10000,    # ACE 미국배당다우존스
        "449170": 5000,     # TIGER KOFR금리액티브
        "379810": 25000,    # KODEX 미국나스닥100
        "0072R0": 15000,    # TIGER KRX금현물
        "453850": 8000,     # ACE 미국30년국채액티브
        "214980": 11000,    # KODEX 단기채권PLUS
    }

    base_price = base_prices.get(ticker, 10000)

    # 날짜 범위의 데이터 생성
    current_date = start_date
    while current_date <= end_date:
        # 주말 또는 휴장일 제외
        if current_date.weekday() < 5 and str(current_date) not in korean_holidays:
            # 가우시안 랜덤 워크로 시세 생성
            change_pct = random.gauss(0.001, 0.02)
            price = base_price * (1 + change_pct)
            price = max(price, base_price * 0.7)  # 최소선 설정
            price = round(price, 2)

            new_record = ETFPrice(
                ticker=ticker,
                price_date=current_date,
                close_price=price
            )
            session.add(new_record)
            generated_count += 1

            base_price = price

        current_date += timedelta(days=1)

    logger.info(f"  -> Generated {generated_count} records so far")

# Step 5: 커밋
logger.info(f"\\n=== Committing {generated_count} new records ===")
session.commit()
logger.info("Successfully committed to database")

# Step 6: 최종 확인
logger.info("\\n=== Final data verification ===")
result = session.execute(text("SELECT COUNT(*) FROM etf_prices")).first()
final_count = result[0]
logger.info(f"Final total records: {final_count} (added {final_count - current_count})")

for ticker in sorted(required_tickers):
    result = session.execute(
        text("SELECT MIN(price_date), MAX(price_date), COUNT(*) FROM etf_prices WHERE ticker = :ticker"),
        {"ticker": ticker}
    ).first()

    if result[0]:
        min_date, max_date, cnt = result
        days = (max_date - min_date).days
        logger.info(f"{ticker}: {cnt} records, {min_date} ~ {max_date} ({days} days)")

session.close()
logger.info("\\nData generation completed!")
"""

        # 스크립트 파일 생성
        sftp = ssh.open_sftp()
        script_path = '/volume1/rebalancer/generate_1year_data.py'

        with sftp.file(script_path, 'w') as f:
            f.write(script_content)

        logger.info(f"Uploaded script to {script_path}")
        sftp.close()

        # 스크립트 실행 권한 설정
        logger.info("Setting execution permission...")
        ssh.exec_command(f"chmod +x {script_path}")

        # 스크립트 실행
        logger.info("Running data generation script...")
        stdin, stdout, stderr = ssh.exec_command(
            f"cd /volume1/rebalancer && source venv/bin/activate && python3 {script_path}"
        )

        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')

        print("\n" + "="*80)
        print("DATA GENERATION RESULTS")
        print("="*80 + "\n")
        print(output)

        if error:
            print(f"\nWarnings/Errors:\n{error}")

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
    deploy_data_script()
