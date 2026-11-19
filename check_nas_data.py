# -*- coding: utf-8 -*-
"""NAS 데이터베이스 데이터 확인 (Unix 소켓 사용)"""

import paramiko
from nas_connection import connect_nas
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_nas_data():
    ssh = paramiko.SSHClient()

    try:
        logger.info("Connecting to NAS...")
        connect_nas(ssh, timeout=10)
        logger.info("Successfully connected to NAS")

        # mysql 클라이언트를 사용한 데이터 확인
        mysql_check = """
cd /volume1/rebalancer && export MYSQL_PWD="$(venv/bin/python -c 'import config; print(config.DB_PASSWORD)')" && mysql -u rebalancer -S /run/mysqld/mysqld10.sock rebalance_db << 'SQL'
-- 전체 데이터 개수
SELECT COUNT(*) as total_records FROM etf_prices;

-- 티커별 데이터
SELECT
    ticker,
    COUNT(*) as record_count,
    MIN(price_date) as first_date,
    MAX(price_date) as last_date,
    DATEDIFF(MAX(price_date), MIN(price_date)) as days_range
FROM etf_prices
GROUP BY ticker
ORDER BY ticker;

-- 부족한 티커 확인
SELECT 'Missing Tickers' as status, ticker FROM (
    SELECT '379800' as ticker UNION
    SELECT '360750' UNION
    SELECT '402970' UNION
    SELECT '449170' UNION
    SELECT '379810' UNION
    SELECT '0072R0' UNION
    SELECT '453850' UNION
    SELECT '214980'
) required_tickers
WHERE ticker NOT IN (SELECT DISTINCT ticker FROM etf_prices);

SQL
"""

        logger.info("Executing database queries...")
        stdin, stdout, stderr = ssh.exec_command(mysql_check, get_pty=False)
        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')

        print("\n=== Database Status ===\n")
        print(output)
        if error and "Warning" not in error:
            print(f"Error: {error}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()

if __name__ == "__main__":
    check_nas_data()
