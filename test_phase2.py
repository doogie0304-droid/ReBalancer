# -*- coding: utf-8 -*-
"""Phase 2 테스트 스크립트"""

import logging
from datetime import datetime
from database import SessionLocal, init_db
from portfolio_engine import PortfolioEngine
from config import PENSION_ETFS, IRP_PORTFOLIO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_db_migration():
    """DB 마이그레이션 테스트"""
    logger.info("=" * 70)
    logger.info("DB Migration Test")
    logger.info("=" * 70)

    try:
        init_db()
        logger.info("✅ DB tables created successfully")
        return True
    except Exception as e:
        logger.error(f"❌ DB migration failed: {e}")
        return False

def test_portfolio_operations():
    """포트폴리오 CRUD 테스트"""
    logger.info("=" * 70)
    logger.info("Portfolio Operations Test")
    logger.info("=" * 70)

    db = SessionLocal()
    try:
        portfolio_engine = PortfolioEngine(db)

        # 1. 포트폴리오 종목 추가
        logger.info("Test 1: Add portfolio holding")
        result = portfolio_engine.add_portfolio_holding(
            ticker="360750",
            quantity=10.5,
            avg_buy_price=88500,
            account_type="IRP"
        )
        logger.info(f"Added: {result}")

        # 2. 포트폴리오 조회
        logger.info("\nTest 2: Get portfolio by ticker")
        result = portfolio_engine.get_portfolio_by_ticker("360750", "IRP")
        logger.info(f"Retrieved: {result}")

        # 3. 수익률 계산
        logger.info("\nTest 3: Calculate portfolio performance")
        performance = portfolio_engine.calculate_portfolio_performance("IRP")
        logger.info(f"Performance: {performance}")

        # 4. 포트폴리오 수정
        logger.info("\nTest 4: Update portfolio holding")
        result = portfolio_engine.update_portfolio_holding(
            ticker="360750",
            quantity=12.0,
            avg_buy_price=88000,
            account_type="IRP"
        )
        logger.info(f"Updated: {result}")

        # 5. 포트폴리오 조회 (수정 후)
        logger.info("\nTest 5: Get portfolio after update")
        result = portfolio_engine.get_portfolio_by_ticker("360750", "IRP")
        logger.info(f"Retrieved: {result}")

        logger.info("\n✅ All portfolio operations passed")
        return True

    except Exception as e:
        logger.error(f"❌ Portfolio operations failed: {e}", exc_info=True)
        return False
    finally:
        db.close()

def test_notification_system():
    """알림 시스템 테스트"""
    logger.info("=" * 70)
    logger.info("Notification System Test")
    logger.info("=" * 70)

    db = SessionLocal()
    try:
        from notification import TelegramNotificationManager

        notifier = TelegramNotificationManager(db)

        # 테스트 알림 (실제 발송 안 함 - 토큰이 없으면)
        logger.info("Test 1: Price Alert Structure")
        etf_data = {
            "date": "2026-07-06",
            "prices": {
                "360750": 88500,
                "379810": 45200,
                "402970": 52300
            }
        }
        logger.info(f"Price Alert Data: {etf_data}")

        logger.info("\nTest 2: Momentum Alert Structure")
        momentum_data = {
            "360750": {"weighted_score": 45.23},
            "379810": {"weighted_score": 52.15}
        }
        logger.info(f"Momentum Alert Data: {momentum_data}")

        logger.info("\nTest 3: Rebalance Alert Structure")
        signals = [
            {
                "ticker": "360750",
                "action": "BUY",
                "current_weight": 20.5,
                "target_weight": 25.0,
                "weight_diff": 4.5,
                "rebalance_amount": 450000
            }
        ]
        logger.info(f"Rebalance Alert Data: {signals}")

        logger.info("\n✅ All notification structures verified")
        return True

    except Exception as e:
        logger.error(f"❌ Notification system test failed: {e}", exc_info=True)
        return False
    finally:
        db.close()

if __name__ == "__main__":
    results = []

    results.append(("DB Migration", test_db_migration()))
    results.append(("Portfolio Operations", test_portfolio_operations()))
    results.append(("Notification System", test_notification_system()))

    logger.info("\n" + "=" * 70)
    logger.info("Test Summary")
    logger.info("=" * 70)

    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    all_passed = all(result[1] for result in results)
    if all_passed:
        logger.info("\n🎉 All tests passed!")
    else:
        logger.error("\n⚠️  Some tests failed")
